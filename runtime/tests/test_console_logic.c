/* Host tests of the console state machine with a fake I/O backend (contracts/serial-console.md). */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "utiny.h"
#include "utiny_console.h"

static int failures = 0;
#define CHECK(cond)                                                                  \
    do {                                                                             \
        if (!(cond)) {                                                               \
            fprintf(stderr, "%s:%d: CHECK failed: %s\n", __FILE__, __LINE__, #cond); \
            failures++;                                                              \
        }                                                                            \
    } while (0)

typedef struct {
    const char *in;
    size_t pos, len;
    char out[262144];
    size_t out_len;
    uint32_t t;
} fake_io;

static int f_read(void *u) {
    fake_io *f = u;
    return f->pos < f->len ? (unsigned char)f->in[f->pos++] : -1;
}
static void f_write(void *u, const char *b, size_t n) {
    fake_io *f = u;
    if (f->out_len + n < sizeof f->out) {
        memcpy(f->out + f->out_len, b, n);
        f->out_len += n;
        f->out[f->out_len] = 0;
    }
}
static uint32_t f_millis(void *u) { return ((fake_io *)u)->t += 5; }
static uint32_t f_micros(void *u) { return ((fake_io *)u)->t * 1000u + 123u; }
static void f_sys(void *u, ut_sys_stats *s) {
    (void)u;
    s->heap_free = 1000;
    s->heap_min = 900;
    s->heap_largest = 800;
    s->stack_free = 4242;
    s->cpu_load[0] = 3;
    s->cpu_load[1] = 100;
    s->uptime_ms = 12345;
    s->cpu_mhz = 240;
}
static uint32_t fake_clock_t = 0;
static uint32_t fake_clock(void) { return fake_clock_t += 7; }

static int count(const char *hay, const char *needle) {
    int n = 0;
    for (const char *p = strstr(hay, needle); p; p = strstr(p + 1, needle)) n++;
    return n;
}

/* Greedy answer computed directly with the runtime (independent of the console). */
static void direct_answer(ut_ctx *c, const ut_model *m, const char *q, int max, char *out) {
    ut_ctx_reset(c);
    for (const char *p = q; *p; p++) ut_feed(c, ut_token_from_codepoint(m, (uint8_t)*p));
    ut_feed(c, UT_TOK_SEP);
    size_t o = 0;
    for (int n = 0; n < max; n++) {
        int tok = ut_argmax(ut_logits(c), m->vocab_size);
        if (tok == UT_TOK_EOS) break;
        o += (size_t)ut_utf8_encode(ut_codepoint_from_token(m, tok), out + o);
        if (c->pos >= m->ctx_len || n + 1 >= max) break;
        ut_feed(c, tok);
    }
    out[o] = 0;
    ut_rewind(c, c->pos);
}

static void feed(ut_console *k, fake_io *f, const char *s) {
    f->in = s;
    f->pos = 0;
    f->len = strlen(s);
    f->out_len = 0;
    f->out[0] = 0;
    /* poll until input consumed and generation finished */
    for (int i = 0; i < 10000; i++) {
        ut_console_poll(k);
        if (f->pos >= f->len && k->state != UT_ST_GENERATING) break;
    }
}

/* ---- function output (specs/006-hybrid-chemielehrer, task T025) ---- */

static uint8_t *load(const char *dir, const char *name, size_t *n) {
    char path[512];
    snprintf(path, sizeof path, "%s/%s", dir, name);
    FILE *fp = fopen(path, "rb");
    if (!fp) return NULL;
    fseek(fp, 0, SEEK_END);
    *n = (size_t)ftell(fp);
    fseek(fp, 0, SEEK_SET);
    uint8_t *d = aligned_alloc(16, (*n + 15) & ~(size_t)15);
    if (fread(d, 1, *n, fp) != *n) *n = 0;
    fclose(fp);
    return d;
}

static uint8_t facts_area[0x10000];
static int facts_read(void *u, uint32_t off, void *buf, uint32_t n) {
    (void)u;
    if (off > sizeof facts_area || n > sizeof facts_area - off) return -1;
    memcpy(buf, facts_area + off, n);
    return 0;
}

/* The tiny v2 fixture answers "Ordnungszahl Kupfer?" with <fn>OCu (tiny_v2_golden.json); the
 * answer comes from the chemistry knowledge image (specs/008, models/chemie.utki). */
static void test_fn_console(const char *dir, const char *models) {
    size_t n = 0, nf = 0;
    uint8_t *data = load(dir, "tiny_v2.utny", &n);
    uint8_t *fdata = load(models, "chemie.utki", &nf);
    CHECK(data && fdata && n && nf);
    if (!data || !fdata) return;
    memset(facts_area, 0xFF, sizeof facts_area);
    memcpy(facts_area, fdata, nf);
    static ut_kb facts;
    CHECK(ut_kb_open(&facts, facts_read, NULL, sizeof facts_area) == UT_KB_OK);
    ut_model m;
    CHECK(ut_model_open(&m, data, n) == UT_OK);
    CHECK(m.has_fn == 1 && m.n_special == 6);
    size_t need = ut_arena_size(&m);
    void *arena = aligned_alloc(16, (need + 15) & ~(size_t)15);
    ut_ctx c;
    CHECK(ut_ctx_init(&c, &m, arena, need) == UT_OK);
    static fake_io f;
    memset(&f, 0, sizeof f);
    ut_console_io io = {f_read, f_write, f_millis, NULL, &f, NULL, NULL, NULL, &facts};
    static ut_console k;
    ut_console_init(&k, &c, &m, need, &io, UT_OK);

    /* full answer from the table; the raw function output is not printed by default */
    feed(&k, &f, "Ordnungszahl Kupfer?\r");
    CHECK(strstr(f.out, "\r\nDie Ordnungszahl von Kupfer ist 29.\r\n> ") != NULL);
    CHECK(strstr(f.out, "OCu") == NULL);

    /* prefix is printed as soon as the type letter is generated, before the key is complete */
    feed(&k, &f, "Ordnungszahl Kupfer?");
    f.in = "\r";
    f.pos = 0;
    f.len = 1;
    f.out_len = 0;
    f.out[0] = 0;
    int saw_prefix_only = 0;
    for (int i = 0; i < 100 && (f.pos < f.len || k.state == UT_ST_GENERATING || i == 0); i++) {
        ut_console_poll(&k);
        if (strstr(f.out, "Die Ordnungszahl von ") && !strstr(f.out, "Kupfer")) saw_prefix_only = 1;
    }
    CHECK(saw_prefix_only);
    CHECK(strstr(f.out, "Kupfer ist 29.") != NULL);

    /* /raw an shows the function output after the answer */
    feed(&k, &f, "/raw an\r");
    feed(&k, &f, "Ordnungszahl Kupfer?\r");
    CHECK(strstr(f.out, "29.  [\xE2\x9F\xA8" "fn" "\xE2\x9F\xA9" "OCu]") != NULL);
    feed(&k, &f, "/raw aus\r");

    /* /info shows the knowledge image; the tiny model has no topic meta (not checked) */
    feed(&k, &f, "/info\r");
    CHECK(strstr(f.out, "Wissen: OK v1, Thema chemie (Schema ") != NULL);
    CHECK(strstr(f.out, "Thema nicht gepr\xC3\xBC" "ft") != NULL);

    /* /wissen: overview, legacy letter, view name, reverse view, umlauts in keys, timing */
    feed(&k, &f, "/wissen\r");
    CHECK(strstr(f.out, "\r\nThema chemie, Schema ") != NULL && strstr(f.out, "ordnungszahl (O)"));
    feed(&k, &f, "/wissen O Cu\r");
    CHECK(strstr(f.out, "\r\nDie Ordnungszahl von Kupfer ist 29.\r\n> ") != NULL);
    feed(&k, &f, "/wissen ordnungszahl< 29\r");
    CHECK(strstr(f.out, "\r\nDie Ordnungszahl 29 hat Kupfer.\r\n> ") != NULL);
    feed(&k, &f, "/wissen O Xx\r");
    CHECK(strstr(f.out, "Die Ordnungszahl von \xE2\x80\x93 Das wei\xC3\x9F ich leider nicht.") != NULL);
    feed(&k, &f, "/trace an\r");
    feed(&k, &f, "/wissen O Cu\r");
    CHECK(strstr(f.out, "\r\nwissen: fact ") != NULL && strstr(f.out, " us") != NULL);
    feed(&k, &f, "/trace aus\r");
    CHECK(strstr(f.out, "Format v2") == NULL); /* banner line, not /info */

    /* Ctrl-C after the prefix: nothing more is printed */
    feed(&k, &f, "Ordnungszahl Kupfer?");
    f.in = "\r";
    f.pos = 0;
    f.len = 1;
    f.out_len = 0;
    for (int i = 0; i < 100; i++) {
        ut_console_poll(&k);
        if (strstr(f.out, "Die Ordnungszahl von ")) break;
    }
    f.in = "\x03";
    f.pos = 0;
    f.len = 1;
    ut_console_poll(&k);
    CHECK(strstr(f.out, "[abgebrochen]") != NULL);
    CHECK(strstr(f.out, "Kupfer") == NULL);
    CHECK(k.state != UT_ST_GENERATING);

    /* topic check (specs/008 research R11): a model of another topic makes the image unusable for
     * fact questions, model text keeps working; the same topic is accepted */
    char saved_meta[sizeof m.meta_buf];
    memcpy(saved_meta, m.meta_buf, sizeof saved_meta);
    snprintf(m.meta_buf, sizeof m.meta_buf, "{\"name\": \"x\", \"topic\": \"schach\"}");
    CHECK(ut_kb_open(&facts, facts_read, NULL, sizeof facts_area) == UT_KB_OK);
    f.out_len = 0;
    f.out[0] = 0;
    ut_console_init(&k, &c, &m, need, &io, UT_OK);
    ut_console_banner(&k);
    CHECK(facts.status == UT_KB_WRONG_TOPIC);
    CHECK(strstr(f.out, "Wissen: falsches Thema (Bild chemie, Modell schach)") != NULL);
    feed(&k, &f, "Ordnungszahl Kupfer?\r");
    CHECK(strstr(f.out, "Die Faktentabelle fehlt") != NULL);
    feed(&k, &f, "Hi\r");
    CHECK(strstr(f.out, "Hallo!") != NULL);
    snprintf(m.meta_buf, sizeof m.meta_buf, "{\"name\": \"x\", \"topic\": \"chemie\"}");
    CHECK(ut_kb_open(&facts, facts_read, NULL, sizeof facts_area) == UT_KB_OK);
    ut_console_init(&k, &c, &m, need, &io, UT_OK);
    CHECK(facts.status == UT_KB_OK);
    feed(&k, &f, "/info\r");
    CHECK(strstr(f.out, "Thema chemie (Schema ") != NULL);
    feed(&k, &f, "Ordnungszahl Kupfer?\r");
    CHECK(strstr(f.out, "Kupfer ist 29.") != NULL);
    memcpy(m.meta_buf, saved_meta, sizeof saved_meta);

    /* missing table: model text still works, factual answers say the table is missing */
    io.kb = NULL;
    ut_console_init(&k, &c, &m, need, &io, UT_OK);
    feed(&k, &f, "Ordnungszahl Kupfer?\r");
    CHECK(strstr(f.out, "Die Faktentabelle fehlt") != NULL);
    feed(&k, &f, "Hi\r");
    CHECK(strstr(f.out, "Hallo!") != NULL);
    feed(&k, &f, "/info\r");
    CHECK(strstr(f.out, "Wissen: fehlt") != NULL);
    feed(&k, &f, "/wissen O Cu\r");
    CHECK(strstr(f.out, "Die Faktentabelle fehlt") != NULL);
    free(arena);
    free(data);
    free(fdata);
}

int main(int argc, char **argv) {
    const char *dir = argc > 1 ? argv[1] : "tests/fixtures";
    char path[512];
    snprintf(path, sizeof path, "%s/tiny.utny", dir);
    FILE *fp = fopen(path, "rb");
    if (!fp) {
        fprintf(stderr, "cannot read %s\n", path);
        return 2;
    }
    fseek(fp, 0, SEEK_END);
    size_t n = (size_t)ftell(fp);
    fseek(fp, 0, SEEK_SET);
    uint8_t *data = aligned_alloc(16, (n + 15) & ~(size_t)15);
    if (fread(data, 1, n, fp) != n) return 2;
    fclose(fp);

    ut_model m;
    CHECK(ut_model_open(&m, data, n) == UT_OK);
    size_t need = ut_arena_size(&m);
    void *arena = aligned_alloc(16, (need + 15) & ~(size_t)15);
    ut_ctx c;
    CHECK(ut_ctx_init(&c, &m, arena, need) == UT_OK);
    fake_io f = {0};
    ut_console_io io = {f_read, f_write, f_millis, NULL, &f, NULL, NULL, NULL, NULL};
    static ut_console k;
    ut_console_init(&k, &c, &m, need, &io, UT_OK);
    CHECK(k.max_answer == m.ctx_len - 3); /* default answer cap fits the context */

    ut_console_banner(&k);
    CHECK(strstr(f.out, "UltraTiny v") != NULL);
    CHECK(strstr(f.out, "Format v1") != NULL);
    CHECK(strstr(f.out, "Funk: aus") != NULL);
    CHECK(k.state == UT_ST_READY);

    /* Empty Enter: just a new prompt, nothing generated. */
    feed(&k, &f, "\r");
    CHECK(strcmp(f.out, "\r\n> ") == 0);
    CHECK(c.pos == 1);

    /* Typing feeds the model immediately (incremental prefill). */
    feed(&k, &f, "Hallo");
    CHECK(k.state == UT_ST_TYPING && k.line_len == 5 && c.pos == 6);
    CHECK(strcmp(f.out, "Hallo") == 0);

    /* Backspace rewinds the model position. */
    feed(&k, &f, "\x7f\x08");
    CHECK(k.line_len == 3 && c.pos == 4);

    /* Unknown character: not fed, notice printed once per line. */
    feed(&k, &f, "\xF0\x9F\x98\x80\xF0\x9F\x98\x80");
    CHECK(k.line_len == 3 && c.pos == 4);
    CHECK(strstr(f.out, "unbekannt") != NULL);
    CHECK(strstr(strstr(f.out, "unbekannt") + 1, "unbekannt") == NULL);

    /* Ctrl-C while typing clears the line. */
    feed(&k, &f, "\x03");
    CHECK(k.line_len == 0 && c.pos == 1 && k.state == UT_ST_READY);

    /* Enter starts an answer that finishes on its own (<eos> or /max), back to READY. */
    feed(&k, &f, "/max 20\r");
    CHECK(k.max_answer == 20);
    feed(&k, &f, "Wer bist du?\r\n");
    CHECK(k.state == UT_ST_READY && c.pos == 1);
    CHECK(k.gen_count <= 20);
    CHECK(strstr(f.out, "\r\n> ") != NULL);

    /* /max above what the context can hold is clamped (specs/005-nodemcu-port FR-006). */
    feed(&k, &f, "/max 200\r");
    CHECK(k.max_answer == m.ctx_len - 3);
    CHECK(strstr(f.out, "Grenze des Kontexts") != NULL);

    /* Ctrl-C during generation aborts. */
    f.in = "Wer bist du?\r";
    f.pos = 0;
    f.len = strlen(f.in);
    f.out_len = 0;
    for (int i = 0; i < 20 && f.pos < f.len; i++) ut_console_poll(&k);
    ut_console_poll(&k); /* first generation step */
    if (k.state == UT_ST_GENERATING) {
        feed(&k, &f, "\x03");
        CHECK(strstr(f.out, "[abgebrochen]") != NULL);
    }
    CHECK(k.state == UT_ST_READY && c.pos == 1);

    /* Question too long for the context: rejected with a message. */
    char longq[512];
    int maxq = m.ctx_len - 2 - UT_ANSWER_RESERVE;
    memset(longq, 'a', (size_t)maxq + 5);
    longq[maxq + 5] = 0;
    feed(&k, &f, longq);
    CHECK(k.line_len == maxq);
    CHECK(strstr(f.out, "zu lang") != NULL);
    feed(&k, &f, "\x03");

    /* Commands. */
    feed(&k, &f, "/hilfe\r");
    CHECK(strstr(f.out, "/modus") != NULL);
    feed(&k, &f, "/modus zufall 7 0.5\r");
    CHECK(k.sampling == 1 && k.seed == 7);
    feed(&k, &f, "/modus gierig\r");
    CHECK(k.sampling == 0);
    feed(&k, &f, "/info\r");
    CHECK(strstr(f.out, "Arena") != NULL);
    feed(&k, &f, "/quatsch\r");
    CHECK(strstr(f.out, "Unbekannter Befehl") != NULL);

    /* Greedy answers are deterministic. */
    feed(&k, &f, "Wer bist du?\r");
    char first[4096];
    strcpy(first, f.out);
    feed(&k, &f, "Wer bist du?\r");
    CHECK(strcmp(first, f.out) == 0);

    /* HALT_ERROR: invalid model, only /hilfe and /info. */
    static ut_console bad;
    ut_console_init(&bad, NULL, NULL, 0, &io, UT_ERR_PAYLOAD_CRC);
    f.out_len = 0;
    ut_console_banner(&bad);
    CHECK(strstr(f.out, "FEHLER: Modell ung") != NULL);
    CHECK(bad.state == UT_ST_HALT_ERROR);
    feed(&bad, &f, "Hallo\r");
    CHECK(bad.state == UT_ST_HALT_ERROR);
    feed(&bad, &f, "/info\r");
    CHECK(strstr(f.out, "Modellfehler 4") != NULL);

    /* ---- Observability (specs/002-observability) ---- */

    /* Profiling only reads the clock: logits stay bit-identical (constitution III). */
    {
        void *arena2 = aligned_alloc(16, (need + 15) & ~(size_t)15);
        ut_ctx c2;
        CHECK(ut_ctx_init(&c2, &m, arena2, need) == UT_OK);
        c2.clock_us = fake_clock;
        ut_ctx_reset(&c);
        const char *q = "Wer bist du?";
        int ok = 1;
        for (const char *p = q; *p; p++) {
            int t = ut_token_from_codepoint(&m, (uint8_t)*p);
            ut_feed(&c, t);
            ut_feed(&c2, t);
            ok &= memcmp(ut_logits(&c), ut_logits(&c2), sizeof(float) * (size_t)m.vocab_size) == 0;
        }
        CHECK(ok);
        uint32_t tot = 0;
        for (int i = 0; i < UT_PROF_N; i++) tot += c2.prof_us[i];
        CHECK(tot > 0 && c2.prof_us[UT_PROF_FFN] > 0 && c2.prof_us[UT_PROF_HEAD] > 0);
        ut_prof_reset(&c2);
        CHECK(c2.prof_us[UT_PROF_ATTN] == 0);
        CHECK(strcmp(ut_prof_name(UT_PROF_QKV), "qkv") == 0 && strcmp(ut_prof_name(99), "?") == 0);
        float pr[UT_MAX_VOCAB], sum = 0.0f;
        ut_softmax_copy(ut_logits(&c), m.vocab_size, pr);
        for (int i = 0; i < m.vocab_size; i++) sum += pr[i];
        CHECK(sum > 0.999f && sum < 1.001f);
        CHECK(ut_argmax(pr, m.vocab_size) == ut_argmax(ut_logits(&c), m.vocab_size));
        free(arena2);
        ut_rewind(&c, c.pos);
    }

    /* Trace off: the answer output is exactly "\r\n" + answer + "\r\n> " (unchanged). */
    static ut_console o;
    ut_console_io io2 = {f_read, f_write, f_millis, NULL, &f, f_micros, f_sys, "Testboard", NULL};
    ut_console_init(&o, &c, &m, need, &io2, UT_OK);
    o.arena_cap = 96 * 1024;
    c.clock_us = fake_clock;
    /* /stats before the first answer (spec US1 acceptance 1). */
    feed(&o, &f, "/stats\r");
    CHECK(strstr(f.out, "Heap frei 1000 B") != NULL);
    CHECK(strstr(f.out, "Letzte Antwort: noch keine") != NULL);
    CHECK(strstr(f.out, "Profil") == NULL && strstr(f.out, "ms pro Zeichen") == NULL);
    const char *q = "Wer bist du?";
    char expect_ans[1024], expect[1100];
    direct_answer(&c, &m, q, UT_MAX_ANSWER, expect_ans);
    snprintf(expect, sizeof expect, "%s\r\n%s\r\n> ", q, expect_ans);
    feed(&o, &f, "Wer bist du?\r");
    CHECK(strcmp(f.out, expect) == 0);
    char off_out[4096];
    strcpy(off_out, f.out);
    CHECK(o.trace == UT_TRACE_OFF && o.has_last && o.last.n == (int)strlen(expect_ans));

    /* /stats: system values, last answer timings, stage profile. */
    feed(&o, &f, "/stats\r");
    CHECK(strstr(f.out, "Heap frei 1000 B, Minimum 900 B") != NULL);
    CHECK(strstr(f.out, "Stack frei (Inferenz-Task) 4242 B") != NULL);
    CHECK(strstr(f.out, "Kern 0 3 %, Kern 1 100 %") != NULL);
    CHECK(strstr(f.out, "Arena ") != NULL && strstr(f.out, "/ 98304 B") != NULL);
    CHECK(strstr(f.out, "KV-Cache: Position 1 /") != NULL);
    CHECK(strstr(f.out, "Takt 240 MHz") != NULL);
    CHECK(strstr(f.out, "erstes Zeichen nach") != NULL && strstr(f.out, "ms pro Zeichen") != NULL);
    CHECK(strstr(f.out, "Profil (Rechenzeit") != NULL && strstr(f.out, "ffn") != NULL);
    CHECK(strstr(f.out, "@ut ") == NULL); /* JSON only in json mode */

    /* /trace an: same answer bytes first, then the per-character table and summary. */
    feed(&o, &f, "/trace an\r");
    CHECK(strstr(f.out, "Trace: an") != NULL && o.trace == UT_TRACE_ON);
    feed(&o, &f, "Wer bist du?\r");
    CHECK(strncmp(f.out, off_out, strlen(off_out) - 4) == 0); /* minus "\r\n> " */
    CHECK(strstr(f.out, "--- Trace: ") != NULL && strstr(f.out, "Ende: ") != NULL);
    CHECK(strstr(f.out, "Entropie") != NULL && strstr(f.out, "Kontext ") != NULL);
    CHECK(count(f.out, "\r\n  ") + count(f.out, "\r\n ") >= o.n_steps);
    /* chars + the stop step when the model ended with <eos> */
    CHECK(o.n_steps == o.last.n + (strcmp(o.last.end, "eos") == 0));

    /* /trace json: one token event per step + answer event; /stats adds a sys event. */
    feed(&o, &f, "/trace json\r");
    feed(&o, &f, "Wer bist du?\r");
    CHECK(strncmp(f.out, off_out, strlen(off_out) - 4) == 0);
    CHECK(count(f.out, "@ut {\"type\":\"token\"") == o.n_steps);
    CHECK(count(f.out, "@ut {\"type\":\"answer\"") == 1);
    CHECK(strstr(f.out, "\"end\":\"") != NULL);
    CHECK((strstr(f.out, "\"stop\":true") != NULL) == (strcmp(o.last.end, "eos") == 0));
    CHECK(strstr(f.out, "\"prof_us\":{\"embed\":") != NULL);
    feed(&o, &f, "/stats\r");
    CHECK(strstr(f.out, "@ut {\"type\":\"sys\",\"model_ok\":true,\"heap_free\":1000") != NULL);
    CHECK(strstr(f.out, "\"cpu_load\":[3,100]") != NULL);

    /* Ctrl-C with trace on: trace covers the characters produced so far. */
    feed(&o, &f, "/trace an\r");
    f.in = "Wer bist du?\r";
    f.pos = 0;
    f.len = strlen(f.in);
    for (int i = 0; i < 20 && f.pos < f.len; i++) ut_console_poll(&o);
    ut_console_poll(&o);
    ut_console_poll(&o);
    if (o.state == UT_ST_GENERATING) {
        int produced = o.gen_count;
        feed(&o, &f, "\x03");
        CHECK(strstr(f.out, "[abgebrochen]") != NULL && strstr(f.out, "Ende: abort") != NULL);
        CHECK(o.last.n == produced && o.n_steps == produced);
    }
    CHECK(o.state == UT_ST_READY && c.pos == 1);

    /* /trace aus: output byte-identical to before again. */
    feed(&o, &f, "/trace aus\r");
    feed(&o, &f, "/trace\r");
    CHECK(strstr(f.out, "Trace: aus") != NULL);
    feed(&o, &f, "/trace quatsch\r");
    CHECK(strstr(f.out, "erwartet aus, an oder json") != NULL);
    feed(&o, &f, "Wer bist du?\r");
    CHECK(strcmp(f.out, off_out) == 0);
    c.clock_us = NULL;

    /* HALT_ERROR: /stats still reports system values. */
    static ut_console bad2;
    ut_console_init(&bad2, NULL, NULL, 0, &io2, UT_ERR_PAYLOAD_CRC);
    feed(&bad2, &f, "/stats\r");
    CHECK(strstr(f.out, "Heap frei 1000 B") != NULL && strstr(f.out, "Modellfehler 4") != NULL);
    CHECK(strstr(f.out, "Letzte Antwort") == NULL);

    free(arena);
    free(data);
    test_fn_console(dir, argc > 2 ? argv[2] : "../models");
    if (failures) {
        fprintf(stderr, "%d check(s) failed\n", failures);
        return 1;
    }
    printf("test_console_logic: all checks passed\n");
    return 0;
}
