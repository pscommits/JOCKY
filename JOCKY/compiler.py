#!/usr/bin/env python3
"""
compiler.py — JOCKY Language Compiler  (SIH Hackathon — Component 1)

Usage:
    python compiler.py <source.jk> [options]

Options:
    --run           JIT-execute the compiled code immediately (no linker needed)
    --emit-ir       Save the LLVM IR to a .ll text file (useful for debugging)
    --no-obfuscate  Skip obfuscation passes (use when debugging)
    -o <dir>        Output directory (default: output/)

Binary output (default, no --run):
    Compiles to a .o object file, then links with stdlib/forensics.o using
    MinGW gcc to produce a fully standalone .exe — no Python runtime needed.
    Run  python build_stdlib.py  once first to build forensics.o.

Examples:
    python compiler.py tests/hello.jk --run
    python compiler.py tests/demo_forensics.jk --run --emit-ir
    python compiler.py tests/hello.jk --emit-ir
    python build_stdlib.py && python compiler.py tests/hello.jk
"""

import sys
import os
import argparse
import ctypes
import subprocess
import shutil

_HERE = os.path.dirname(os.path.abspath(__file__))
GCC   = shutil.which('gcc') or r'C:\mingw64\bin\gcc.exe'

try:
    import llvmlite.ir      as ir
    import llvmlite.binding as llvm
except ImportError:
    print("ERROR: llvmlite is not installed.")
    print("       Run:  pip install llvmlite")
    sys.exit(1)

from jocky.lexer    import Lexer
from jocky.parser   import Parser, ParseError
from jocky.semantic import SemanticAnalyzer, SemanticError
from jocky.codegen  import CodeGenerator, CodegenError
from jocky.passes   import ObfuscationPasses, compute_hash
from jocky.stdlib   import register_all


# ─────────────────────────────────────────────────────────────────────────────
# Pipeline
# ─────────────────────────────────────────────────────────────────────────────

def compile_jocky(
    source_path:  str,
    output_dir:   str  = 'output',
    emit_ir:      bool = False,
    run_jit:      bool = False,
    obfuscate:    bool = True,
) -> bool:
    """Run the full JOCKY compilation pipeline. Returns True on success."""

    print(f"\n{'='*60}")
    print(f"  JOCKY Compiler — SIH Hackathon")
    print(f"  Source : {source_path}")
    mode = 'JIT' if run_jit else 'native binary (gcc)'
    print(f"  Mode   : {mode}")
    print(f"{'='*60}")

    try:
        with open(source_path, 'r', encoding='utf-8') as f:
            source = f.read()
    except FileNotFoundError:
        print(f"\nERROR: File not found: {source_path}")
        return False

    base_name = os.path.splitext(os.path.basename(source_path))[0]
    os.makedirs(output_dir, exist_ok=True)

    # ── Stage 1: Lexer ────────────────────────────────────────────────────────
    print("\n[1/5] Lexer — tokenising source...")
    tokens = Lexer(source).tokenize()
    errors = [t for t in tokens if t.type.name == 'ERROR']
    if errors:
        print("  Lexer errors:")
        for e in errors:
            print(f"    Line {e.line}: {e.value}")
        return False
    print(f"      OK — {len(tokens)} tokens")

    # ── Stage 2: Parser ───────────────────────────────────────────────────────
    print("\n[2/5] Parser — building AST...")
    try:
        ast = Parser(tokens).parse()
    except ParseError as e:
        print(f"  Parse error: {e}")
        return False
    print(f"      OK — {len(ast.functions)} function(s) found")
    if 'start' not in [f.name for f in ast.functions]:
        print("  WARNING: No 'start' function — entry point is missing")

    # ── Stage 3: Semantic analysis ────────────────────────────────────────────
    print("\n[3/5] Semantic analysis — type checking...")
    try:
        SemanticAnalyzer().analyze(ast)
    except SemanticError as e:
        print(f"  Semantic error:\n{e}")
        return False
    print("      OK — no type errors")

    # ── Stage 4: IR generation ────────────────────────────────────────────────
    print("\n[4/5] Generating LLVM IR...")
    try:
        ir_module = CodeGenerator(source_name=base_name).generate(ast)
    except CodegenError as e:
        print(f"  IR generation error: {e}")
        return False
    print("      OK — IR module built")

    # ── Stage 5: Obfuscation (binary mode only) ───────────────────────────────
    if obfuscate and not run_jit:
        print("\n[5/5] Obfuscation passes...")
        ir_module = ObfuscationPasses(ir_module).run_all()
        print("      OK — build-ID injection + string XOR encryption + entropy noise")
    elif run_jit:
        print("\n[5/5] Obfuscation — skipped (JIT mode)")
    else:
        print("\n[5/5] Obfuscation — SKIPPED (--no-obfuscate)")

    # ── Emit IR text file ─────────────────────────────────────────────────────
    ir_text = str(ir_module)
    if emit_ir:
        ir_path = os.path.join(output_dir, base_name + '.ll')
        with open(ir_path, 'w', encoding='utf-8') as f:
            f.write(ir_text)
        print(f"\n  IR file  : {ir_path}")

    # ── Initialise LLVM native target ─────────────────────────────────────────
    llvm.initialize_native_target()
    llvm.initialize_native_asmprinter()

    # ── Parse + verify IR ─────────────────────────────────────────────────────
    try:
        llvm_mod = llvm.parse_assembly(ir_text)
        llvm_mod.verify()
    except Exception as e:
        print(f"\nERROR: IR verification failed: {e}")
        bad_path = os.path.join(output_dir, base_name + '_debug.ll')
        with open(bad_path, 'w') as f:
            f.write(ir_text)
        print(f"  Dumped bad IR to: {bad_path}")
        return False

    if run_jit:
        return _run_jit(llvm_mod)
    else:
        return _emit_and_link(llvm_mod, base_name, output_dir)


# ─────────────────────────────────────────────────────────────────────────────
# JIT execution
# ─────────────────────────────────────────────────────────────────────────────

def _run_jit(llvm_mod) -> bool:
    """JIT-compile and run the 'start' function using Python stdlib callbacks."""
    print("\n  JIT execution — entry point: 'start'")

    register_all()   # register Python stdlib callbacks BEFORE finalize

    target = llvm.Target.from_default_triple()
    tm     = target.create_target_machine()

    try:
        with llvm.create_mcjit_compiler(llvm_mod, tm) as engine:
            engine.finalize_object()
            engine.run_static_constructors()

            func_addr = engine.get_function_address('start')
            if func_addr == 0:
                print("  ERROR: 'start' function not found in compiled module")
                return False

            start_fn = ctypes.CFUNCTYPE(None)(func_addr)
            print(f"\n{'─'*40}")
            print("  Program output:")
            print(f"{'─'*40}")
            start_fn()
            print(f"{'─'*40}")
            print("\n  Execution complete.")
            return True

    except Exception as e:
        print(f"  JIT error: {e}")
        import traceback; traceback.print_exc()
        return False


# ─────────────────────────────────────────────────────────────────────────────
# Native binary output (gcc)
# ─────────────────────────────────────────────────────────────────────────────

def _emit_and_link(llvm_mod, base_name: str, output_dir: str) -> bool:
    """
    Compile IR to a .o object file, then link with stdlib/forensics.o using
    MinGW gcc to produce a standalone .exe.

    If forensics.o is not built yet, the .o is still written and the SHA-256
    is printed (useful for the polymorphism demo even without the full link).
    """
    target   = llvm.Target.from_default_triple()
    # reloc='static' avoids PIC GOT references that MinGW exe linker rejects
    tm       = target.create_target_machine(opt=2, reloc='static')

    obj_bytes = tm.emit_object(llvm_mod)
    obj_path  = os.path.join(output_dir, base_name + '.o')
    with open(obj_path, 'wb') as f:
        f.write(obj_bytes)
    print(f"\n  Object file : {obj_path}")

    sha = compute_hash(obj_path)
    print(f"  SHA-256     : {sha}")
    print("  (Run the same command again — SHA-256 will be different: polymorphism.)")

    # ── Locate stdlib/forensics.o ─────────────────────────────────────────────
    forensics_o = os.path.join(_HERE, 'stdlib', 'forensics.o')
    exe_path    = os.path.join(output_dir, base_name + '.exe')

    if not os.path.exists(forensics_o):
        print(f"\n  NOTE: stdlib/forensics.o not found.")
        print(f"        Run  python build_stdlib.py  to build it,")
        print(f"        then recompile for a fully linked .exe.")
        print(f"        (Use --run to JIT-execute without a linker.)")
        return True   # .o file succeeded — partial success

    # ── Link: jocky.o + forensics.o + entry.o → .exe ─────────────────────────
    if not os.path.exists(GCC):
        print(f"\n  NOTE: gcc not found at {GCC}. Cannot link.")
        return True

    # Compile a tiny C entry shim:  int main() { start(); return 0; }
    # JOCKY's 'start' function is not named 'main', so gcc needs a bridge.
    entry_c   = os.path.join(output_dir, '_jocky_entry.c')
    entry_o   = os.path.join(output_dir, '_jocky_entry.o')
    with open(entry_c, 'w') as f:
        f.write('extern void start(void);\nint main(void){start();return 0;}\n')

    r = subprocess.run([GCC, '-c', entry_c, '-o', entry_o, '-O2'],
                       capture_output=True, text=True)
    if r.returncode != 0:
        print(f"  Entry shim compile error:\n{r.stderr}")
        return True

    print(f"\n  Linking with gcc...")
    link_cmd = [
        GCC,
        obj_path,
        forensics_o,
        entry_o,
        '-o', exe_path,
        '-O2',
        '-mconsole',  # console app (main entry, not WinMain)
    ]

    result = subprocess.run(link_cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"  Link error:\n{result.stderr}")
        print(f"\n  Manual link command:")
        print(f"    gcc {obj_path} {forensics_o} {entry_o} -o {exe_path} -mconsole")
        return True   # .o still succeeded

    exe_sha = compute_hash(exe_path)
    size_kb = os.path.getsize(exe_path) // 1024
    print(f"\n  Executable  : {exe_path}  ({size_kb} KB)")
    print(f"  SHA-256 (exe): {exe_sha}")
    print(f"\n  Run it:  {exe_path}")
    return True


# ─────────────────────────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────────────────────────

def main() -> None:
    ap = argparse.ArgumentParser(
        description='JOCKY Language Compiler — SIH Hackathon Component 1',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    ap.add_argument('source',           help='Path to .jk source file')
    ap.add_argument('-o', '--output',   default='output',
                    help='Output directory (default: output/)')
    ap.add_argument('--emit-ir',        action='store_true',
                    help='Save LLVM IR to a .ll file')
    ap.add_argument('--run',            action='store_true',
                    help='JIT-execute immediately (no linker needed)')
    ap.add_argument('--no-obfuscate',   action='store_true',
                    help='Skip obfuscation passes (for debugging)')

    args = ap.parse_args()
    ok   = compile_jocky(
        source_path = args.source,
        output_dir  = args.output,
        emit_ir     = args.emit_ir,
        run_jit     = args.run,
        obfuscate   = not args.no_obfuscate,
    )
    sys.exit(0 if ok else 1)


if __name__ == '__main__':
    main()
