/* Host tests for the fact table reader (specs/006-hybrid-chemielehrer, task T019).
 * Expected bytes come from the Python renderer (training/tools/make_runtime_fixtures.py), so a
 * pass means facts.c and facttable.py render identically. */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "json.h"
#include "utiny.h"
#include "utiny_facts.h"

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
static int reads = 0;

static int mem_read(void *u, uint32_t off, void *buf, uint32_t n) {
    (void)u;
    /* Like ESP.flashRead: offset, length and buffer must be word aligned. */
    if (((off | n) & 3u) != 0 || ((uintptr_t)buf & 3u) != 0) __builtin_trap();
    if (off > AREA || n > AREA - off) return -1;
    memcpy(buf, area + off, n);
    reads++;
    return 0;
}

static char out[512];
static size_t out_n;
static void cap(void *u, const char *s, size_t n) {
    (void)u;
    if (out_n + n < sizeof out) {
        memcpy(out + out_n, s, n);
        out_n += n;
    }
}

static int hexval(char c) { return c <= '9' ? c - '0' : c - 'a' + 10; }

/* The console's fn path: prefix on the type letter, ut_facts_finish at the end. */
static void answer(ut_facts *f, char code, const char *key) {
    out_n = 0;
    ut_fact_type t;
    int has = code && ut_facts_type(f, code, &t);
    int p = has ? ut_facts_prefix(f, &t, cap, NULL) : 0;
    ut_facts_finish(f, has ? &t : NULL, p, key, strlen(key), cap, NULL);
    out[out_n] = 0;
}

int main(int argc, char **argv) {
    const char *dir = argc > 1 ? argv[1] : "tests/fixtures";
    char path[512];
    snprintf(path, sizeof path, "%s/facts_small.utft", dir);
    size_t n = 0;
    char *data = read_file(path, &n);
    if (!data || n > AREA) {
        fprintf(stderr, "cannot read %s\n", path);
        return 2;
    }
    memset(area, 0xFF, AREA);
    memcpy(area, data, n);
    ut_facts f;
    CHECK(ut_facts_open(&f, mem_read, NULL, AREA) == UT_FACTS_OK);

    snprintf(path, sizeof path, "%s/facts_cases.tsv", dir);
    char *cases = read_file(path, NULL);
    CHECK(cases != NULL);
    int n_cases = 0;
    for (char *line = cases ? strtok(cases, "\n") : NULL; line; line = strtok(NULL, "\n")) {
        if (line[0] == '#') continue;
        char *code = line, *key = strchr(line, '\t');
        if (!key) continue;
        *key++ = 0;
        char *hex = strchr(key, '\t');
        if (!hex) continue;
        *hex++ = 0;
        char want[512];
        size_t wn = 0;
        for (size_t i = 0; hex[i] && hex[i + 1] && wn + 1 < sizeof want; i += 2)
            want[wn++] = (char)(hexval(hex[i]) * 16 + hexval(hex[i + 1]));
        want[wn] = 0;
        if (!strcmp(code, "MISSING")) {
            ut_facts none;
            uint8_t saved[4];
            memcpy(saved, area, 4);
            memset(area, 0xFF, 4); /* erased flash */
            CHECK(ut_facts_open(&none, mem_read, NULL, AREA) == UT_FACTS_MISSING);
            answer(&none, 'O', "Cu");
            memcpy(area, saved, 4);
        } else {
            answer(&f, strcmp(code, "-") ? code[0] : 0, key);
        }
        if (strcmp(out, want) != 0) {
            fprintf(stderr, "case %s/%s: got \"%s\" want \"%s\"\n", code, key, out, want);
            failures++;
        }
        n_cases++;
    }
    CHECK(n_cases >= 30);

    /* Corruption: payload CRC, header CRC, version, truncated size. */
    ut_facts g;
    area[n - 1] ^= 0x01;
    CHECK(ut_facts_open(&g, mem_read, NULL, AREA) == UT_FACTS_CORRUPT);
    area[n - 1] ^= 0x01;
    area[61] ^= 0x10;
    CHECK(ut_facts_open(&g, mem_read, NULL, AREA) == UT_FACTS_CORRUPT);
    area[61] ^= 0x10;
    CHECK(ut_facts_open(&g, mem_read, NULL, (uint32_t)n - 8) == UT_FACTS_CORRUPT);
    CHECK(ut_facts_open(&g, mem_read, NULL, AREA) == UT_FACTS_OK);
    /* NULL table and unknown type */
    answer(NULL, 'O', "Cu");
    CHECK(strcmp(out, UT_FACTS_TXT_MISSING) == 0);
    ut_fact_type t;
    CHECK(ut_facts_type(&g, '#', &t) == 0);

    free(cases);
    free(data);
    if (failures) {
        fprintf(stderr, "%d check(s) failed\n", failures);
        return 1;
    }
    printf("facts: %d cases OK (%d flash reads)\n", n_cases, reads);
    return 0;
}
