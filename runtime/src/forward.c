/*
 * One-token forward pass with int8 KV cache (research.md R3/R4). Mirrors
 * Reference.feed() in training/src/ultratiny/reference.py operation by operation.
 */
#include <math.h>
#include <string.h>

#include "mathx.h"
#include "utiny.h"

static void *carve(uint8_t **p, size_t n) {
    void *r = *p;
    *p += (n + 15u) & ~(size_t)15u;
    return r;
}

ut_status ut_ctx_init(ut_ctx *c, const ut_model *m, void *arena, size_t arena_size) {
    memset(c, 0, sizeof *c);
    if (arena == NULL || ((uintptr_t)arena & 15u) != 0 || arena_size < ut_arena_size(m))
        return UT_ERR_ARENA;
    size_t kvd = (size_t)m->head_dim * (size_t)m->n_kv_heads;
    size_t lt = (size_t)m->n_layers * (size_t)m->ctx_len;
    size_t d = (size_t)m->d_model;
    uint8_t *p = (uint8_t *)arena;
    c->m = m;
    c->kq = carve(&p, lt * kvd);
    c->vq = carve(&p, lt * kvd);
    c->ks = carve(&p, 4 * lt);
    c->vs = carve(&p, 4 * lt);
    c->x = carve(&p, 4 * d);
    c->h = carve(&p, 4 * d);
    c->q = carve(&p, 4 * d);
    c->att = carve(&p, 4 * d);
    c->tmp = carve(&p, 4 * d);
    c->k = carve(&p, 4 * kvd);
    c->v = carve(&p, 4 * kvd);
    c->ff = carve(&p, 4 * (size_t)m->d_ff);
    c->logits = carve(&p, 4 * (size_t)m->vocab_size);
    c->scores = carve(&p, 4 * (size_t)m->ctx_len);
    c->aq = carve(&p, d > (size_t)m->d_ff ? d : (size_t)m->d_ff);
    c->qh = carve(&p, (size_t)m->head_dim);
    ut_ctx_reset(c);
    return UT_OK;
}

void ut_ctx_reset(ut_ctx *c) {
    c->pos = 0;
    ut_feed(c, UT_TOK_BOS);
}

void ut_rewind(ut_ctx *c, int n) {
    c->pos -= n;
    if (c->pos < 1) c->pos = 1; /* never drop <bos> */
}

const float *ut_logits(const ut_ctx *c) { return c->logits; }

static void qmatvec(ut_ctx *c, const ut_qmat *w, const float *x, float *y) {
    float xs = ut_quantize(x, w->cols, c->aq);
    ut_matvec(w->w, w->scale, w->rows, w->cols, c->aq, xs, y);
}

ut_status ut_feed(ut_ctx *c, int token) {
    const ut_model *m = c->m;
    if (c->pos >= m->ctx_len) return UT_ERR_CONTEXT_FULL;
    if (token < 0 || token >= m->vocab_size) return UT_ERR_TOKEN;
    const int d = m->d_model, hd = m->head_dim, nh = m->n_heads, p = c->pos;
    const float inv_sqrt_hd = 1.0f / sqrtf((float)hd);

    /* x = dequant(tok_emb[token]) + dequant(pos_emb[p]) */
    const int8_t *te = m->tok_emb.w + (size_t)token * d;
    const int8_t *pe = m->pos_emb.w + (size_t)p * d;
    float ts = m->tok_emb.scale[token], ps = m->pos_emb.scale[p];
    for (int i = 0; i < d; i++) c->x[i] = (float)te[i] * ts + (float)pe[i] * ps;

    for (int l = 0; l < m->n_layers; l++) {
        const ut_layer *L = &m->layers[l];
        int8_t *kq = c->kq + (size_t)l * m->ctx_len * hd;
        int8_t *vq = c->vq + (size_t)l * m->ctx_len * hd;
        float *ks = c->ks + (size_t)l * m->ctx_len;
        float *vs = c->vs + (size_t)l * m->ctx_len;

        ut_rmsnorm(c->x, L->attn_norm, d, m->norm_eps, c->h);
        float hs = ut_quantize(c->h, d, c->aq);
        ut_matvec(L->wq.w, L->wq.scale, d, d, c->aq, hs, c->q);
        ut_matvec(L->wk.w, L->wk.scale, hd, d, c->aq, hs, c->k);
        ut_matvec(L->wv.w, L->wv.scale, hd, d, c->aq, hs, c->v);
        ks[p] = ut_quantize(c->k, hd, kq + (size_t)p * hd);
        vs[p] = ut_quantize(c->v, hd, vq + (size_t)p * hd);

        for (int h = 0; h < nh; h++) {
            float qs = ut_quantize(c->q + h * hd, hd, c->qh);
            for (int t = 0; t <= p; t++) {
                int32_t acc = ut_dot_i8(c->qh, kq + (size_t)t * hd, hd);
                c->scores[t] = (((float)acc * qs) * ks[t]) * inv_sqrt_hd;
            }
            ut_softmax(c->scores, p + 1);
            float *out = c->att + h * hd;
            for (int j = 0; j < hd; j++) {
                float acc = 0.0f;
                for (int t = 0; t <= p; t++)
                    acc += c->scores[t] * ((float)vq[(size_t)t * hd + j] * vs[t]);
                out[j] = acc;
            }
        }
        qmatvec(c, &L->wo, c->att, c->tmp);
        for (int i = 0; i < d; i++) c->x[i] = c->x[i] + c->tmp[i];

        ut_rmsnorm(c->x, L->ffn_norm, d, m->norm_eps, c->h);
        qmatvec(c, &L->w1, c->h, c->ff);
        for (int i = 0; i < m->d_ff; i++)
            if (c->ff[i] < 0.0f) c->ff[i] = 0.0f;
        qmatvec(c, &L->w2, c->ff, c->tmp);
        for (int i = 0; i < d; i++) c->x[i] = c->x[i] + c->tmp[i];
    }
    ut_rmsnorm(c->x, m->final_norm, d, m->norm_eps, c->h);
    qmatvec(c, &m->tok_emb, c->h, c->logits);
    c->pos = p + 1;
    return UT_OK;
}

int ut_argmax(const float *logits, int n) {
    int best = 0;
    for (int i = 1; i < n; i++)
        if (logits[i] > logits[best]) best = i;
    return best;
}

static uint32_t xorshift32(uint32_t x) {
    x ^= x << 13;
    x ^= x >> 17;
    x ^= x << 5;
    return x;
}

int ut_sample(const float *logits, int n, float temperature, uint32_t *rng_state,
              float *scratch) {
    float m = logits[0] / temperature;
    for (int i = 0; i < n; i++) {
        scratch[i] = logits[i] / temperature;
        if (scratch[i] > m) m = scratch[i];
    }
    float total = 0.0f;
    for (int i = 0; i < n; i++) {
        scratch[i] = ut_expf(scratch[i] - m);
        total += scratch[i];
    }
    *rng_state = xorshift32(*rng_state);
    float u = (float)(*rng_state >> 8) * 0x1p-24f;
    float target = u * total;
    float cum = 0.0f;
    for (int i = 0; i < n; i++) {
        cum += scratch[i];
        if (cum > target) return i;
    }
    return n - 1;
}
