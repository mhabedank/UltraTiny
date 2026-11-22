/*
 * utiny-host: run the portable runtime on a PC (contracts/runtime-api.md).
 *
 *   utiny-host --model m.utny --prompt "Frage" [--greedy | --sample SEED TEMP] [--max N]
 *   utiny-host --model m.utny --golden golden.json   # bit-exact parity check, exit 0 on match
 *   utiny-host --model m.utny --info                 # header fields + arena size
 *   utiny-host --model m.utny --console              # serial console on stdin/stdout (POSIX)
 */
#define _POSIX_C_SOURCE 200809L
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include <poll.h>
#include <time.h>
#include <unistd.h>

#include "json.h"
#include "utiny.h"
#include "utiny_console.h"

static int feed_prompt(ut_ctx *c, const ut_model *m, const char *text) {
    ut_ctx_reset(c);
    ut_utf8_dec dec = {0};
    for (const unsigned char *p = (const unsigned char *)text; *p; p++) {
        uint32_t cp;
        if (ut_utf8_feed(&dec, *p, &cp) == 1) {
            if (ut_feed(c, ut_token_from_codepoint(m, cp)) != UT_OK) return -1;
        }
    }
    return ut_feed(c, UT_TOK_SEP) == UT_OK ? 0 : -1;
}

static int run_prompt(ut_ctx *c, const ut_model *m, const char *text, int sampling,
                      uint32_t seed, float temp, int max) {
    if (feed_prompt(c, m, text) != 0) {
        fprintf(stderr, "prompt too long\n");
        return 1;
    }
    float scratch[UT_MAX_VOCAB];
    uint32_t rng = seed;
    for (int n = 0; n < max; n++) {
        const float *lg = ut_logits(c);
        int tok = sampling ? ut_sample(lg, m->vocab_size, temp, &rng, scratch)
                           : ut_argmax(lg, m->vocab_size);
        if (tok == UT_TOK_EOS) break;
        char b[4];
        uint32_t cp = ut_codepoint_from_token(m, tok);
        if (cp) fwrite(b, 1, (size_t)ut_utf8_encode(cp, b), stdout);
        if (c->pos >= m->ctx_len || n + 1 >= max) break;
        ut_feed(c, tok);
    }
    fputc('\n', stdout);
    return 0;
}

/* ---- --console: the device console logic on stdin/stdout (specs/002-observability) ---- */

static int stdin_eof = 0;

static uint64_t mono_us(void) {
    struct timespec ts;
    clock_gettime(CLOCK_MONOTONIC, &ts);
    return (uint64_t)ts.tv_sec * 1000000u + (uint64_t)ts.tv_nsec / 1000u;
}
static uint32_t h_clock_us(void) { return (uint32_t)mono_us(); }
static uint32_t h_micros(void *u) {
    (void)u;
    return (uint32_t)mono_us();
}
static uint32_t h_millis(void *u) {
    (void)u;
    return (uint32_t)(mono_us() / 1000u);
}
static int h_read(void *u) {
    (void)u;
    struct pollfd p = {0, POLLIN, 0};
    if (stdin_eof || poll(&p, 1, 0) <= 0) return -1;
    unsigned char b;
    ssize_t n = read(0, &b, 1);
    if (n <= 0) {
        stdin_eof = 1;
        return -1;
    }
    return b;
}
static void h_write(void *u, const char *b, size_t n) {
    (void)u;
    fwrite(b, 1, n, stdout);
    fflush(stdout);
}
static void h_sys(void *u, ut_sys_stats *s) {
    (void)u;
    static uint64_t t0 = 0;
    if (!t0) t0 = mono_us();
    s->uptime_ms = (int32_t)((mono_us() - t0) / 1000u);
}

static int run_console(ut_ctx *c, const ut_model *m, size_t arena_size) {
    static ut_console k;
    ut_console_io io = {h_read, h_write, h_millis, NULL, NULL, h_micros, h_sys, "Host (utiny-host)"};
    c->clock_us = h_clock_us;
    h_sys(NULL, &(ut_sys_stats){0});
    ut_console_init(&k, c, m, arena_size, &io, UT_OK);
    ut_console_banner(&k);
    for (;;) {
        ut_console_poll(&k);
        if (k.state == UT_ST_GENERATING) continue;
        if (stdin_eof) break;
        struct pollfd p = {0, POLLIN, 0};
        poll(&p, 1, 50);
    }
    fputs("\n", stdout);
    return 0;
}

static int u32_of(const jval *v) { return (int)v->i; }

/* Compares every logit bit pattern and every generated token against the reference. */
static int run_golden(ut_ctx *c, const ut_model *m, const char *path) {
    char *text = read_file(path, NULL);
    if (!text) {
        fprintf(stderr, "cannot read %s\n", path);
        return 2;
    }
    jval *g = json_parse(text);
    free(text);
    const jval *cases = json_get(g, "cases");
    if (!g || !cases || cases->type != J_ARR) {
        fprintf(stderr, "invalid golden file\n");
        json_free(g);
        return 2;
    }
    int fails = 0;
    size_t steps = 0;
    for (size_t ci = 0; ci < cases->n; ci++) {
        const jval *cs = cases->items[ci];
        const jval *pt = json_get(cs, "prompt_tokens"), *toks = json_get(cs, "tokens");
        const jval *lb = json_get(cs, "logits_bits");
        ut_ctx_reset(c); /* feeds <bos> = prompt_tokens[0] */
        int ok = 1;
        for (size_t i = 1; i < pt->n && ok; i++) ok = ut_feed(c, u32_of(pt->items[i])) == UT_OK;
        for (size_t s = 0; s < toks->n && ok; s++) {
            const float *lg = ut_logits(c);
            const jval *row = lb->items[s];
            for (int v = 0; v < m->vocab_size; v++) {
                uint32_t bits;
                memcpy(&bits, &lg[v], 4);
                if (bits != (uint32_t)row->items[v]->i) {
                    float want;
                    uint32_t wb = (uint32_t)row->items[v]->i;
                    memcpy(&want, &wb, 4);
                    fprintf(stderr, "case %zu step %zu logit %d: got %.9g want %.9g\n", ci, s,
                            v, (double)lg[v], (double)want);
                    ok = 0;
                    break;
                }
            }
            int tok = ut_argmax(lg, m->vocab_size);
            if (ok && tok != u32_of(toks->items[s])) {
                fprintf(stderr, "case %zu step %zu: token %d != %d\n", ci, s, tok,
                        u32_of(toks->items[s]));
                ok = 0;
            }
            steps++;
            if (ok && s + 1 < toks->n) ok = ut_feed(c, tok) == UT_OK;
        }
        if (!ok) fails++;
    }
    printf("golden: %zu cases, %zu steps, %d failed\n", cases->n, steps, fails);
    json_free(g);
    return fails ? 1 : 0;
}

int main(int argc, char **argv) {
    const char *model_path = NULL, *prompt = NULL, *golden = NULL;
    int sampling = 0, max = 200, info = 0, console = 0;
    uint32_t seed = 1;
    float temp = 0.8f;
    for (int i = 1; i < argc; i++) {
        if (!strcmp(argv[i], "--model") && i + 1 < argc) model_path = argv[++i];
        else if (!strcmp(argv[i], "--prompt") && i + 1 < argc) prompt = argv[++i];
        else if (!strcmp(argv[i], "--golden") && i + 1 < argc) golden = argv[++i];
        else if (!strcmp(argv[i], "--max") && i + 1 < argc) max = atoi(argv[++i]);
        else if (!strcmp(argv[i], "--greedy")) sampling = 0;
        else if (!strcmp(argv[i], "--info")) info = 1;
        else if (!strcmp(argv[i], "--console")) console = 1;
        else if (!strcmp(argv[i], "--sample") && i + 2 < argc) {
            sampling = 1;
            seed = (uint32_t)strtoul(argv[++i], NULL, 10);
            temp = (float)atof(argv[++i]);
        } else {
            fprintf(stderr, "usage: %s --model FILE [--prompt TEXT | --golden FILE | --info | --console] "
                            "[--greedy | --sample SEED TEMP] [--max N]\n", argv[0]);
            return 2;
        }
    }
    if (!model_path) {
        fprintf(stderr, "--model is required\n");
        return 2;
    }
    size_t size;
    char *data = read_file(model_path, &size);
    if (!data) {
        fprintf(stderr, "cannot read %s\n", model_path);
        return 2;
    }
    ut_model m;
    ut_status st = ut_model_open(&m, data, size);
    if (st != UT_OK) {
        fprintf(stderr, "model invalid (%d: %s)\n", (int)st, ut_status_str(st));
        free(data);
        return 3;
    }
    size_t arena_size = ut_arena_size(&m);
    void *arena = aligned_alloc(16, (arena_size + 15) & ~(size_t)15);
    ut_ctx c;
    if (!arena || ut_ctx_init(&c, &m, arena, arena_size) != UT_OK) {
        fprintf(stderr, "arena init failed\n");
        return 3;
    }
    int rc = 0;
    if (info) {
        printf("{\"vocab\": %d, \"d_model\": %d, \"n_layers\": %d, \"n_heads\": %d, "
               "\"d_ff\": %d, \"ctx_len\": %d, \"n_params\": %u, \"model_bytes\": %zu, "
               "\"arena_bytes\": %zu, \"meta\": %s}\n",
               m.vocab_size, m.d_model, m.n_layers, m.n_heads, m.d_ff, m.ctx_len, m.n_params,
               m.size, arena_size, m.meta);
    } else if (console) {
        rc = run_console(&c, &m, arena_size);
    } else if (golden) {
        rc = run_golden(&c, &m, golden);
    } else if (prompt) {
        rc = run_prompt(&c, &m, prompt, sampling, seed, temp, max);
    } else {
        fprintf(stderr, "nothing to do (use --prompt, --golden or --info)\n");
        rc = 2;
    }
    free(arena);
    free(data);
    return rc;
}
