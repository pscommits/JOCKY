/*
 * forensics.h — JOCKY Standard Library: Public API
 *
 * This header declares all functions available to JOCKY programs.
 * Compiled by gcc into forensics.o and linked with the JOCKY output object.
 *
 * Type mapping (JOCKY → C):
 *   num     → int64_t   (64-bit signed integer)
 *   dec     → double
 *   text    → char*     (null-terminated string)
 *   flag    → int64_t   (0 = no, 1 = yes)
 *   raw     → void*     (opaque pointer — caller must not dereference)
 *   nothing → void
 */

#ifndef JOCKY_FORENSICS_H
#define JOCKY_FORENSICS_H

#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

/* ── Output ────────────────────────────────────────────────────────────────── */
void    report         (const char* message);

/* ── Process enumeration ───────────────────────────────────────────────────── */
void*   procs_list     (void);
int64_t proc_count     (void* procs);
char*   proc_name      (void* procs, int64_t index);
int64_t proc_pid       (void* procs, int64_t index);
void    proc_kill      (int64_t pid);
void*   proc_mem_read  (int64_t pid, int64_t addr, int64_t size);

/* ── Network ───────────────────────────────────────────────────────────────── */
void*   net_conns      (void);
void*   net_sniff      (int64_t duration_ms);

/* ── Registry ──────────────────────────────────────────────────────────────── */
char*   reg_read       (const char* key, const char* value_name);
void*   reg_list       (const char* key);

/* ── File system ───────────────────────────────────────────────────────────── */
void*   file_list      (const char* path);
void*   file_read      (const char* path);

/* ── System ────────────────────────────────────────────────────────────────── */
void*   sys_info       (void);
void*   hash_file      (const char* path);

#ifdef __cplusplus
}
#endif

#endif /* JOCKY_FORENSICS_H */
