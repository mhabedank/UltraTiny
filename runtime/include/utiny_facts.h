/*
 * UltraTiny fact table (UTFT v1) reader: validation, lookup and answer rendering.
 * specs/006-hybrid-chemielehrer/contracts/fact-table-format.md and function-output.md.
 *
 * Plain C11, no heap, no float. The table is read through a callback (on the NodeMCU: SPI flash
 * reads outside the mapped megabyte); every read has a 4-byte aligned offset, length and buffer.
 * Parity twin: training/src/ultratiny/facttable.py.
 */
#ifndef UTINY_FACTS_H
#define UTINY_FACTS_H

#include <stddef.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

#define UT_FACTS_VERSION 1
#define UT_FACTS_HEADER 64
#define UT_FACTS_BUF 128  /* read buffer, bytes */
#define UT_FACTS_STR 128  /* longest string (template) incl. NUL */
#define UT_FACTS_KEY_MAX 12

/* Fixed texts (identical in facttable.py). */
extern const char UT_FACTS_TXT_UNKNOWN[]; /* "Das weiß ich leider nicht." */
extern const char UT_FACTS_TXT_MISSING[]; /* "Die Faktentabelle fehlt, ..." */
extern const char UT_FACTS_TXT_SEP[];     /* "– " before UNKNOWN after a printed prefix */

typedef enum { UT_FACTS_OK = 0, UT_FACTS_MISSING, UT_FACTS_CORRUPT } ut_facts_status;

/* Reads n bytes at offset off into buf (all multiples of 4 / aligned). Returns 0 on success.
 * Platforms may yield to a watchdog inside. */
typedef int (*ut_facts_read_fn)(void *user, uint32_t off, void *buf, uint32_t n);
typedef void (*ut_facts_write_fn)(void *user, const char *s, size_t n);

typedef struct {
    ut_facts_read_fn read;
    void *user;
    ut_facts_status status;
    uint32_t n_types, n_objects, n_records;
    uint32_t t_off, o_off, r_off, s_off, s_size, n_bytes, sha4;
    uint32_t buf[UT_FACTS_BUF / 4];
} ut_facts;

typedef struct {
    char code;
    uint8_t flags, kinds;
    char reverse_of;
    uint32_t tpl, na; /* string offsets; na = 0xFFFFFFFF: generic text */
} ut_fact_type;

/* Validate the table (magic, version, CRCs, offsets) inside an area of `area_size` bytes. */
ut_facts_status ut_facts_open(ut_facts *f, ut_facts_read_fn read, void *user, uint32_t area_size);
const char *ut_facts_status_str(ut_facts_status s);

/* 1 and *t filled if the table is OK and has type `code`, else 0. */
int ut_facts_type(ut_facts *f, char code, ut_fact_type *t);
/* Writes the template prefix (text before the first slot); returns its length in bytes. */
int ut_facts_prefix(ut_facts *f, const ut_fact_type *t, ut_facts_write_fn w, void *u);
/* Resolves `key`: writes the template rest or the not-applicable continuation and returns 1;
 * returns 0 (nothing written) when the key is unknown. */
int ut_facts_resolve(ut_facts *f, const ut_fact_type *t, const char *key, size_t key_len,
                     ut_facts_write_fn w, void *u);

/* Everything printed when a function answer ends (contracts/function-output.md "Console
 * behaviour"): MISSING without a valid table, UNKNOWN for an unknown type (t == NULL), else the
 * resolved rest; an unknown key gives "– " (if a prefix was written) + UNKNOWN. */
void ut_facts_finish(ut_facts *f, const ut_fact_type *t, int prefix_len_written, const char *key,
                     size_t key_len, ut_facts_write_fn w, void *u);

#ifdef __cplusplus
}
#endif

#endif /* UTINY_FACTS_H */
