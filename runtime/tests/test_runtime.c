/* Host unit tests for the portable runtime (loader validation, KV/context, math, UTF-8). */
#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "../src/mathx.h"
#include "json.h"
#include "utiny.h"

static int failures = 0;
#define CHECK(cond)                                                                    \
    do {                                                                               \
        if (!(cond)) {                                                                 \
            fprintf(stderr, "%s:%d: CHECK failed: %s\n", __FILE__, __LINE__, #cond);   \
            failures++;                                                                \
        }                                                                              \
    } while (0)

static void put32(uint8_t *p, uint32_t v) {
    p[0] = (uint8_t)v;
    p[1] = (uint8_t)(v >> 8);
    p[2] = (uint8_t)(v >> 16);
    p[3] = (uint8_t)(v >> 24);
}
static void fix_header_crc(uint8_t *b) { put32(b + 60, ut_crc32(b, 60)); }

static uint8_t *dup_aligned(const char *src, size_t n) {
    uint8_t *b = aligned_alloc(16, (n + 15) & ~(size_t)15);
    memcpy(b, src, n);
    return b;
}

static ut_status open_copy(const char *data, size_t n, void (*mutate)(uint8_t *, size_t *),
                           size_t *n_out) {
    uint8_t *b = dup_aligned(data, n);
    size_t size = n;
    if (mutate) mutate(b, &size);
    ut_model m;
    ut_status st = ut_model_open(&m, b, size);
    if (n_out) *n_out = size;
    free(b);
    return st;
}

static void m_magic(uint8_t *b, size_t *n) { (void)n; b[0] = 'X'; }
static void m_version(uint8_t *b, size_t *n) { (void)n; b[4] = 2; }
static void m_hcrc(uint8_t *b, size_t *n) { (void)n; b[61] ^= 0x55; }
static void m_payload(uint8_t *b, size_t *n) { b[*n - 5] ^= 0x01; }
static void m_trunc(uint8_t *b, size_t *n) { (void)b; *n -= 100; }
static void m_kvheads(uint8_t *b, size_t *n) { (void)n; b[16] = 2; fix_header_crc(b); }
static void m_heads(uint8_t *b, size_t *n) { (void)n; b[14] = 3; fix_header_crc(b); }
static void m_tiny(uint8_t *b, size_t *n) { (void)b; *n = 40; }

static void test_loader(const char *data, size_t n) {
    ut_model m;
    uint8_t *b = dup_aligned(data, n);
    CHECK(ut_model_open(&m, b, n) == UT_OK);
    /* A partition larger than the file is fine (flash partition is 2 MB). */
    uint8_t *big = aligned_alloc(16, n + 4096);
    memcpy(big, data, n);
    memset(big + n, 0xFF, 4096);
    CHECK(ut_model_open(&m, big, n + 4096) == UT_OK);
    free(big);
    free(b);
    CHECK(open_copy(data, n, m_magic, NULL) == UT_ERR_MAGIC);
    CHECK(open_copy(data, n, m_version, NULL) == UT_ERR_VERSION);
    CHECK(open_copy(data, n, m_hcrc, NULL) == UT_ERR_HEADER_CRC);
    CHECK(open_copy(data, n, m_payload, NULL) == UT_ERR_PAYLOAD_CRC);
    CHECK(open_copy(data, n, m_trunc, NULL) == UT_ERR_SIZE);
    CHECK(open_copy(data, n, m_tiny, NULL) == UT_ERR_SIZE);
    CHECK(open_copy(data, n, m_kvheads, NULL) == UT_ERR_DIMS);
    CHECK(open_copy(data, n, m_heads, NULL) == UT_ERR_DIMS);
    for (int s = 0; s <= UT_ERR_TOKEN; s++) CHECK(strlen(ut_status_str((ut_status)s)) > 0);
}

static void test_context(const char *data, size_t n) {
    uint8_t *b = dup_aligned(data, n);
    ut_model m;
    CHECK(ut_model_open(&m, b, n) == UT_OK);
    size_t need = ut_arena_size(&m);
    void *arena = aligned_alloc(16, (need + 15) & ~(size_t)15);
    ut_ctx c;
    CHECK(ut_ctx_init(&c, &m, arena, need - 16) == UT_ERR_ARENA);
    CHECK(ut_ctx_init(&c, &m, (char *)arena + 4, need) == UT_ERR_ARENA); /* misaligned */
    CHECK(ut_ctx_init(&c, &m, arena, need) == UT_OK);
    CHECK(c.pos == 1); /* <bos> fed */
    CHECK(ut_feed(&c, m.vocab_size) == UT_ERR_TOKEN);
    CHECK(ut_feed(&c, -1) == UT_ERR_TOKEN);

    /* Rewind + re-feed reproduces identical logits (backspace semantics). */
    int a = ut_token_from_codepoint(&m, 'a'), z = ut_token_from_codepoint(&m, 'z');
    CHECK(a > UT_TOK_UNK && z > UT_TOK_UNK);
    CHECK(ut_feed(&c, a) == UT_OK);
    float ref[UT_MAX_VOCAB];
    memcpy(ref, ut_logits(&c), sizeof(float) * (size_t)m.vocab_size);
    CHECK(ut_feed(&c, z) == UT_OK);
    ut_rewind(&c, 2);
    CHECK(c.pos == 1);
    CHECK(ut_feed(&c, a) == UT_OK);
    CHECK(memcmp(ref, ut_logits(&c), sizeof(float) * (size_t)m.vocab_size) == 0);
    ut_rewind(&c, 1000);
    CHECK(c.pos == 1);

    /* Context full is reported, never overrun. */
    int st = UT_OK;
    while (st == UT_OK) st = ut_feed(&c, a);
    CHECK(st == UT_ERR_CONTEXT_FULL);
    CHECK(c.pos == m.ctx_len);
    free(arena);
    free(b);
}

static void test_alphabet(const char *data, size_t n) {
    uint8_t *b = dup_aligned(data, n);
    ut_model m;
    CHECK(ut_model_open(&m, b, n) == UT_OK);
    const uint32_t umlauts[] = {0xE4, 0xF6, 0xFC, 0xC4, 0xD6, 0xDC, 0xDF};
    for (size_t i = 0; i < sizeof umlauts / sizeof umlauts[0]; i++) {
        int t = ut_token_from_codepoint(&m, umlauts[i]);
        CHECK(t > UT_TOK_UNK);
        CHECK(ut_codepoint_from_token(&m, t) == umlauts[i]);
    }
    CHECK(ut_token_from_codepoint(&m, 0x1F600) == UT_TOK_UNK); /* emoji */
    CHECK(ut_codepoint_from_token(&m, UT_TOK_EOS) == 0);

    /* UTF-8 round trip incl. 2-, 3- and 4-byte sequences */
    const uint32_t cps[] = {'A', 0xDF, 0x20AC, 0x1F600};
    for (size_t i = 0; i < 4; i++) {
        char buf[4];
        int len = ut_utf8_encode(cps[i], buf);
        ut_utf8_dec d = {0};
        uint32_t got = 0;
        int r = 0;
        for (int j = 0; j < len; j++) r = ut_utf8_feed(&d, (uint8_t)buf[j], &got);
        CHECK(r == 1 && got == cps[i]);
    }
    ut_utf8_dec d = {0};
    uint32_t cp;
    CHECK(ut_utf8_feed(&d, 0xC3, &cp) == 0);
    CHECK(ut_utf8_feed(&d, 'a', &cp) == -1); /* invalid continuation */
    free(b);
}

static void test_math(void) {
    for (float x = -79.0f; x <= 0.0f; x += 0.37f) {
        float e = ut_expf(x), r = (float)exp((double)x);
        CHECK(fabsf(e - r) <= 2e-6f * r + 1e-37f);
    }
    CHECK(ut_expf(-100.0f) == 0.0f);
    CHECK(ut_expf(0.0f) == 1.0f);
    CHECK(ut_round_half_away(2.5f) == 3.0f);
    CHECK(ut_round_half_away(-2.5f) == -3.0f);
    CHECK(ut_round_half_away(0.49f) == 0.0f);
    int8_t q[4];
    const float zeros[4] = {0};
    CHECK(ut_quantize(zeros, 4, q) == 1.0f && q[0] == 0);
    const float v[4] = {1.0f, -2.0f, 0.5f, 2.0f};
    float s = ut_quantize(v, 4, q);
    CHECK(q[1] == -127 && q[3] == 127 && q[0] == 64 && q[2] == 32);
    CHECK(fabsf(s - 2.0f / 127.0f) < 1e-9f);
}

static void test_golden(const char *data, size_t n, const char *golden_path) {
    char *text = read_file(golden_path, NULL);
    CHECK(text != NULL);
    if (!text) return;
    jval *g = json_parse(text);
    free(text);
    const jval *cases = json_get(g, "cases");
    CHECK(cases && cases->n > 0);
    uint8_t *b = dup_aligned(data, n);
    ut_model m;
    CHECK(ut_model_open(&m, b, n) == UT_OK);
    size_t need = ut_arena_size(&m);
    void *arena = aligned_alloc(16, (need + 15) & ~(size_t)15);
    ut_ctx c;
    CHECK(ut_ctx_init(&c, &m, arena, need) == UT_OK);
    for (size_t ci = 0; cases && ci < cases->n; ci++) {
        const jval *pt = json_get(cases->items[ci], "prompt_tokens");
        const jval *toks = json_get(cases->items[ci], "tokens");
        ut_ctx_reset(&c);
        for (size_t i = 1; i < pt->n; i++) ut_feed(&c, (int)pt->items[i]->i);
        for (size_t s = 0; s < toks->n; s++) {
            int tok = ut_argmax(ut_logits(&c), m.vocab_size);
            CHECK(tok == (int)toks->items[s]->i);
            if (s + 1 < toks->n) ut_feed(&c, tok);
        }
    }
    json_free(g);
    free(arena);
    free(b);
}

int main(int argc, char **argv) {
    const char *dir = argc > 1 ? argv[1] : "tests/fixtures";
    char path[512];
    snprintf(path, sizeof path, "%s/tiny.utny", dir);
    size_t n;
    char *data = read_file(path, &n);
    if (!data) {
        fprintf(stderr, "cannot read %s\n", path);
        return 2;
    }
    test_loader(data, n);
    test_context(data, n);
    test_alphabet(data, n);
    test_math();
    snprintf(path, sizeof path, "%s/tiny_golden.json", dir);
    test_golden(data, n, path);
    free(data);
    if (failures) {
        fprintf(stderr, "%d check(s) failed\n", failures);
        return 1;
    }
    printf("test_runtime: all checks passed\n");
    return 0;
}
