#!/usr/bin/env python3
"""
build_stdlib.py — Compile forensics.c into forensics.o using MinGW gcc.

Run this ONCE before using binary output mode (--emit-obj or just running
compiler.py without --run).  You only need to re-run it if forensics.c changes.

Usage:
    python build_stdlib.py

Output:
    stdlib/forensics.o   (linked by the compiler automatically)
"""

import subprocess
import sys
import os
import shutil

GCC         = shutil.which('gcc') or r'C:\mingw64\bin\gcc.exe'
FORENSICS_C = os.path.join(os.path.dirname(__file__), 'stdlib', 'forensics.c')
FORENSICS_O = os.path.join(os.path.dirname(__file__), 'stdlib', 'forensics.o')


def build() -> bool:
    if not os.path.exists(GCC):
        print(f"ERROR: gcc not found at {GCC}")
        print("       Install MinGW-w64 or add gcc to PATH.")
        return False

    if not os.path.exists(FORENSICS_C):
        print(f"ERROR: forensics.c not found at {FORENSICS_C}")
        return False

    print(f"[build_stdlib] Compiling {FORENSICS_C}")
    print(f"               gcc: {GCC}")

    cmd = [GCC, '-c', FORENSICS_C, '-o', FORENSICS_O,
           '-O2', '-std=c11', '-Wall']

    result = subprocess.run(cmd, capture_output=True, text=True)

    if result.returncode != 0:
        print(f"\nERROR: gcc failed:\n{result.stderr}")
        return False

    size = os.path.getsize(FORENSICS_O)
    print(f"\n  OK — {FORENSICS_O}  ({size} bytes)")
    print("\nStdlib is ready.  You can now compile JOCKY programs to native binaries:")
    print("  python compiler.py tests/demo_forensics.jk --emit-ir")
    return True


if __name__ == '__main__':
    ok = build()
    sys.exit(0 if ok else 1)
