/* UTFT v1 fact table reader (specs/006-hybrid-chemielehrer/contracts/fact-table-format.md).
 * Mirrors training/src/ultratiny/facttable.py byte for byte. No heap, no float. */
#include <string.h>

#include "utiny.h"
#include "utiny_facts.h"

const char UT_FACTS_TXT_UNKNOWN[] = "Das weiß ich leider nicht.";
const char UT_FACTS_TXT_MISSING[] = "Die Faktentabelle fehlt, Faktenfragen gehen gerade nicht.";
const char UT_FACTS_TXT_SEP[] = "– ";
static const char TXT_GENERIC_NA[] = ": dazu habe ich keine Angabe.";

#define F_NEEDS_VALUE 1u
#define F_REVERSE 2u
#define SL_NAME 1
#define SL_KEY 2
#define SL_VALUE 3
#define SL_OTHER 4
#define NONE 0xFFFFFFFFu

static uint32_t le32(const uint8_t *p) {
    return (uint32_t)p[0] | ((uint32_t)p[1] << 8) | ((uint32_t)p[2] << 16) | ((uint32_t)p[3] << 24);
}

/* Copies n bytes at table offset off into dst through aligned chunk reads. */
static int read_at(ut_facts *f, uint32_t off, void *dst, uint32_t n) {
    uint8_t *d = (uint8_t *)dst;
    while (n > 0) {
        uint32_t base = off & ~3u, skip = off - base;
        uint32_t len = UT_FACTS_BUF;
        if (base + len > f->n_bytes) len = (f->n_bytes - base + 3u) & ~3u;
        if (len == 0 || f->read(f->user, base, f->buf, len) != 0) return -1;
        uint32_t take = len - skip;
        if (take > n) take = n;
        memcpy(d, (const uint8_t *)f->buf + skip, take);
        d += take;
        off += take;
        n -= take;
    }
    return 0;
}

/* NUL-terminated string at string offset `so` into dst (cap incl. NUL). Returns its length,
 * or -1 if it does not fit / runs past the string area. */
static int read_str(ut_facts *f, uint32_t so, char *dst, int cap) {
    if (so >= f->s_size) return -1;
    uint32_t off = f->s_off + so;
    int n = 0;
    while (n < cap) {
        uint32_t base = off & ~3u, skip = off - base;
        uint32_t len = UT_FACTS_BUF;
        if (base >= f->n_bytes) return -1;
        if (base + len > f->n_bytes) len = f->n_bytes - base;
        if (f->read(f->user, base, f->buf, len) != 0) return -1;
        const char *b = (const char *)f->buf;
        for (uint32_t i = skip; i < len && n < cap; i++, off++) {
            dst[n] = b[i];
            if (b[i] == 0) return n;
            n++;
        }
    }
    return -1;
}

ut_facts_status ut_facts_open(ut_facts *f, ut_facts_read_fn read, void *user, uint32_t area_size) {
    memset(f, 0, sizeof *f);
    f->read = read;
    f->user = user;
    f->status = UT_FACTS_MISSING;
    uint8_t h[UT_FACTS_HEADER];
    f->n_bytes = UT_FACTS_HEADER;
    if (area_size < UT_FACTS_HEADER || read_at(f, 0, h, UT_FACTS_HEADER) != 0) return f->status;
    if (memcmp(h, "UTFT", 4) != 0) return f->status;
    f->status = UT_FACTS_CORRUPT;
    if (le32(h + 4) != UT_FACTS_VERSION || le32(h + 8) != UT_FACTS_HEADER) return f->status;
    if (ut_crc32(h, 60) != le32(h + 60)) return f->status;
    uint32_t nt = le32(h + 12), no = le32(h + 16), nr = le32(h + 20);
    uint32_t t_off = le32(h + 24), o_off = le32(h + 28), r_off = le32(h + 32);
    uint32_t s_off = le32(h + 36), s_size = le32(h + 40), p_size = le32(h + 44);
    uint32_t end = UT_FACTS_HEADER + p_size;
    if (p_size > area_size || end > area_size || nt < 1 || nt > 52 || no < 1 || no > 4096 ||
        nr > 65535 || t_off != UT_FACTS_HEADER || o_off != t_off + 16u * nt ||
        r_off != o_off + 12u * no || s_off != r_off + 8u * nr || s_off + s_size != end ||
        ((p_size | s_size) & 3u) != 0)
        return f->status;
    f->n_bytes = end;
    uint32_t crc = 0xFFFFFFFFu;
    for (uint32_t off = UT_FACTS_HEADER; off < end; off += UT_FACTS_BUF) {
        uint32_t len = end - off < UT_FACTS_BUF ? end - off : UT_FACTS_BUF;
        if (f->read(f->user, off, f->buf, len) != 0) return f->status;
        crc = ut_crc32_update(crc, f->buf, len);
    }
    if ((crc ^ 0xFFFFFFFFu) != le32(h + 48)) return f->status;
    f->n_types = nt;
    f->n_objects = no;
    f->n_records = nr;
    f->t_off = t_off;
    f->o_off = o_off;
    f->r_off = r_off;
    f->s_off = s_off;
    f->s_size = s_size;
    f->sha4 = le32(h + 52);
    f->status = UT_FACTS_OK;
    return f->status;
}

const char *ut_facts_status_str(ut_facts_status s) {
    switch (s) {
    case UT_FACTS_OK: return "OK";
    case UT_FACTS_MISSING: return "fehlt";
    case UT_FACTS_CORRUPT: return "defekt (Version/CRC)";
    }
    return "?";
}

int ut_facts_type(ut_facts *f, char code, ut_fact_type *t) {
    if (f == NULL || f->status != UT_FACTS_OK) return 0;
    uint8_t e[16];
    for (uint32_t i = 0; i < f->n_types; i++) {
        if (read_at(f, f->t_off + 16u * i, e, 16) != 0) return 0;
        if ((char)e[0] == code) {
            t->code = code;
            t->flags = e[1];
            t->kinds = e[2];
            t->reverse_of = (char)e[3];
            t->tpl = le32(e + 4);
            t->na = le32(e + 8);
            return 1;
        }
    }
    return 0;
}

static int prefix_len(const char *tpl, int n) {
    int i = 0;
    while (i < n && (uint8_t)tpl[i] > SL_OTHER) i++;
    return i;
}

int ut_facts_prefix(ut_facts *f, const ut_fact_type *t, ut_facts_write_fn w, void *u) {
    char tpl[UT_FACTS_STR];
    int n = read_str(f, t->tpl, tpl, sizeof tpl);
    if (n <= 0) return 0;
    int p = prefix_len(tpl, n);
    if (p > 0) w(u, tpl, (size_t)p);
    return p;
}

typedef struct {
    uint32_t key, name;
    uint8_t kind;
} obj_entry;

static int read_obj(ut_facts *f, uint32_t i, obj_entry *o) {
    uint8_t e[12];
    if (read_at(f, f->o_off + 12u * i, e, 12) != 0) return -1;
    o->key = le32(e);
    o->name = le32(e + 4);
    o->kind = e[8];
    return 0;
}

static int read_rec(ut_facts *f, uint32_t i, uint32_t *obj, char *code, uint32_t *val) {
    uint8_t e[8];
    if (read_at(f, f->r_off + 8u * i, e, 8) != 0) return -1;
    *obj = (uint32_t)e[0] | ((uint32_t)e[1] << 8);
    *code = (char)e[2];
    *val = le32(e + 4);
    return 0;
}

/* memcmp order, shorter first when one is a prefix of the other (Python bytes order). */
static int cmp_bytes(const char *a, size_t na, const char *b, size_t nb) {
    size_t n = na < nb ? na : nb;
    int c = memcmp(a, b, n);
    if (c != 0) return c;
    return na < nb ? -1 : (na > nb ? 1 : 0);
}

static int find_object(ut_facts *f, const char *key, size_t key_len, uint32_t *idx) {
    uint32_t lo = 0, hi = f->n_objects;
    char k[UT_FACTS_KEY_MAX + 4];
    while (lo < hi) {
        uint32_t mid = (lo + hi) / 2;
        obj_entry o;
        if (read_obj(f, mid, &o) != 0) return 0;
        int n = read_str(f, o.key, k, sizeof k);
        if (n < 0) return 0;
        int c = cmp_bytes(k, (size_t)n, key, key_len);
        if (c == 0) {
            *idx = mid;
            return 1;
        }
        if (c < 0)
            lo = mid + 1;
        else
            hi = mid;
    }
    return 0;
}

/* Value string offset of record (obj, code), or NONE. */
static uint32_t find_value(ut_facts *f, uint32_t obj, char code) {
    uint32_t lo = 0, hi = f->n_records;
    while (lo < hi) {
        uint32_t mid = (lo + hi) / 2, ro, rv;
        char rc;
        if (read_rec(f, mid, &ro, &rc, &rv) != 0) return NONE;
        if (ro == obj && rc == code) return rv;
        if (ro < obj || (ro == obj && (uint8_t)rc < (uint8_t)code))
            lo = mid + 1;
        else
            hi = mid;
    }
    return NONE;
}

static void emit_str(ut_facts *f, uint32_t so, ut_facts_write_fn w, void *u) {
    char s[UT_FACTS_STR];
    int n = read_str(f, so, s, sizeof s);
    if (n > 0) w(u, s, (size_t)n);
}

/* Writes template bytes tpl[from..n) with slots expanded. */
static void expand(ut_facts *f, const char *tpl, int from, int n, uint32_t name, const char *key,
                   size_t key_len, uint32_t value, uint32_t obj, ut_facts_write_fn w, void *u) {
    int run = from;
    for (int i = from; i < n; i++) {
        uint8_t b = (uint8_t)tpl[i];
        if (b > SL_OTHER) continue;
        if (i > run) w(u, tpl + run, (size_t)(i - run));
        if (b == SL_NAME) {
            emit_str(f, name, w, u);
        } else if (b == SL_KEY) {
            w(u, key, key_len);
        } else if (b == SL_VALUE) {
            if (value != NONE) emit_str(f, value, w, u);
        } else if (b == SL_OTHER && i + 1 < n) {
            uint32_t v = find_value(f, obj, tpl[++i]);
            if (v != NONE) emit_str(f, v, w, u);
        }
        run = i + 1;
    }
    if (n > run) w(u, tpl + run, (size_t)(n - run));
}

static void not_applicable(ut_facts *f, const ut_fact_type *t, uint32_t name, const char *key,
                           size_t key_len, ut_facts_write_fn w, void *u) {
    if (t->na == NONE) {
        emit_str(f, name, w, u);
        w(u, TXT_GENERIC_NA, sizeof TXT_GENERIC_NA - 1);
        return;
    }
    char s[UT_FACTS_STR];
    int n = read_str(f, t->na, s, sizeof s);
    if (n > 0) expand(f, s, 0, n, name, key, key_len, NONE, 0, w, u);
}

int ut_facts_resolve(ut_facts *f, const ut_fact_type *t, const char *key, size_t key_len,
                     ut_facts_write_fn w, void *u) {
    if (f == NULL || f->status != UT_FACTS_OK) return 0;
    uint32_t obj = 0;
    int found = 0;
    if (t->flags & F_REVERSE) {
        char v[UT_FACTS_STR];
        for (uint32_t i = 0; i < f->n_records && !found; i++) {
            uint32_t ro, rv;
            char rc;
            if (read_rec(f, i, &ro, &rc, &rv) != 0) return 0;
            if (rc != t->reverse_of) continue;
            int n = read_str(f, rv, v, sizeof v);
            if (n >= 0 && cmp_bytes(v, (size_t)n, key, key_len) == 0) {
                obj = ro;
                found = 1;
            }
        }
    } else {
        found = find_object(f, key, key_len, &obj);
    }
    if (!found) return 0;
    obj_entry o;
    if (read_obj(f, obj, &o) != 0) return 0;
    if ((o.kind & t->kinds) == 0) {
        not_applicable(f, t, o.name, key, key_len, w, u);
        return 1;
    }
    uint32_t value = NONE;
    if (t->flags & F_NEEDS_VALUE) {
        value = find_value(f, obj, t->code);
        if (value == NONE) {
            not_applicable(f, t, o.name, key, key_len, w, u);
            return 1;
        }
    }
    char tpl[UT_FACTS_STR];
    int n = read_str(f, t->tpl, tpl, sizeof tpl);
    if (n < 0) return 0;
    for (int i = 0; i + 1 < n; i++)
        if (tpl[i] == SL_OTHER && find_value(f, obj, tpl[i + 1]) == NONE) {
            not_applicable(f, t, o.name, key, key_len, w, u);
            return 1;
        }
    expand(f, tpl, prefix_len(tpl, n), n, o.name, key, key_len, value, obj, w, u);
    return 1;
}

void ut_facts_finish(ut_facts *f, const ut_fact_type *t, int prefix_len_written, const char *key,
                     size_t key_len, ut_facts_write_fn w, void *u) {
    if (f == NULL || f->status != UT_FACTS_OK) {
        w(u, UT_FACTS_TXT_MISSING, sizeof UT_FACTS_TXT_MISSING - 1);
        return;
    }
    if (t == NULL) {
        w(u, UT_FACTS_TXT_UNKNOWN, sizeof UT_FACTS_TXT_UNKNOWN - 1);
        return;
    }
    if (ut_facts_resolve(f, t, key, key_len, w, u)) return;
    if (prefix_len_written > 0) w(u, UT_FACTS_TXT_SEP, sizeof UT_FACTS_TXT_SEP - 1);
    w(u, UT_FACTS_TXT_UNKNOWN, sizeof UT_FACTS_TXT_UNKNOWN - 1);
}
