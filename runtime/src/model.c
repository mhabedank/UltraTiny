/* UTNY v1/v2 loader and validation (contracts/model-format.md; v2 adds the <fn> special,
 * specs/006-hybrid-chemielehrer/contracts/function-output.md). */
#include <string.h>

#include "mathx.h"
#include "utiny.h"

const char *ut_status_str(ut_status s) {
    switch (s) {
    case UT_OK: return "ok";
    case UT_ERR_MAGIC: return "keine UTNY-Datei (Magic falsch)";
    case UT_ERR_VERSION: return "Formatversion nicht unterstuetzt";
    case UT_ERR_HEADER_CRC: return "Header-Pruefsumme falsch";
    case UT_ERR_PAYLOAD_CRC: return "Daten-Pruefsumme falsch (Datei beschaedigt?)";
    case UT_ERR_SIZE: return "Groesse passt nicht (abgeschnitten oder zu gross)";
    case UT_ERR_DIMS: return "ungueltige Modelldimensionen";
    case UT_ERR_ARENA: return "Arbeitsspeicher reicht nicht";
    case UT_ERR_CONTEXT_FULL: return "Kontext voll";
    case UT_ERR_TOKEN: return "ungueltiges Token";
    }
    return "unbekannter Fehler";
}

static uint16_t rd16(const uint8_t *p) { return (uint16_t)(p[0] | (p[1] << 8)); }
static uint32_t rd32(const uint8_t *p) {
    return (uint32_t)p[0] | ((uint32_t)p[1] << 8) | ((uint32_t)p[2] << 16) | ((uint32_t)p[3] << 24);
}
static float rdf32(const uint8_t *p) {
    uint32_t u = rd32(p);
    float f;
    memcpy(&f, &u, sizeof f);
    return f;
}

/* Walks the tensor block; `ok` is cleared if it would run past `end`. */
typedef struct {
    const uint8_t *p, *end;
    int ok;
} cursor;

static void align4(cursor *c, const uint8_t *base) {
    size_t off = (size_t)(c->p - base);
    c->p = base + ((off + 3u) & ~(size_t)3u);
}

static const float *take_f32(cursor *c, const uint8_t *base, int n) {
    if (!c->ok || (size_t)(c->end - c->p) < (size_t)n * 4u) {
        c->ok = 0;
        return NULL;
    }
    const float *r = (const float *)(const void *)c->p;
    c->p += (size_t)n * 4u;
    align4(c, base);
    return r;
}

static ut_qmat take_q(cursor *c, const uint8_t *base, int rows, int cols) {
    ut_qmat q = {0};
    q.rows = rows;
    q.cols = cols;
    size_t need = (size_t)rows * 4u + (size_t)rows * (size_t)cols;
    if (!c->ok || (size_t)(c->end - c->p) < need) {
        c->ok = 0;
        return q;
    }
    q.scale = (const float *)(const void *)c->p;
    q.w = (const int8_t *)(c->p + (size_t)rows * 4u);
    c->p += need;
    align4(c, base);
    return q;
}

ut_status ut_model_open(ut_model *m, const void *data, size_t size) {
    const uint8_t *img = (const uint8_t *)data;
    memset(m, 0, sizeof *m);
    if (size < UT_HEADER_SIZE) return UT_ERR_SIZE;
    if (((uintptr_t)img & 3u) != 0) return UT_ERR_SIZE;
    /* The image may sit in ESP8266 mapped flash: copy the header with 32-bit loads and parse the
     * copy (contracts/runtime-image-access.md). */
    uint32_t hdr_words[UT_HEADER_SIZE / 4];
    ut_copy_words(hdr_words, img, UT_HEADER_SIZE);
    const uint8_t *b = (const uint8_t *)hdr_words;
    if (memcmp(b, "UTNY", 4) != 0) return UT_ERR_MAGIC;
    uint32_t version = rd16(b + 4);
    if (version < 1 || version > UT_FORMAT_VERSION) return UT_ERR_VERSION;
    if (ut_crc32(b, 60) != rd32(b + 60)) return UT_ERR_HEADER_CRC;
    uint32_t hsize = rd16(b + 6);
    uint32_t payload = rd32(b + 40);
    if (hsize != UT_HEADER_SIZE || (size_t)hsize + payload > size || (payload & 3u) != 0)
        return UT_ERR_SIZE;
    size = (size_t)hsize + payload; /* the partition may be larger than the file */
    if (ut_crc32(img + hsize, payload) != rd32(b + 44)) return UT_ERR_PAYLOAD_CRC;

    m->vocab_size = rd16(b + 8);
    m->d_model = rd16(b + 10);
    m->n_layers = rd16(b + 12);
    m->n_heads = rd16(b + 14);
    m->n_kv_heads = rd16(b + 16);
    m->d_ff = rd16(b + 18);
    m->ctx_len = rd16(b + 20);
    uint16_t flags = rd16(b + 22);
    m->norm_eps = rdf32(b + 24);
    m->n_params = rd32(b + 48);
    m->size = size;
    if (m->vocab_size <= UT_TOK_UNK || m->vocab_size > UT_MAX_VOCAB || m->d_model == 0 ||
        m->n_heads == 0 || m->d_model % m->n_heads != 0 || m->n_kv_heads != 1 ||
        m->n_layers == 0 || m->n_layers > UT_MAX_LAYERS || m->d_ff == 0 || m->ctx_len < 2 ||
        (flags & 1u) == 0 || !(m->norm_eps > 0.0f))
        return UT_ERR_DIMS;
    m->head_dim = m->d_model / m->n_heads;
    if (m->head_dim % 4 != 0) return UT_ERR_DIMS;

    if (m->d_model % 4 != 0 || m->d_ff % 4 != 0) return UT_ERR_DIMS;

    uint32_t a_off = rd32(b + 28), m_off = rd32(b + 32), t_off = rd32(b + 36);
    if (a_off + 4u > size || m_off >= size || t_off > size || m_off > t_off || (a_off & 3u) ||
        (m_off & 3u) || (t_off & 3u))
        return UT_ERR_SIZE;
    if (ut_ld32(img + a_off) != (uint32_t)m->vocab_size ||
        a_off + 4u + 4u * (uint32_t)m->vocab_size > size)
        return UT_ERR_DIMS;
    m->alphabet = (const uint32_t *)(const void *)(img + a_off + 4);
    /* v1: specials 0..4; v2: specials 0..5 (5 = <fn>). Entry k must be 0xFFFF0000 + k. */
    m->n_special = version >= 2 ? UT_TOK_FN + 1 : UT_TOK_UNK + 1;
    m->has_fn = version >= 2;
    if (m->vocab_size <= m->n_special) return UT_ERR_DIMS;
    for (int k = 0; k < m->n_special; k++)
        if (ut_ld32(m->alphabet + k) != 0xFFFF0000u + (uint32_t)k) return UT_ERR_DIMS;
    if (ut_ld32(m->alphabet + m->n_special) >= 0xFFFF0000u) return UT_ERR_DIMS;
    /* Meta JSON: copied into RAM (word reads), must be NUL-terminated within meta_buf. */
    size_t meta_n = t_off - m_off;
    if (meta_n > sizeof m->meta_buf) meta_n = sizeof m->meta_buf;
    ut_copy_words(m->meta_buf, img + m_off, meta_n);
    if (memchr(m->meta_buf, 0, meta_n) == NULL) return UT_ERR_SIZE;
    m->meta = m->meta_buf;

    b = img; /* tensors are referenced in place */
    cursor c = {b + t_off, b + size, 1};
    int d = m->d_model, kvd = m->head_dim * m->n_kv_heads;
    m->tok_emb = take_q(&c, b, m->vocab_size, d);
    m->pos_emb = take_q(&c, b, m->ctx_len, d);
    for (int l = 0; l < m->n_layers; l++) {
        ut_layer *L = &m->layers[l];
        L->attn_norm = take_f32(&c, b, d);
        L->wq = take_q(&c, b, d, d);
        L->wk = take_q(&c, b, kvd, d);
        L->wv = take_q(&c, b, kvd, d);
        L->wo = take_q(&c, b, d, d);
        L->ffn_norm = take_f32(&c, b, d);
        L->w1 = take_q(&c, b, m->d_ff, d);
        L->w2 = take_q(&c, b, d, m->d_ff);
    }
    m->final_norm = take_f32(&c, b, d);
    if (!c.ok || c.p != b + size) return UT_ERR_SIZE;
    return UT_OK;
}

static size_t a16(size_t n) { return (n + 15u) & ~(size_t)15u; }

/* Keep in sync with reference.arena_size() (training/src/ultratiny/reference.py). */
size_t ut_arena_size(const ut_model *m) {
    size_t kvd = (size_t)m->head_dim * (size_t)m->n_kv_heads;
    size_t lt = (size_t)m->n_layers * (size_t)m->ctx_len;
    size_t d = (size_t)m->d_model;
    size_t s = 0;
    s += 2 * a16(lt * kvd);
    s += 2 * a16(4 * lt);
    s += 5 * a16(4 * d);
    s += 2 * a16(4 * kvd);
    s += a16(4 * (size_t)m->d_ff) + a16(4 * (size_t)m->vocab_size) + a16(4 * (size_t)m->ctx_len);
    s += a16(d > (size_t)m->d_ff ? d : (size_t)m->d_ff);
    s += a16((size_t)m->head_dim);
    return s;
}
