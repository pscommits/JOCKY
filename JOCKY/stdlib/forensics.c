/*
 * forensics.c — JOCKY Standard Library: Native C Implementations
 *
 * Compiled with MinGW gcc and linked with the JOCKY output object file to
 * produce a fully standalone native .exe — no Python runtime needed.
 *
 * Compile (run build_stdlib.py or do it manually):
 *   gcc -c stdlib/forensics.c -o stdlib/forensics.o -O2
 *
 * Link with a compiled JOCKY program:
 *   gcc output/myprog.o stdlib/forensics.o -o output/myprog.exe
 *
 * To replace stubs with real Windows API calls:
 *   - Add  -lpsapi  to the linker flags for process functions
 *   - Add  -lws2_32 to the linker flags for network functions
 *   - Add  -ladvapi32 for registry functions
 * Each stub below has a comment showing the real API call to use.
 */

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdint.h>
#include "forensics.h"

/* ═══════════════════════════════════════════════════════════════════════════
 * Internal process list structure
 * ═══════════════════════════════════════════════════════════════════════════ */

#define MAX_PROCS 64

typedef struct {
    char    names[MAX_PROCS][260];  /* 260 = MAX_PATH */
    int64_t pids [MAX_PROCS];
    int64_t count;
} ProcessList;

/* Hardcoded demo process table — replace body of procs_list() with
   EnumProcesses() + OpenProcess() + GetModuleBaseName() for real data. */
static ProcessList g_procs = {
    .names = {
        "svchost.exe",  "explorer.exe", "lsass.exe",
        "winlogon.exe", "csrss.exe",    "cmd.exe",   "python.exe"
    },
    .pids  = { 1234, 5678, 9012, 3456, 7890, 2222, 3333 },
    .count = 7
};

/* ═══════════════════════════════════════════════════════════════════════════
 * Output
 * ═══════════════════════════════════════════════════════════════════════════ */

void report(const char* message) {
    /* Real implementation: WriteConsoleA() or OutputDebugStringA() */
    if (message) {
        printf("[JOCKY] %s\n", message);
        fflush(stdout);
    }
}

/* ═══════════════════════════════════════════════════════════════════════════
 * Process enumeration
 * ═══════════════════════════════════════════════════════════════════════════ */

void* procs_list(void) {
    /*
     * Real implementation (requires -lpsapi):
     *   DWORD pids[1024], cbNeeded; int count;
     *   EnumProcesses(pids, sizeof(pids), &cbNeeded);
     *   count = cbNeeded / sizeof(DWORD);
     *   ProcessList* pl = malloc(sizeof(ProcessList));
     *   pl->count = 0;
     *   for (int i = 0; i < count && pl->count < MAX_PROCS; i++) {
     *       HANDLE h = OpenProcess(PROCESS_QUERY_INFORMATION|PROCESS_VM_READ, FALSE, pids[i]);
     *       if (h) {
     *           HMODULE hMod; DWORD cbMod;
     *           if (EnumProcessModules(h, &hMod, sizeof(hMod), &cbMod))
     *               GetModuleBaseNameA(h, hMod, pl->names[pl->count], 260);
     *           pl->pids[pl->count++] = pids[i];
     *           CloseHandle(h);
     *       }
     *   }
     *   return pl;
     */
    return (void*)&g_procs;
}

int64_t proc_count(void* procs) {
    if (!procs) return 0;
    return ((ProcessList*)procs)->count;
}

char* proc_name(void* procs, int64_t idx) {
    if (!procs) return "";
    ProcessList* pl = (ProcessList*)procs;
    if (idx >= 0 && idx < pl->count) return pl->names[(int)idx];
    return "";
}

int64_t proc_pid(void* procs, int64_t idx) {
    if (!procs) return -1;
    ProcessList* pl = (ProcessList*)procs;
    if (idx >= 0 && idx < pl->count) return pl->pids[(int)idx];
    return -1;
}

void proc_kill(int64_t pid) {
    /*
     * Real implementation:
     *   HANDLE h = OpenProcess(PROCESS_TERMINATE, FALSE, (DWORD)pid);
     *   if (h) { TerminateProcess(h, 1); CloseHandle(h); }
     */
    printf("[JOCKY] proc_kill(%lld) — stub\n", (long long)pid);
    fflush(stdout);
}

void* proc_mem_read(int64_t pid, int64_t addr, int64_t size) {
    /*
     * Real implementation:
     *   HANDLE h = OpenProcess(PROCESS_VM_READ, FALSE, (DWORD)pid);
     *   void* buf = malloc((size_t)size);
     *   SIZE_T nRead;
     *   ReadProcessMemory(h, (LPCVOID)(uintptr_t)addr, buf, (SIZE_T)size, &nRead);
     *   CloseHandle(h);
     *   return buf;
     */
    printf("[JOCKY] proc_mem_read(pid=%lld, addr=0x%llx, size=%lld) — stub\n",
           (long long)pid, (long long)addr, (long long)size);
    fflush(stdout);
    return calloc(1, (size_t)(size > 0 ? size : 1));
}

/* ═══════════════════════════════════════════════════════════════════════════
 * Network
 * ═══════════════════════════════════════════════════════════════════════════ */

void* net_conns(void) {
    /*
     * Real implementation (requires -lws2_32 -liphlpapi):
     *   MIB_TCPTABLE2* table = NULL; DWORD size = 0;
     *   GetTcpTable2(NULL, &size, TRUE);
     *   table = (MIB_TCPTABLE2*)malloc(size);
     *   GetTcpTable2(table, &size, TRUE);
     *   return table;
     */
    printf("[JOCKY] net_conns() — stub\n");
    fflush(stdout);
    return calloc(1, 8);
}

void* net_sniff(int64_t duration_ms) {
    printf("[JOCKY] net_sniff(%lld ms) — stub\n", (long long)duration_ms);
    fflush(stdout);
    return calloc(1, 8);
}

/* ═══════════════════════════════════════════════════════════════════════════
 * Registry
 * ═══════════════════════════════════════════════════════════════════════════ */

char* reg_read(const char* key, const char* value_name) {
    /*
     * Real implementation (requires -ladvapi32):
     *   HKEY hKey; char buf[1024]; DWORD bufLen = sizeof(buf), type;
     *   RegOpenKeyExA(HKEY_LOCAL_MACHINE, key, 0, KEY_READ, &hKey);
     *   RegQueryValueExA(hKey, value_name, NULL, &type, (LPBYTE)buf, &bufLen);
     *   RegCloseKey(hKey);
     *   return _strdup(buf);
     */
    printf("[JOCKY] reg_read(%s, %s) — stub\n", key ? key : "", value_name ? value_name : "");
    fflush(stdout);
    static char empty[1] = { '\0' };
    return empty;
}

void* reg_list(const char* key) {
    printf("[JOCKY] reg_list(%s) — stub\n", key ? key : "");
    fflush(stdout);
    return calloc(1, 8);
}

/* ═══════════════════════════════════════════════════════════════════════════
 * File system
 * ═══════════════════════════════════════════════════════════════════════════ */

void* file_list(const char* path) {
    /*
     * Real implementation:
     *   WIN32_FIND_DATAA fd; char pattern[MAX_PATH];
     *   snprintf(pattern, MAX_PATH, "%s\\*", path);
     *   HANDLE h = FindFirstFileA(pattern, &fd);
     *   ... collect file names ...
     *   FindClose(h);
     */
    printf("[JOCKY] file_list(%s) — stub\n", path ? path : "");
    fflush(stdout);
    return calloc(1, 8);
}

void* file_read(const char* path) {
    /*
     * Real implementation:
     *   FILE* f = fopen(path, "rb");
     *   fseek(f, 0, SEEK_END); long sz = ftell(f); rewind(f);
     *   void* buf = malloc(sz + 1); fread(buf, 1, sz, f); fclose(f);
     *   return buf;
     */
    printf("[JOCKY] file_read(%s) — stub\n", path ? path : "");
    fflush(stdout);
    return calloc(1, 8);
}

/* ═══════════════════════════════════════════════════════════════════════════
 * System info
 * ═══════════════════════════════════════════════════════════════════════════ */

void* sys_info(void) {
    /*
     * Real implementation:
     *   SYSTEM_INFO si; GetSystemInfo(&si);
     *   OSVERSIONINFOEXA osv; GetVersionExA((OSVERSIONINFOA*)&osv);
     *   ... package into a struct ...
     */
    printf("[JOCKY] sys_info() — stub\n");
    fflush(stdout);
    return calloc(1, 64);
}

/* ═══════════════════════════════════════════════════════════════════════════
 * Utilities
 * ═══════════════════════════════════════════════════════════════════════════ */

void* hash_file(const char* path) {
    /*
     * Real implementation (requires -lbcrypt):
     *   BCRYPT_ALG_HANDLE hAlg; BCRYPT_HASH_HANDLE hHash;
     *   BCryptOpenAlgorithmProvider(&hAlg, BCRYPT_SHA256_ALGORITHM, NULL, 0);
     *   ... compute hash into a 32-byte buffer ...
     *   BCryptCloseAlgorithmProvider(hAlg, 0);
     */
    printf("[JOCKY] hash_file(%s) — stub\n", path ? path : "");
    fflush(stdout);
    return calloc(1, 32);   /* 32 bytes = SHA-256 digest size */
}
