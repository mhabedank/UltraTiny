/* Host tests for the knowledge engine (specs/008-wissens-compiler, tasks T019/T030).
 *
 *   test_knowledge IMAGE.utki CASES.tsv
 *
 * Expected bytes come from the Python reference (ut knowledge cases), so a pass means
 * knowledge.c and knowledge/image.py render identically. Also checks status handling (erased,
 * corrupt, wrong topic), the console's function-output path and the overview. */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "json.h"
#include "utiny.h"
#include "utiny_knowledge.h"

static int failures = 0;
#define CHECK(cond)                                                                    \
    do {                                                                               \
        if (!(cond)) {                                                                 \
            fprintf(stderr, "%s:%d: CHECK failed: %s\n", __FILE__, __LINE__, #cond);   \
            failures++;                                                                \
        }                                                                              \
    } while (0)

#define AREA 0x10000u
static uint8_t area[AREA];

static int mem_read(void *u, uint32_t off, void *buf, uint32_t n) {
    (void)u;
    /* Like ESP.flashRead: offset, length and buffer must be word aligned. */
    if (((off | n) & 3u) != 0 || ((uintptr_t)buf & 3u) != 0) __builtin_trap();
    if (off > AREA || n > AREA - off) return -1;
    memcpy(buf, area + off, n);
    return 0;
}

static char out[1024];
static size_t out_n;
static void cap(void *u, const char *s, size_t n) {
    (void)u;
    if (out_n + n < sizeof out) {
        memcpy(out + out_n, s, n);
        out_n += n;
    }
}

static const char *const OUTCOME[] = {"unknown", "fact", "na", "missing"};

/* The console's fn path: prefix on the letter, ut_kb_finish at the end. */
static ut_kb_outcome fn_answer(ut_kb *kb, char letter, const char *key) {
    out_n = 0;
    ut_kb_view v;
    int has = ut_kb_view_by_letter(kb, letter, &v);
    int p = has ? ut_kb_prefix(kb, &v, cap, NULL) : 0;
    ut_kb_outcome o = ut_kb_finish(kb, has ? &v : NULL, p, key, strlen(key), cap, NULL);
    out[out_n] = 0;
    return o;
}

static ut_kb_outcome query(ut_kb *kb, const char *q) {
    out_n = 0;
    ut_kb_outcome o = ut_kb_query(kb, q, strlen(q), cap, NULL);
    out[out_n] = 0;
    return o;
}

int main(int argc, char **argv) {
    if (argc < 3) {
        fprintf(stderr, "usage: %s IMAGE CASES\n", argv[0]);
        return 2;
    }
    size_t n = 0;
    char *data = read_file(argv[1], &n);
    if (!data || n > AREA) {
        fprintf(stderr, "cannot read %s\n", argv[1]);
        return 2;
    }
    ut_kb kb;

    /* erased area: MISSING; every answer is the missing text */
    memset(area, 0xFF, AREA);
    CHECK(ut_kb_open(&kb, mem_read, NULL, AREA) == UT_KB_MISSING);
    CHECK(query(&kb, "X y") == UT_KB_MISSING_OUT && !strcmp(out, UT_KB_TXT_MISSING));
    CHECK(fn_answer(&kb, 'O', "Cu") == UT_KB_MISSING_OUT && !strcmp(out, UT_KB_TXT_MISSING));

    /* corrupt payload byte and corrupt header byte */
    memcpy(area, data, n);
    area[n - 6] ^= 0x5A;
    CHECK(ut_kb_open(&kb, mem_read, NULL, AREA) == UT_KB_CORRUPT);
    memcpy(area, data, n);
    area[25] ^= 1;
    CHECK(ut_kb_open(&kb, mem_read, NULL, AREA) == UT_KB_CORRUPT);

    /* the real image */
    memset(area, 0xFF, AREA);
    memcpy(area, data, n);
    CHECK(ut_kb_open(&kb, mem_read, NULL, AREA) == UT_KB_OK);
    CHECK(kb.topic[0] != 0 && kb.n_answerable > 0);

    out_n = 0;
    ut_kb_overview(&kb, cap, NULL);
    out[out_n] = 0;
    CHECK(strstr(out, "Thema ") == out && strstr(out, "Ansichten:") != NULL);

    /* golden query cases */
    char *cases = read_file(argv[2], NULL);
    CHECK(cases != NULL);
    int n_cases = 0, n_fn = 0;
    char *save = NULL;
    char *line = cases ? strtok_r(cases, "\n", &save) : NULL; /* header */
    for (line = line ? strtok_r(NULL, "\n", &save) : NULL; line; line = strtok_r(NULL, "\n", &save)) {
        char *f[4] = {0};
        char *p = line;
        for (int i = 0; i < 4 && p; i++) {
            f[i] = p;
            char *t = i < 3 ? strchr(p, '\t') : NULL;
            if (t) *t = 0;
            p = t ? t + 1 : NULL;
        }
        if (!f[3]) continue;
        char q[256];
        snprintf(q, sizeof q, "%s %s", f[0], f[1]);
        ut_kb_outcome o = query(&kb, q);
        if (strcmp(out, f[3]) != 0 || strcmp(OUTCOME[o], f[2]) != 0) {
            fprintf(stderr, "case %d (%s): got %s \"%s\" want %s \"%s\"\n", n_cases + 1, q,
                    OUTCOME[o], out, f[2], f[3]);
            failures++;
        }
        /* same answer through the function-output path for legacy letters */
        if (strlen(f[0]) == 1 && strlen(f[1]) <= UT_KB_KEY_MAX) {
            ut_kb_outcome o2 = fn_answer(&kb, f[0][0], f[1]);
            CHECK(o2 == o && strcmp(out, f[3]) == 0);
            n_fn++;
        }
        n_cases++;
    }
    CHECK(n_cases > 0);

    /* unmapped letter and unknown view name give the topic's "unknown" text without prefix */
    ut_kb_outcome o = query(&kb, "# x");
    CHECK(o == UT_KB_UNKNOWN && out_n > 0);
    char unknown[sizeof out];
    memcpy(unknown, out, out_n + 1);
    CHECK(query(&kb, "gibtsnicht x") == UT_KB_UNKNOWN && !strcmp(out, unknown));
    CHECK(fn_answer(&kb, 0, "x") == UT_KB_UNKNOWN && !strcmp(out, unknown));

    /* topic check (research R11) */
    CHECK(ut_kb_check_topic(&kb, NULL) == UT_KB_OK);
    CHECK(ut_kb_check_topic(&kb, "") == UT_KB_OK);
    CHECK(ut_kb_check_topic(&kb, kb.topic) == UT_KB_OK);
    CHECK(ut_kb_check_topic(&kb, "anderes") == UT_KB_WRONG_TOPIC);
    CHECK(query(&kb, "X y") == UT_KB_MISSING_OUT && !strcmp(out, UT_KB_TXT_MISSING));

    printf("knowledge: %s, %d cases (%d via fn path), %d failures\n", argv[1], n_cases, n_fn,
           failures);
    free(cases);
    free(data);
    return failures ? 1 : 0;
}
