/*
 * UltraTiny portable runtime (contracts/runtime-api.md).
 *
 * Plain C11, no heap allocation, no global mutable state. The model image (UTNY v1,
 * contracts/model-format.md) is read in place, e.g. from memory-mapped flash; all
 * working memory comes from a caller-provided static arena.
 */
#ifndef UTINY_H
#define UTINY_H

#include <stddef.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

#define UT_FORMAT_VERSION 1
#define UT_HEADER_SIZE 64
#define UT_MAX_VOCAB 96
#define UT_MAX_LAYERS 16

/* Special tokens (data-model.md Alphabet). */
#define UT_TOK_PAD 0
#define UT_TOK_BOS 1
#define UT_TOK_SEP 2
#define UT_TOK_EOS 3
#define UT_TOK_UNK 4

typedef enum {
    UT_OK = 0,
    UT_ERR_MAGIC,
    UT_ERR_VERSION,
    UT_ERR_HEADER_CRC,
    UT_ERR_PAYLOAD_CRC,
    UT_ERR_SIZE,
    UT_ERR_DIMS,
    UT_ERR_ARENA,
    UT_ERR_CONTEXT_FULL,
    UT_ERR_TOKEN
} ut_status;

const char *ut_status_str(ut_status s);

/* Quantized matrix view: rows x cols int8 + one float scale per row. */
typedef struct {
    const float *scale;
    const int8_t *w;
    int rows, cols;
} ut_qmat;

typedef struct {
    const float *attn_norm;
    ut_qmat wq, wk, wv, wo;
    const float *ffn_norm;
    ut_qmat w1, w2;
} ut_layer;

/* Read-only view into a model image. */
typedef struct ut_model {
    int vocab_size, d_model, n_layers, n_heads, n_kv_heads, head_dim, d_ff, ctx_len;
    float norm_eps;
    uint32_t n_params;
    size_t size;
    const uint32_t *alphabet; /* vocab_size code points, index = token id */
    const char *meta;         /* NUL-terminated JSON, points to meta_buf */
    ut_qmat tok_emb, pos_emb;
    ut_layer layers[UT_MAX_LAYERS];
    const float *final_norm;
    /* RAM copy of the meta JSON: the image may be in flash that only allows 32-bit loads
     * (specs/005-nodemcu-port/contracts/runtime-image-access.md). */
    char meta_buf[256];
} ut_model;

/* Optional profiling (specs/002-observability): stages of one forward pass. */
typedef enum {
    UT_PROF_EMBED = 0, /* token + position embedding */
    UT_PROF_NORM,      /* all RMSNorms (attention, FFN, final) */
    UT_PROF_QKV,       /* Q/K/V projections + KV-cache quantization */
    UT_PROF_ATTN,      /* scores, softmax, weighted sum over the cache */
    UT_PROF_WO,        /* output projection + residual */
    UT_PROF_FFN,       /* w1, ReLU, w2 + residual */
    UT_PROF_HEAD,      /* logits (tied embedding) */
    UT_PROF_N
} ut_prof_stage;

/* Monotonic microsecond clock supplied by the platform (wraps at 2^32). */
typedef uint32_t (*ut_clock_us_fn)(void);

/* Session: KV cache, activations and position, all inside the arena. */
typedef struct ut_ctx {
    const ut_model *m;
    int pos;
    int8_t *kq, *vq; /* [n_layers][ctx_len][head_dim] */
    float *ks, *vs;  /* [n_layers][ctx_len] */
    float *x, *h, *q, *att, *tmp, *k, *v, *ff, *logits, *scores;
    int8_t *aq;      /* int8 activation buffer, max(d_model, d_ff) */
    int8_t *qh;      /* int8 per-head query */
    /* Profiling: NULL = off. Only reads the clock; results stay bit-identical. Set after
     * ut_ctx_init (which clears it); prof_us accumulates until ut_prof_reset. */
    ut_clock_us_fn clock_us;
    uint32_t prof_us[UT_PROF_N];
} ut_ctx;

/* Validate and parse a model image. No copy is made; `data` must stay valid. */
ut_status ut_model_open(ut_model *m, const void *data, size_t size);

/* Bytes of arena required for this model. */
size_t ut_arena_size(const ut_model *m);

ut_status ut_ctx_init(ut_ctx *c, const ut_model *m, void *arena, size_t arena_size);
void ut_ctx_reset(ut_ctx *c); /* pos = 0 and feeds <bos> */

/* Feed one token at the current position (incremental prefill); computes logits. */
ut_status ut_feed(ut_ctx *c, int token);
void ut_rewind(ut_ctx *c, int n); /* backspace: pos -= n (never below 1) */

/* Logits for the last fed position (vocab_size floats inside the arena). */
const float *ut_logits(const ut_ctx *c);

void ut_prof_reset(ut_ctx *c);
const char *ut_prof_name(int stage); /* "embed", "norm", ... or "?" */

int ut_argmax(const float *logits, int n);
/* Softmax probabilities of `logits` (temperature 1) into `out`; logits stay unchanged.
 * For observability only; not part of the parity-checked path. */
void ut_softmax_copy(const float *logits, int n, float *out);
/* Temperature sampling with xorshift32; `scratch` needs n floats. */
int ut_sample(const float *logits, int n, float temperature, uint32_t *rng_state, float *scratch);

/* Alphabet mapping. */
int ut_token_from_codepoint(const ut_model *m, uint32_t cp); /* id or UT_TOK_UNK */
uint32_t ut_codepoint_from_token(const ut_model *m, int token); /* 0 for specials */

/* UTF-8 helpers. */
int ut_utf8_encode(uint32_t cp, char out[4]); /* returns bytes written (1..4) */
/* Incremental decoder: feed bytes; returns 1 and sets *cp when a code point completes,
 * 0 when more bytes are needed, -1 on an invalid sequence (state is reset). */
typedef struct {
    uint32_t cp;
    int need;
} ut_utf8_dec;
int ut_utf8_feed(ut_utf8_dec *d, uint8_t byte, uint32_t *cp);

/* CRC-32 (IEEE 802.3), as used by the model file. */
uint32_t ut_crc32(const void *data, size_t n);

#ifdef __cplusplus
}
#endif

#endif /* UTINY_H */
