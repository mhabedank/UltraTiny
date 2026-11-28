/* UTKI v1 knowledge image reader (specs/008-wissens-compiler/contracts/image-format.md, query.md).
 * Mirrors training/src/ultratiny/knowledge/image.py byte for byte. No heap, no float. */
#include <stdio.h>
#include <string.h>

#include "utiny.h"
#include "utiny_knowledge.h"

const char UT_KB_TXT_MISSING[] = "Die Faktentabelle fehlt, Faktenfragen gehen gerade nicht.";

#define NONE16 0xFFFFu
#define F_CARD_MANY 1u
#define F_VAL2 8u
#define F_SUBJ2 16u
#define K_FORWARD 0
#define K_REVERSE 1
#define K_SELF 2
#define K_PROFILE 3
#define SL_NAME 1
#define SL_KEY 2
#define SL_V 3
#define SL_REL 4
#define SL_N 5
#define BAD 0xFFFFFFFFu

static uint32_t le16(const uint8_t *p) { return (uint32_t)p[0] | ((uint32_t)p[1] << 8); }
static uint32_t le32(const uint8_t *p) {
    return le16(p) | ((uint32_t)p[2] << 16) | ((uint32_t)p[3] << 24);
}

/* Copies n bytes at image offset off into dst through aligned chunk reads. */
static int read_at(ut_kb *kb, uint32_t off, void *dst, uint32_t n) {
    uint8_t *d = (uint8_t *)dst;
    while (n > 0) {
        uint32_t base = off & ~3u, skip = off - base;
        uint32_t len = UT_KB_BUF;
        if (base >= kb->n_bytes) return -1;
        if (base + len > kb->n_bytes) len = (kb->n_bytes - base + 3u) & ~3u;
        if (kb->read(kb->user, base, kb->buf, len) != 0) return -1;
        uint32_t take = len - skip;
        if (take > n) take = n;
        memcpy(d, (const uint8_t *)kb->buf + skip, take);
        d += take;
        off += take;
        n -= take;
    }
    return 0;
}

static uint32_t rd8(ut_kb *kb, uint32_t off) {
    uint8_t b;
    return read_at(kb, off, &b, 1) == 0 ? b : BAD;
}

static uint32_t rd16(ut_kb *kb, uint32_t off) {
    uint8_t b[2];
    return read_at(kb, off, b, 2) == 0 ? le16(b) : BAD;
}

/* NUL-terminated string at string offset `so` into dst (cap incl. NUL). Returns its length, or
 * -1 if absent, too long or past the string area. */
static int read_str(ut_kb *kb, uint32_t so, char *dst, int cap) {
    if (so == NONE16 || so >= kb->size_strings) return -1;
    uint32_t off = (uint32_t)kb->off_strings + so;
    int n = 0;
    while (n < cap) {
        uint32_t base = off & ~3u, skip = off - base;
        uint32_t len = UT_KB_BUF;
        if (base >= kb->n_bytes) return -1;
        if (base + len > kb->n_bytes) len = (kb->n_bytes - base + 3u) & ~3u;
        if (kb->read(kb->user, base, kb->buf, len) != 0) return -1;
        const char *b = (const char *)kb->buf;
        for (uint32_t i = skip; i < len && n < cap; i++, off++) {
            dst[n] = b[i];
            if (b[i] == 0) return n;
            n++;
        }
    }
    return -1;
}

static void emit_str(ut_kb *kb, uint32_t so, ut_kb_write_fn w, void *u) {
    char s[UT_KB_STR];
    int n = read_str(kb, so, s, sizeof s);
    if (n > 0) w(u, s, (size_t)n);
}

static size_t str_len(ut_kb *kb, uint32_t so) {
    char s[UT_KB_STR];
    int n = read_str(kb, so, s, sizeof s);
    return n > 0 ? (size_t)n : 0;
}

static void count_w(void *u, const char *s, size_t n) {
    (void)s;
    *(size_t *)u += n;
}

/* memcmp order, shorter first when one is a prefix of the other (Python bytes order). */
static int cmp_bytes(const char *a, size_t na, const char *b, size_t nb) {
    size_t n = na < nb ? na : nb;
    int c = memcmp(a, b, n);
    if (c != 0) return c;
    return na < nb ? -1 : (na > nb ? 1 : 0);
}

/* ---- open ------------------------------------------------------------------------------ */

ut_kb_status ut_kb_open(ut_kb *kb, ut_kb_read_fn read, void *user, uint32_t area_size) {
    memset(kb, 0, sizeof *kb);
    kb->read = read;
    kb->user = user;
    kb->status = UT_KB_MISSING;
    uint8_t h[UT_KB_HEADER];
    kb->n_bytes = UT_KB_HEADER;
    if (area_size < UT_KB_HEADER || read_at(kb, 0, h, UT_KB_HEADER) != 0) return kb->status;
    if (memcmp(h, "UTKI", 4) != 0) return kb->status;
    kb->status = UT_KB_CORRUPT;
    if (le16(h + 4) != UT_KB_VERSION || le16(h + 6) != UT_KB_HEADER) return kb->status;
    if (ut_crc32(h, 76) != le32(h + 76)) return kb->status;
    uint32_t nc = le16(h + 26), no = le16(h + 28), nr = le16(h + 30), nv = le16(h + 32);
    uint32_t p_size = le32(h + 52), end = UT_KB_HEADER + p_size;
    if (p_size > area_size || end > area_size) return kb->status;
    if (nc < 1 || nc > UT_KB_MAX_CLASSES || no < 1 || nr > 254 || nv < 1 || nv > 254)
        return kb->status;
    const uint32_t secs[7][2] = {
        {le16(h + 40), 4u * nc}, {le16(h + 42), 4u * no},  {le16(h + 44), 2u * no},
        {le16(h + 46), 16u * nr}, {le16(h + 48), 12u * nv}, {le16(h + 50), 12u},
        {le16(h + 36), le16(h + 38)},
    };
    for (int i = 0; i < 7; i++)
        if (secs[i][0] < UT_KB_HEADER || (secs[i][0] & 3u) || secs[i][0] + secs[i][1] > end)
            return kb->status;
    kb->n_bytes = end;
    uint32_t crc = 0xFFFFFFFFu;
    for (uint32_t off = UT_KB_HEADER; off < end; off += UT_KB_BUF) {
        uint32_t len = end - off < UT_KB_BUF ? end - off : UT_KB_BUF;
        if (kb->read(kb->user, off, kb->buf, (len + 3u) & ~3u) != 0) return kb->status;
        crc = ut_crc32_update(crc, kb->buf, len);
    }
    if ((crc ^ 0xFFFFFFFFu) != le32(h + 60)) return kb->status;
    uint32_t next = 0, off_classes = le16(h + 40);
    for (uint32_t i = 0; i < nc; i++) {
        uint32_t first = rd16(kb, off_classes + 4 * i), count = rd16(kb, off_classes + 4 * i + 2);
        if (first == BAD || count == BAD || first != next) return kb->status;
        kb->cls_first[i] = (uint16_t)first;
        kb->cls_count[i] = (uint16_t)count;
        next += count;
    }
    if (next != no) return kb->status;
    uint8_t tx[12];
    if (read_at(kb, le16(h + 50), tx, 12) != 0) return kb->status;
    memcpy(kb->topic, h + 8, 15);
    kb->topic[15] = 0;
    kb->schema_version = (uint16_t)le16(h + 24);
    kb->n_classes = (uint16_t)nc;
    kb->n_objects = (uint16_t)no;
    kb->n_relations = (uint16_t)nr;
    kb->n_views = (uint16_t)nv;
    kb->n_answerable = (uint16_t)le16(h + 34);
    kb->off_strings = (uint16_t)le16(h + 36);
    kb->size_strings = (uint16_t)le16(h + 38);
    kb->off_objects = (uint16_t)le16(h + 42);
    kb->off_keyidx = (uint16_t)le16(h + 44);
    kb->off_relations = (uint16_t)le16(h + 46);
    kb->off_views = (uint16_t)le16(h + 48);
    kb->txt_unknown = (uint16_t)le16(tx);
    kb->txt_na = (uint16_t)le16(tx + 2);
    kb->txt_sep = (uint16_t)le16(tx + 4);
    kb->txt_list_sep = (uint16_t)le16(tx + 6);
    kb->txt_list_last = (uint16_t)le16(tx + 8);
    kb->sha4 = le32(h + 56);
    kb->status = UT_KB_OK;
    return kb->status;
}

const char *ut_kb_status_str(ut_kb_status s) {
    switch (s) {
    case UT_KB_OK: return "OK";
    case UT_KB_MISSING: return "fehlt";
    case UT_KB_CORRUPT: return "defekt (Version/CRC)";
    case UT_KB_WRONG_TOPIC: return "falsches Thema";
    }
    return "?";
}

ut_kb_status ut_kb_check_topic(ut_kb *kb, const char *model_topic) {
    if (kb->status == UT_KB_OK && model_topic && model_topic[0] &&
        strcmp(model_topic, kb->topic) != 0)
        kb->status = UT_KB_WRONG_TOPIC;
    return kb->status;
}

/* ---- objects, relations, views ---------------------------------------------------------- */

typedef struct {
    uint8_t type, flags, subject, target;
    uint16_t name, n_values, off_values, off_forward, off_reverse;
} rel_t;

static int read_rel(ut_kb *kb, uint32_t i, rel_t *r) {
    uint8_t e[16];
    if (i >= kb->n_relations || read_at(kb, kb->off_relations + 16u * i, e, 16) != 0) return -1;
    r->name = (uint16_t)le16(e);
    r->type = e[2];
    r->flags = e[3];
    r->subject = e[4];
    r->target = e[5];
    r->n_values = (uint16_t)le16(e + 6);
    r->off_values = (uint16_t)le16(e + 8);
    r->off_forward = (uint16_t)le16(e + 10);
    r->off_reverse = (uint16_t)le16(e + 12);
    return r->subject < kb->n_classes ? 0 : -1;
}

static uint32_t obj_key(ut_kb *kb, uint32_t n) { return rd16(kb, kb->off_objects + 4u * n); }
static uint32_t obj_name(ut_kb *kb, uint32_t n) { return rd16(kb, kb->off_objects + 4u * n + 2); }

static int obj_class(const ut_kb *kb, uint32_t n) {
    for (int i = 0; i < kb->n_classes; i++)
        if (n >= kb->cls_first[i] && n < (uint32_t)kb->cls_first[i] + kb->cls_count[i]) return i;
    return -1;
}

static int find_object(ut_kb *kb, const char *key, size_t key_len, uint32_t *out) {
    uint32_t lo = 0, hi = kb->n_objects;
    char k[UT_KB_STR];
    while (lo < hi) {
        uint32_t mid = (lo + hi) / 2, n = rd16(kb, kb->off_keyidx + 2u * mid);
        if (n == BAD || n >= kb->n_objects) return 0;
        int len = read_str(kb, obj_key(kb, n), k, sizeof k);
        if (len < 0) return 0;
        int c = cmp_bytes(k, (size_t)len, key, key_len);
        if (c == 0) {
            *out = n;
            return 1;
        }
        if (c < 0)
            lo = mid + 1;
        else
            hi = mid;
    }
    return 0;
}

/* String offset of what a reverse query compares with (value or target object's key). */
static uint32_t value_key(ut_kb *kb, const rel_t *r, uint32_t vid) {
    uint32_t e = rd16(kb, r->off_values + 2u * vid);
    if (e == BAD) return BAD;
    return r->type == 4 ? obj_key(kb, e) : e;
}

/* String offset of what is printed (value or target object's name). */
static uint32_t value_text(ut_kb *kb, const rel_t *r, uint32_t vid) {
    uint32_t e = rd16(kb, r->off_values + 2u * vid);
    if (e == BAD) return BAD;
    return r->type == 4 ? obj_name(kb, e) : e;
}

static int find_value(ut_kb *kb, const rel_t *r, const char *key, size_t key_len, uint32_t *out) {
    uint32_t lo = 0, hi = r->n_values;
    char k[UT_KB_STR];
    while (lo < hi) {
        uint32_t mid = (lo + hi) / 2;
        int len = read_str(kb, value_key(kb, r, mid), k, sizeof k);
        if (len < 0) return 0;
        int c = cmp_bytes(k, (size_t)len, key, key_len);
        if (c == 0) {
            *out = mid;
            return 1;
        }
        if (c < 0)
            lo = mid + 1;
        else
            hi = mid;
    }
    return 0;
}

/* Entries [*a, *b) of item i of a posting-list block with n items; *base = first entry. */
static int posting(ut_kb *kb, uint32_t block, uint32_t n, uint32_t i, uint32_t *a, uint32_t *b,
                   uint32_t *base) {
    *a = rd16(kb, block + 2u * i);
    *b = rd16(kb, block + 2u * i + 2);
    *base = block + 2u * (n + 1);
    return (*a == BAD || *b == BAD || *b < *a) ? -1 : 0;
}

static uint32_t entry(ut_kb *kb, uint32_t base, uint32_t j, int width) {
    return width == 2 ? rd16(kb, base + 2u * j) : rd8(kb, base + j);
}

/* Single forward value ID of object n for relation r, or BAD (data-model.md View `{r:…}`). */
static uint32_t single_value(ut_kb *kb, const rel_t *r, uint32_t n) {
    if (obj_class(kb, n) != r->subject) return BAD;
    uint32_t local = n - kb->cls_first[r->subject];
    int wv = (r->flags & F_VAL2) ? 2 : 1;
    if (!(r->flags & F_CARD_MANY)) {
        uint32_t v = entry(kb, r->off_forward, local, wv);
        return v == (wv == 2 ? 0xFFFFu : 0xFFu) ? BAD : v;
    }
    uint32_t a, b, base;
    if (posting(kb, r->off_forward, kb->cls_count[r->subject], local, &a, &b, &base) != 0 || a == b)
        return BAD;
    return entry(kb, base, a, wv);
}

static void read_view(uint32_t i, const uint8_t e[12], ut_kb_view *v) {
    v->index = (uint8_t)i;
    v->name = (uint16_t)le16(e);
    v->kind = e[2];
    v->letter = e[3];
    v->rel = e[4];
    v->mask = e[5];
    v->tpl = (uint16_t)le16(e + 6);
    v->na = (uint16_t)le16(e + 8);
    v->more = (uint16_t)le16(e + 10);
}

int ut_kb_view_by_letter(ut_kb *kb, char letter, ut_kb_view *v) {
    if (kb == NULL || kb->status != UT_KB_OK || letter == 0) return 0;
    uint8_t e[12];
    for (uint32_t i = 0; i < kb->n_views; i++) {
        if (read_at(kb, kb->off_views + 12u * i, e, 12) != 0) return 0;
        if ((char)e[3] == letter) {
            read_view(i, e, v);
            return 1;
        }
    }
    return 0;
}

int ut_kb_view_by_name(ut_kb *kb, const char *name, size_t len, ut_kb_view *v) {
    if (kb == NULL || kb->status != UT_KB_OK) return 0;
    uint8_t e[12];
    char s[UT_KB_STR];
    for (uint32_t i = 0; i < kb->n_views; i++) {
        if (read_at(kb, kb->off_views + 12u * i, e, 12) != 0) return 0;
        int n = read_str(kb, le16(e), s, sizeof s);
        if (n >= 0 && (size_t)n == len && memcmp(s, name, len) == 0) {
            read_view(i, e, v);
            return 1;
        }
    }
    return 0;
}

static int prefix_len(const char *tpl, int n) {
    int i = 0;
    while (i < n && (uint8_t)tpl[i] > SL_N) i++;
    return i;
}

int ut_kb_prefix(ut_kb *kb, const ut_kb_view *v, ut_kb_write_fn w, void *u) {
    char tpl[UT_KB_STR];
    int n = read_str(kb, v->tpl, tpl, sizeof tpl);
    if (n <= 0) return 0;
    int p = prefix_len(tpl, n);
    if (p > 0) w(u, tpl, (size_t)p);
    return p;
}

/* ---- lookup and rendering (contracts/query.md) ------------------------------------------ */

enum { IT_NONE = 0, IT_SINGLE, IT_FWD_LIST, IT_REV_LIST };

typedef struct {
    const ut_kb_view *v;
    const char *key;
    size_t key_len;
    uint32_t obj; /* object for {name}: the subject (forward/self/profile) or first subject */
    int items;    /* IT_* */
    uint32_t n_items, vid, a, base, first;
    int width;
    rel_t rel;
    size_t budget; /* bytes left for {v} when it is a list */
} lk_t;

static ut_kb_outcome lookup(ut_kb *kb, lk_t *L) {
    const ut_kb_view *v = L->v;
    L->items = IT_NONE;
    L->n_items = 0;
    if (v->kind == K_REVERSE) {
        uint32_t vid, a, b, base;
        if (read_rel(kb, v->rel, &L->rel) != 0) return UT_KB_UNKNOWN;
        if (!find_value(kb, &L->rel, L->key, L->key_len, &vid)) return UT_KB_UNKNOWN;
        if (L->rel.off_reverse == NONE16 ||
            posting(kb, L->rel.off_reverse, L->rel.n_values, vid, &a, &b, &base) != 0 || a == b)
            return UT_KB_UNKNOWN;
        L->first = kb->cls_first[L->rel.subject];
        L->width = (L->rel.flags & F_SUBJ2) ? 2 : 1;
        uint32_t local = entry(kb, base, a, L->width);
        if (local == BAD) return UT_KB_UNKNOWN;
        L->obj = L->first + local;
        L->items = IT_REV_LIST;
        L->a = a;
        L->base = base;
        L->n_items = b - a;
        return UT_KB_FACT;
    }
    uint32_t n;
    if (!find_object(kb, L->key, L->key_len, &n)) return UT_KB_UNKNOWN;
    L->obj = n;
    int cls = obj_class(kb, n);
    if (cls < 0 || !((v->mask >> cls) & 1u)) return UT_KB_NA;
    if (v->kind == K_FORWARD) {
        if (read_rel(kb, v->rel, &L->rel) != 0) return UT_KB_NA;
        uint32_t local = n - kb->cls_first[L->rel.subject];
        int wv = (L->rel.flags & F_VAL2) ? 2 : 1;
        if (!(L->rel.flags & F_CARD_MANY)) {
            uint32_t x = entry(kb, L->rel.off_forward, local, wv);
            if (x == BAD || x == (wv == 2 ? 0xFFFFu : 0xFFu)) return UT_KB_NA;
            L->items = IT_SINGLE;
            L->vid = x;
            L->n_items = 1;
            return UT_KB_FACT;
        }
        uint32_t a, b, base;
        if (posting(kb, L->rel.off_forward, kb->cls_count[L->rel.subject], local, &a, &b,
                    &base) != 0 ||
            a == b)
            return UT_KB_NA;
        L->items = IT_FWD_LIST;
        L->width = wv;
        L->a = a;
        L->base = base;
        L->n_items = b - a;
        return UT_KB_FACT;
    }
    if (v->kind == K_PROFILE) {
        char tpl[UT_KB_STR];
        int len = read_str(kb, v->tpl, tpl, sizeof tpl);
        for (int i = 0; i + 1 < len; i++) {
            if ((uint8_t)tpl[i] != SL_REL) continue;
            rel_t r;
            if (read_rel(kb, (uint8_t)tpl[i + 1] - 1u, &r) != 0 || single_value(kb, &r, n) == BAD)
                return UT_KB_NA;
            i++;
        }
    }
    return UT_KB_FACT;
}

/* String offset of list item i. */
static uint32_t item_str(ut_kb *kb, const lk_t *L, uint32_t i) {
    switch (L->items) {
    case IT_SINGLE: return value_text(kb, &L->rel, L->vid);
    case IT_FWD_LIST: {
        uint32_t vid = entry(kb, L->base, L->a + i, L->width);
        return vid == BAD ? BAD : value_text(kb, &L->rel, vid);
    }
    case IT_REV_LIST: {
        uint32_t local = entry(kb, L->base, L->a + i, L->width);
        return local == BAD ? BAD : obj_name(kb, L->first + local);
    }
    }
    return BAD;
}

static void write_uint(uint32_t x, ut_kb_write_fn w, void *u) {
    char b[12];
    int n = snprintf(b, sizeof b, "%lu", (unsigned long)x);
    w(u, b, (size_t)n);
}

/* `more` text with {n} = m (other slots are empty, as in image.py). */
static void emit_more(ut_kb *kb, uint32_t so, uint32_t m, ut_kb_write_fn w, void *u) {
    char s[UT_KB_STR];
    int n = read_str(kb, so, s, sizeof s), run = 0;
    for (int i = 0; i < n; i++) {
        uint8_t b = (uint8_t)s[i];
        if (b > SL_N) continue;
        if (i > run) w(u, s + run, (size_t)(i - run));
        if (b == SL_N) write_uint(m, w, u);
        if (b == SL_REL) i++;
        run = i + 1;
    }
    if (n > run) w(u, s + run, (size_t)(n - run));
}

static void emit_list(ut_kb *kb, const lk_t *L, ut_kb_write_fn w, void *u) {
    uint32_t n = L->n_items;
    if (n == 0) return;
    if (n == 1) {
        emit_str(kb, item_str(kb, L, 0), w, u);
        return;
    }
    size_t sep = str_len(kb, kb->txt_list_sep), last = str_len(kb, kb->txt_list_last);
    size_t full = 0;
    for (uint32_t i = 0; i < n; i++) full += str_len(kb, item_str(kb, L, i));
    full += (n - 2) * sep + last;
    if (full <= L->budget) {
        for (uint32_t i = 0; i < n; i++) {
            if (i > 0) emit_str(kb, i == n - 1 ? kb->txt_list_last : kb->txt_list_sep, w, u);
            emit_str(kb, item_str(kb, L, i), w, u);
        }
        return;
    }
    uint32_t best = 0;
    size_t acc = 0;
    for (uint32_t k = 1; k < n; k++) {
        acc += str_len(kb, item_str(kb, L, k - 1)) + (k > 1 ? sep : 0);
        size_t more = 0;
        emit_more(kb, L->v->more, n - k, count_w, &more);
        if (acc + more <= L->budget)
            best = k;
        else
            break;
    }
    if (best == 0) best = 1; /* the compiler guarantees one item fits; print it regardless */
    for (uint32_t i = 0; i < best; i++) {
        if (i > 0) emit_str(kb, kb->txt_list_sep, w, u);
        emit_str(kb, item_str(kb, L, i), w, u);
    }
    emit_more(kb, L->v->more, n - best, w, u);
}

/* Writes template bytes tpl[from..n) with slots expanded; with_v = 0 leaves {v} empty. */
static void expand(ut_kb *kb, const lk_t *L, const char *tpl, int from, int n, int with_v,
                   ut_kb_write_fn w, void *u) {
    int run = from;
    for (int i = from; i < n; i++) {
        uint8_t b = (uint8_t)tpl[i];
        if (b > SL_N) continue;
        if (i > run) w(u, tpl + run, (size_t)(i - run));
        if (b == SL_NAME) {
            emit_str(kb, obj_name(kb, L->obj), w, u);
        } else if (b == SL_KEY) {
            w(u, L->key, L->key_len);
        } else if (b == SL_V) {
            if (with_v) emit_list(kb, L, w, u);
        } else if (b == SL_REL && i + 1 < n) {
            rel_t r;
            uint32_t vid;
            if (read_rel(kb, (uint8_t)tpl[++i] - 1u, &r) == 0 &&
                (vid = single_value(kb, &r, L->obj)) != BAD)
                emit_str(kb, value_text(kb, &r, vid), w, u);
        }
        run = i + 1;
    }
    if (n > run) w(u, tpl + run, (size_t)(n - run));
}

ut_kb_outcome ut_kb_finish(ut_kb *kb, const ut_kb_view *v, int prefix_len_written,
                           const char *key, size_t key_len, ut_kb_write_fn w, void *u) {
    if (kb == NULL || kb->status != UT_KB_OK) {
        w(u, UT_KB_TXT_MISSING, sizeof UT_KB_TXT_MISSING - 1);
        return UT_KB_MISSING_OUT;
    }
    if (v == NULL) {
        emit_str(kb, kb->txt_unknown, w, u);
        return UT_KB_UNKNOWN;
    }
    lk_t L;
    memset(&L, 0, sizeof L);
    L.v = v;
    L.key = key;
    L.key_len = key_len;
    ut_kb_outcome out = lookup(kb, &L);
    if (out == UT_KB_UNKNOWN) {
        if (prefix_len_written > 0) emit_str(kb, kb->txt_sep, w, u);
        emit_str(kb, kb->txt_unknown, w, u);
        return out;
    }
    if (out == UT_KB_NA) {
        if (v->na == NONE16) {
            emit_str(kb, obj_name(kb, L.obj), w, u);
            emit_str(kb, kb->txt_na, w, u);
        } else {
            char s[UT_KB_STR];
            int n = read_str(kb, v->na, s, sizeof s);
            if (n > 0) expand(kb, &L, s, 0, n, 0, w, u);
        }
        return out;
    }
    char tpl[UT_KB_STR];
    int n = read_str(kb, v->tpl, tpl, sizeof tpl);
    if (n < 0) return UT_KB_UNKNOWN;
    if (L.n_items > 1) {
        size_t a = 0;
        expand(kb, &L, tpl, 0, n, 0, count_w, &a);
        L.budget = a < UT_KB_RENDER_MAX ? UT_KB_RENDER_MAX - a : 0;
    }
    expand(kb, &L, tpl, prefix_len(tpl, n), n, 1, w, u);
    return out;
}

ut_kb_outcome ut_kb_query(ut_kb *kb, const char *arg, size_t n, ut_kb_write_fn w, void *u) {
    if (kb == NULL || kb->status != UT_KB_OK) {
        w(u, UT_KB_TXT_MISSING, sizeof UT_KB_TXT_MISSING - 1);
        return UT_KB_MISSING_OUT;
    }
    size_t head = 0;
    while (head < n && arg[head] != ' ') head++;
    const char *key = head < n ? arg + head + 1 : arg + n;
    size_t key_len = head < n ? n - head - 1 : 0;
    ut_kb_view v;
    int found = head == 1 ? ut_kb_view_by_letter(kb, arg[0], &v)
                          : ut_kb_view_by_name(kb, arg, head, &v);
    if (!found) {
        emit_str(kb, kb->txt_unknown, w, u);
        return UT_KB_UNKNOWN;
    }
    int p = ut_kb_prefix(kb, &v, w, u);
    return ut_kb_finish(kb, &v, p, key, key_len, w, u);
}

void ut_kb_overview(ut_kb *kb, ut_kb_write_fn w, void *u) {
    char line[96];
    if (kb == NULL || kb->status != UT_KB_OK) {
        int n = snprintf(line, sizeof line, "Wissen: %s",
                         ut_kb_status_str(kb ? kb->status : UT_KB_MISSING));
        w(u, line, (size_t)n);
        return;
    }
    int n = snprintf(line, sizeof line, "Thema %s, Schema %u, %u Fakten, data %08lx\r\nAnsichten:",
                     kb->topic, (unsigned)kb->schema_version, (unsigned)kb->n_answerable,
                     (unsigned long)kb->sha4);
    w(u, line, (size_t)n);
    uint8_t e[12];
    for (uint32_t i = 0; i < kb->n_views; i++) {
        if (read_at(kb, kb->off_views + 12u * i, e, 12) != 0) return;
        w(u, i ? ", " : " ", i ? 2 : 1);
        emit_str(kb, le16(e), w, u);
        if (e[3]) {
            char b[5] = {' ', '(', (char)e[3], ')', 0};
            w(u, b, 4);
        }
    }
}
