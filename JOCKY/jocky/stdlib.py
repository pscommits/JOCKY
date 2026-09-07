"""
stdlib.py — Python implementations of JOCKY's standard library functions.

Used by the JIT execution mode (--run flag).  When LLVM JIT executes compiled
JOCKY code and encounters a call to report(), procs_list(), etc., it resolves
those calls to the Python functions registered here via ctypes callbacks.

For native binary output mode, the linker instead links in stdlib/forensics.c
(compiled by gcc), so these Python implementations are not involved at all.
"""

import ctypes
import llvmlite.binding as llvm

# ── Simulated process list (used in --run / JIT mode) ────────────────────────
# In a real deployment, procs_list() would call Windows API EnumProcesses().
_PROCESS_TABLE = [
    ('svchost.exe',  1234),
    ('explorer.exe', 5678),
    ('lsass.exe',    9012),
    ('winlogon.exe', 3456),
    ('csrss.exe',    7890),
    ('cmd.exe',      2222),
    ('python.exe',   3333),
]

# Pre-encode process names into stable C-compatible byte buffers.
# Must stay alive for the entire duration of JIT execution.
_NAME_BUFS: list[ctypes.Array] = [
    ctypes.create_string_buffer(name.encode('utf-8') + b'\x00')
    for name, _ in _PROCESS_TABLE
]

# All ctypes callback objects kept here to prevent garbage collection.
_CALLBACKS: dict[str, object] = {}


# ── Callback implementations ─────────────────────────────────────────────────

def _cb_report():
    @ctypes.CFUNCTYPE(None, ctypes.c_char_p)
    def report(msg: bytes) -> None:
        if msg:
            print(f"[JOCKY] {msg.decode('utf-8', errors='replace')}")
    return report


def _cb_procs_list():
    @ctypes.CFUNCTYPE(ctypes.c_void_p)
    def procs_list() -> int:
        return 1   # non-null sentinel; Python side ignores the value
    return procs_list


def _cb_proc_count():
    @ctypes.CFUNCTYPE(ctypes.c_int64, ctypes.c_void_p)
    def proc_count(procs: int) -> int:
        return len(_PROCESS_TABLE)
    return proc_count


def _cb_proc_name():
    @ctypes.CFUNCTYPE(ctypes.c_void_p, ctypes.c_void_p, ctypes.c_int64)
    def proc_name(procs: int, idx: int) -> int:
        if 0 <= idx < len(_NAME_BUFS):
            return ctypes.cast(_NAME_BUFS[idx], ctypes.c_void_p).value
        return 0
    return proc_name


def _cb_proc_pid():
    @ctypes.CFUNCTYPE(ctypes.c_int64, ctypes.c_void_p, ctypes.c_int64)
    def proc_pid(procs: int, idx: int) -> int:
        if 0 <= idx < len(_PROCESS_TABLE):
            return _PROCESS_TABLE[idx][1]
        return -1
    return proc_pid


def _cb_proc_kill():
    @ctypes.CFUNCTYPE(None, ctypes.c_int64)
    def proc_kill(pid: int) -> None:
        print(f"[JOCKY] proc_kill({pid})")
    return proc_kill


def _cb_proc_mem_read():
    @ctypes.CFUNCTYPE(ctypes.c_void_p, ctypes.c_int64, ctypes.c_int64, ctypes.c_int64)
    def proc_mem_read(pid: int, addr: int, size: int) -> int:
        print(f"[JOCKY] proc_mem_read(pid={pid}, addr=0x{addr:x}, size={size})")
        buf = (ctypes.c_uint8 * max(size, 1))()
        return ctypes.cast(buf, ctypes.c_void_p).value
    return proc_mem_read


def _cb_net_conns():
    @ctypes.CFUNCTYPE(ctypes.c_void_p)
    def net_conns() -> int:
        print("[JOCKY] net_conns()")
        return ctypes.cast((ctypes.c_uint8 * 1)(), ctypes.c_void_p).value
    return net_conns


def _cb_net_sniff():
    @ctypes.CFUNCTYPE(ctypes.c_void_p, ctypes.c_int64)
    def net_sniff(duration_ms: int) -> int:
        print(f"[JOCKY] net_sniff({duration_ms}ms)")
        return ctypes.cast((ctypes.c_uint8 * 1)(), ctypes.c_void_p).value
    return net_sniff


def _cb_reg_read():
    _empty = ctypes.create_string_buffer(b'\x00')

    @ctypes.CFUNCTYPE(ctypes.c_void_p, ctypes.c_char_p, ctypes.c_char_p)
    def reg_read(key: bytes, value_name: bytes) -> int:
        k = key.decode('utf-8', errors='replace') if key else ''
        v = value_name.decode('utf-8', errors='replace') if value_name else ''
        print(f"[JOCKY] reg_read({k!r}, {v!r})")
        return ctypes.cast(_empty, ctypes.c_void_p).value
    _cb_reg_read._empty = _empty
    return reg_read


def _cb_reg_list():
    @ctypes.CFUNCTYPE(ctypes.c_void_p, ctypes.c_char_p)
    def reg_list(key: bytes) -> int:
        k = key.decode('utf-8', errors='replace') if key else ''
        print(f"[JOCKY] reg_list({k!r})")
        return ctypes.cast((ctypes.c_uint8 * 1)(), ctypes.c_void_p).value
    return reg_list


def _cb_file_list():
    @ctypes.CFUNCTYPE(ctypes.c_void_p, ctypes.c_char_p)
    def file_list(path: bytes) -> int:
        p = path.decode('utf-8', errors='replace') if path else ''
        print(f"[JOCKY] file_list({p!r})")
        return ctypes.cast((ctypes.c_uint8 * 1)(), ctypes.c_void_p).value
    return file_list


def _cb_file_read():
    @ctypes.CFUNCTYPE(ctypes.c_void_p, ctypes.c_char_p)
    def file_read(path: bytes) -> int:
        p = path.decode('utf-8', errors='replace') if path else ''
        print(f"[JOCKY] file_read({p!r})")
        return ctypes.cast((ctypes.c_uint8 * 1)(), ctypes.c_void_p).value
    return file_read


def _cb_sys_info():
    @ctypes.CFUNCTYPE(ctypes.c_void_p)
    def sys_info() -> int:
        print("[JOCKY] sys_info()")
        return ctypes.cast((ctypes.c_uint8 * 64)(), ctypes.c_void_p).value
    return sys_info


def _cb_hash_file():
    @ctypes.CFUNCTYPE(ctypes.c_void_p, ctypes.c_char_p)
    def hash_file(path: bytes) -> int:
        p = path.decode('utf-8', errors='replace') if path else ''
        print(f"[JOCKY] hash_file({p!r})")
        return ctypes.cast((ctypes.c_uint8 * 32)(), ctypes.c_void_p).value
    return hash_file


# ── Registration ─────────────────────────────────────────────────────────────

def register_all() -> None:
    """
    Register every stdlib function with LLVM's global symbol table so the
    MCJIT engine can resolve calls from compiled JOCKY code.

    Must be called BEFORE engine.finalize_object().
    """
    builders = {
        'report':        _cb_report,
        'procs_list':    _cb_procs_list,
        'proc_count':    _cb_proc_count,
        'proc_name':     _cb_proc_name,
        'proc_pid':      _cb_proc_pid,
        'proc_kill':     _cb_proc_kill,
        'proc_mem_read': _cb_proc_mem_read,
        'net_conns':     _cb_net_conns,
        'net_sniff':     _cb_net_sniff,
        'reg_read':      _cb_reg_read,
        'reg_list':      _cb_reg_list,
        'file_list':     _cb_file_list,
        'file_read':     _cb_file_read,
        'sys_info':      _cb_sys_info,
        'hash_file':     _cb_hash_file,
    }
    for name, builder_fn in builders.items():
        cb   = builder_fn()
        addr = ctypes.cast(cb, ctypes.c_void_p).value
        llvm.add_symbol(name, addr)
        _CALLBACKS[name] = cb   # keep alive
