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
    char out[16384];
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
    ut_console_io io = {f_read, f_write, f_millis, NULL, &f};
    static ut_console k;
    ut_console_init(&k, &c, &m, need, &io, UT_OK);

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

    /* Ctrl-C during generation aborts. */
    feed(&k, &f, "/max 200\r");
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

    free(arena);
    free(data);
    if (failures) {
        fprintf(stderr, "%d check(s) failed\n", failures);
        return 1;
    }
    printf("test_console_logic: all checks passed\n");
    return 0;
}
