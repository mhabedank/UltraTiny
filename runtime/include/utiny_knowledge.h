/*
 * UltraTiny knowledge image (UTKI v1) reader: validation, lookup and answer rendering.
 * specs/008-wissens-compiler/contracts/image-format.md and contracts/query.md.
 *
 * Plain C11, no heap, no float. The image is read through a callback (on the NodeMCU: SPI flash
 * reads outside the mapped megabyte); every read has a 4-byte aligned offset, length and buffer.
 * Nothing here knows a topic: all texts except the "missing" message come from the image (FR-013).
 * Parity twin: training/src/ultratiny/knowledge/image.py.
 */
#ifndef UTINY_KNOWLEDGE_H
#define UTINY_KNOWLEDGE_H

#include <stddef.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

#define UT_KB_VERSION 1
#define UT_KB_HEADER 80
#define UT_KB_BUF 128     /* read buffer, bytes */
#define UT_KB_STR 128     /* longest string (template) incl. NUL */
#define UT_KB_KEY_MAX 12  /* function-output key characters (as in spec 006) */
#define UT_KB_RENDER_MAX 100
#define UT_KB_MAX_CLASSES 8

/* The only built-in text (topic-neutral, unchanged from spec 006). */
extern const char UT_KB_TXT_MISSING[]; /* "Die Faktentabelle fehlt, ..." */

typedef enum {
    UT_KB_OK = 0,
    UT_KB_MISSING,
    UT_KB_CORRUPT,
    UT_KB_WRONG_TOPIC
} ut_kb_status;

typedef enum { UT_KB_UNKNOWN = 0, UT_KB_FACT, UT_KB_NA, UT_KB_MISSING_OUT } ut_kb_outcome;

/* Reads n bytes at offset off into buf (all multiples of 4 / aligned). Returns 0 on success. */
typedef int (*ut_kb_read_fn)(void *user, uint32_t off, void *buf, uint32_t n);
typedef void (*ut_kb_write_fn)(void *user, const char *s, size_t n);

typedef struct {
    ut_kb_read_fn read;
    void *user;
    ut_kb_status status;
    char topic[16];
    uint16_t schema_version, n_classes, n_objects, n_relations, n_views, n_answerable;
    uint16_t off_strings, size_strings, off_objects, off_keyidx, off_relations, off_views;
    uint16_t cls_first[UT_KB_MAX_CLASSES], cls_count[UT_KB_MAX_CLASSES];
    uint16_t txt_unknown, txt_na, txt_sep, txt_list_sep, txt_list_last;
    uint32_t n_bytes, sha4;
    uint32_t buf[UT_KB_BUF / 4];
} ut_kb;

typedef struct {
    uint8_t index, kind, letter, rel, mask;
    uint16_t name, tpl, na, more; /* string offsets; 0xFFFF = none */
} ut_kb_view;

/* Validate the image (magic, version, CRCs, offsets) inside an area of `area_size` bytes. */
ut_kb_status ut_kb_open(ut_kb *kb, ut_kb_read_fn read, void *user, uint32_t area_size);
const char *ut_kb_status_str(ut_kb_status s);
/* Model meta `topic` (may be NULL or ""): a different non-empty topic sets UT_KB_WRONG_TOPIC
 * (research R11). Returns the resulting status. */
ut_kb_status ut_kb_check_topic(ut_kb *kb, const char *model_topic);

/* 1 and *v filled if the image is OK and has the view, else 0. */
int ut_kb_view_by_letter(ut_kb *kb, char letter, ut_kb_view *v);
int ut_kb_view_by_name(ut_kb *kb, const char *name, size_t len, ut_kb_view *v);
/* Writes the view's prefix (template text before the first slot); returns its length. */
int ut_kb_prefix(ut_kb *kb, const ut_kb_view *v, ut_kb_write_fn w, void *u);

/* Everything printed when a function answer ends (006 behaviour): MISSING without a valid image,
 * the topic's "unknown" text for an unknown view (v == NULL), else the rest of the answer; an
 * unknown key gives fallback separator (if a prefix was written) + "unknown". */
ut_kb_outcome ut_kb_finish(ut_kb *kb, const ut_kb_view *v, int prefix_len_written,
                           const char *key, size_t key_len, ut_kb_write_fn w, void *u);

/* `/wissen <view-or-letter> <key>`: the full answer (prefix + rest). */
ut_kb_outcome ut_kb_query(ut_kb *kb, const char *arg, size_t n, ut_kb_write_fn w, void *u);
/* `/wissen`: topic line and the list of views. */
void ut_kb_overview(ut_kb *kb, ut_kb_write_fn w, void *u);

#ifdef __cplusplus
}
#endif

#endif /* UTINY_KNOWLEDGE_H */
