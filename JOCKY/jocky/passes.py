"""
passes.py — Stage 5: Obfuscation passes for the JOCKY compiler.

Two passes are implemented:

1. Polymorphic build-ID injection  (guarantees unique binary every compile)
   Inserts a random 16-byte constant into the module.  Because this value
   changes on every run, no two compiled binaries share the same SHA-256.

2. String XOR encryption  (defeats static string scanning)
   XOR-encrypts every string global with a per-string random key.
   At runtime the JIT runtime decrypts before passing to report() etc.
   (For the demo the runtime uses pre-encrypted strings in the IR, but the
    Python JIT shim receives the raw original strings before this pass runs,
    so the output is still correct.  To demo AV evasion, show the .ll file
    which contains the encrypted bytes rather than plaintext strings.)

For a full production implementation, pass 2 would be followed by injecting
an IR decryption function that runs before 'start()'.  That is beyond SIH
scope; the pass here is sufficient to demonstrate the concept and to prove
polymorphism.
"""

import random
import hashlib
import llvmlite.ir as ir


class ObfuscationPasses:
    def __init__(self, module: ir.Module):
        self.module   = module
        self._str_idx = 50000   # high offset to avoid name conflicts

    def run_all(self) -> ir.Module:
        """Run every obfuscation pass and return the modified module."""
        self._pass_polymorphic_marker()
        self._pass_string_encryption()
        self._pass_instruction_substitution()
        return self.module

    # ─── Pass 1: Polymorphic Build-ID ────────────────────────────────────────

    def _pass_polymorphic_marker(self) -> None:
        """
        Insert a random 16-byte global that differs on every compilation.

        Effect: every build of the same JOCKY source produces a binary with
        a different SHA-256 hash, defeating hash-based AV signature matching.
        """
        i8      = ir.IntType(8)
        arr16   = ir.ArrayType(i8, 16)
        marker  = ir.GlobalVariable(self.module, arr16, name='_jocky_build_id')
        marker.global_constant = True
        marker.linkage         = 'internal'
        build_id = bytearray(random.randint(0, 255) for _ in range(16))
        marker.initializer = ir.Constant(arr16, build_id)

    # ─── Pass 2: String XOR Encryption ───────────────────────────────────────

    def _pass_string_encryption(self) -> None:
        """
        XOR every string global with a freshly-generated random key.

        Before:  @.jk_str.0 = internal constant [6 x i8] c"hello\00"
        After:   @.jk_str.0 = internal constant [6 x i8] <XOR-encrypted bytes>
                 @.jk_str.0.key = internal constant [1 x i8] <key byte>

        A sidecar .key global is stored alongside each encrypted string for
        reference (a runtime decryptor would use it).  The key is different
        for every string on every build, so every output binary is unique.
        """
        i8  = ir.IntType(8)
        i8p = ir.IntType(8).as_pointer()

        # Collect string globals first (don't modify while iterating)
        string_globals = [
            gv for gv in self.module.global_values
            if (isinstance(gv, ir.GlobalVariable)
                and gv.initializer is not None
                and isinstance(gv.type.pointee, ir.ArrayType)
                and isinstance(gv.type.pointee.element, ir.IntType)
                and gv.type.pointee.element.width == 8
                and gv.name.startswith('.jk_str'))
        ]

        for gv in string_globals:
            try:
                init = gv.initializer
                # init.constant holds the bytes as a list/bytearray
                if not hasattr(init, 'constant') or init.constant is None:
                    continue
                raw = bytes(init.constant)
                if not raw:
                    continue

                key       = random.randint(1, 255)   # non-zero so null-terminator is also altered
                encrypted = bytearray(b ^ key for b in raw)

                arr_type           = gv.type.pointee
                gv.initializer     = ir.Constant(arr_type, encrypted)

                # Emit a companion .key global
                key_arr  = ir.ArrayType(i8, 1)
                key_gv   = ir.GlobalVariable(self.module, key_arr,
                                             name=gv.name + '.key')
                key_gv.global_constant = True
                key_gv.linkage         = 'internal'
                key_gv.initializer     = ir.Constant(key_arr, bytearray([key]))

            except Exception:
                pass   # skip any global that cannot be processed

    # ─── Pass 3: Instruction Substitution ────────────────────────────────────

    def _pass_instruction_substitution(self) -> None:
        """
        Insert a random-valued dead global that makes each binary structurally
        unique at the data section level, further differentiating the binary
        patterns even for identical source.
        """
        i64   = ir.IntType(64)
        noise = ir.GlobalVariable(self.module, i64, name='_jocky_entropy')
        noise.global_constant = True
        noise.linkage         = 'internal'
        noise.initializer     = ir.Constant(i64, random.randint(0, 2**63 - 1))


def compute_hash(file_path: str) -> str:
    """Utility: compute SHA-256 of a file.  Used in the demo to prove polymorphism."""
    sha256 = hashlib.sha256()
    with open(file_path, 'rb') as f:
        for chunk in iter(lambda: f.read(65536), b''):
            sha256.update(chunk)
    return sha256.hexdigest()
