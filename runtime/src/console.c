/* Serial console state machine (contracts/serial-console.md). */
#include "utiny_console.h"

#include <math.h>
#include <stdarg.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static void out(ut_console *k, const char *s) { k->io.write(k->io.user, s, strlen(s)); }

static void outf(ut_console *k, const char *fmt, ...) __attribute__((format(printf, 2, 3)));
static void outf(ut_console *k, const char *fmt, ...) {
    char buf[256];
    va_list ap;
    va_start(ap, fmt);
    int n = vsnprintf(buf, sizeof buf, fmt, ap);
    va_end(ap);
    if (n > 0) k->io.write(k->io.user, buf, (size_t)(n < (int)sizeof buf ? n : (int)sizeof buf - 1));
}

static void out_cp(ut_console *k, uint32_t cp) {
    char b[4];
    int n = ut_utf8_encode(cp, b);
    k->io.write(k->io.user, b, (size_t)n);
}

static uint32_t now(ut_console *k) { return k->io.millis ? k->io.millis(k->io.user) : 0; }

static uint32_t now_us(ut_console *k) {
    if (k->io.micros) return k->io.micros(k->io.user);
    return now(k) * 1000u;
}

/* Copies the string value of "key" from the flat meta JSON into buf ("" if absent). */
static void meta_str(const char *meta, const char *key, char *buf, size_t n) {
    char pat[32];
    snprintf(pat, sizeof pat, "\"%s\": \"", key);
    const char *p = meta ? strstr(meta, pat) : NULL;
    buf[0] = 0;
    if (!p) return;
    p += strlen(pat);
    size_t i = 0;
    while (*p && *p != '"' && i + 1 < n) buf[i++] = *p++;
    buf[i] = 0;
}

static int max_question_len(const ut_console *k) {
    /* <bos> + question + <sep> + reserve must fit into the context. */
    return k->m->ctx_len - 2 - UT_ANSWER_RESERVE;
}

/* Longest possible answer: <bos> + at least one question character + <sep> must fit too
 * (FR-006 of specs/005-nodemcu-port); never above UT_MAX_ANSWER. */
static int answer_cap(const ut_console *k) {
    int cap = UT_MAX_ANSWER;
    if (k->m && k->m->ctx_len - 3 < cap) cap = k->m->ctx_len - 3;
    return cap < 1 ? 1 : cap;
}

static void prompt(ut_console *k) { out(k, "\r\n> "); }

static void clear_line(ut_console *k) {
    k->line_len = 0;
    k->is_command = 0;
    k->cmd_len = 0;
    k->warned_unknown = 0;
    k->warned_long = 0;
    k->dec.need = 0;
    if (k->c) ut_rewind(k->c, k->c->pos); /* back to just <bos> */
    if (k->state != UT_ST_HALT_ERROR) k->state = UT_ST_READY;
}

static void reprint_line(ut_console *k) {
    out(k, "\r\n> ");
    for (int i = 0; i < k->line_len; i++) out_cp(k, k->line[i]);
}

void ut_console_init(ut_console *k, ut_ctx *c, const ut_model *m, size_t arena_bytes,
                     const ut_console_io *io, ut_status model_status) {
    memset(k, 0, sizeof *k);
    k->c = c;
    k->m = m;
    k->io = *io;
    k->model_status = model_status;
    k->arena_bytes = arena_bytes;
    k->seed = 1;
    k->rng = 1;
    k->temperature = 0.8f;
    k->max_answer = answer_cap(k);
    k->state = model_status == UT_OK && c ? UT_ST_READY : UT_ST_HALT_ERROR;
    if (k->c) ut_rewind(k->c, k->c->pos);
}

void ut_console_banner(ut_console *k) {
    out(k, "\r\nUltraTiny v" UT_FW_VERSION " \xE2\x80\x94 Sprachmodell offline auf dem Mikrocontroller\r\n");
    if (k->io.board) outf(k, "Board: %s\r\n", k->io.board);
    if (k->state == UT_ST_HALT_ERROR) {
        outf(k, "FEHLER: Modell ung\xC3\xBCltig (%d: %s). Bitte Modell neu flashen (siehe README).\r\n",
             (int)k->model_status, ut_status_str(k->model_status));
        out(k, "Nur /hilfe und /info sind verf\xC3\xBCgbar.");
        prompt(k);
        return;
    }
    char name[48];
    meta_str(k->m->meta, "name", name, sizeof name);
    outf(k, "Modell: %s | Format v%d | %lu Parameter | %lu KB Flash | %lu KB RAM\r\n",
         name[0] ? name : "?", k->m->has_fn ? 2 : 1, (unsigned long)k->m->n_params,
         (unsigned long)((k->m->size + 1023) / 1024), (unsigned long)((k->arena_bytes + 1023) / 1024));
    out(k, "Funk: aus. Tippe eine Frage und dr\xC3\xBC" "cke Enter. /hilfe f\xC3\xBCr Befehle.");
    prompt(k);
}

static void cmd_help(ut_console *k) {
    out(k, "\r\nBefehle:\r\n"
           "  /hilfe                       diese Hilfe\r\n"
           "  /info                        Modell, Speicher, Geschwindigkeit\r\n"
           "  /modus gierig                immer das wahrscheinlichste Zeichen (Standard)\r\n"
           "  /modus zufall [seed] [temp]  zuf\xC3\xA4llige Auswahl (seed 1, temp 0.8)\r\n"
           "  /max <n>                     maximale Antwortl\xC3\xA4nge\r\n"
           "  /stats                       Speicher, CPU-Last, Timings, Profil\r\n"
           "  /trace aus|an|json           Modell-Trace nach jeder Antwort (Standard aus)\r\n"
           "  /raw an|aus                  Funktionsausgabe zus\xC3\xA4tzlich roh zeigen\r\n"
           "Strg-C bricht eine Antwort ab.");
}

static void cmd_info(ut_console *k) {
    if (k->state == UT_ST_HALT_ERROR) {
        outf(k, "\r\nModellfehler %d: %s", (int)k->model_status, ut_status_str(k->model_status));
    } else {
        const ut_model *m = k->m;
        char git[24], date[16];
        meta_str(m->meta, "git", git, sizeof git);
        meta_str(m->meta, "date", date, sizeof date);
        outf(k, "\r\nModell: vocab %d, d %d, Schichten %d, Koepfe %d, ff %d, Kontext %d",
             m->vocab_size, m->d_model, m->n_layers, m->n_heads, m->d_ff, m->ctx_len);
        outf(k, "\r\nParameter: %lu | Datei: %lu Bytes | Arena: %lu Bytes",
             (unsigned long)m->n_params, (unsigned long)m->size, (unsigned long)k->arena_bytes);
        outf(k, "\r\nTraining: git %s, Datum %s", git[0] ? git : "?", date[0] ? date : "?");
        outf(k, "\r\nModus: %s (seed %lu, temp %.2f), max %d Zeichen",
             k->sampling ? "zufall" : "gierig", (unsigned long)k->seed, (double)k->temperature,
             k->max_answer);
        outf(k, "\r\nLetzte Antwort: erstes Zeichen nach %lu ms, %.1f Zeichen/s",
             (unsigned long)k->last_first_ms, (double)k->last_cps);
        if (m->has_fn) {
            const ut_facts *f = k->io.facts;
            if (f && f->status == UT_FACTS_OK)
                outf(k, "\r\nFaktentabelle: OK v%d, %lu Eintr\xC3\xA4ge, data %08lx", UT_FACTS_VERSION,
                     (unsigned long)f->n_records, (unsigned long)f->sha4);
            else
                outf(k, "\r\nFaktentabelle: %s",
                     ut_facts_status_str(f ? f->status : UT_FACTS_MISSING));
        }
    }
    if (k->io.free_heap)
        outf(k, "\r\nFreier Heap: %lu Bytes", (unsigned long)k->io.free_heap(k->io.user));
}

static void cmd_stats(ut_console *k);
static void cmd_trace(ut_console *k, int argc, char **argv);

static void run_command(ut_console *k) {
    k->cmd[k->cmd_len] = 0;
    char *argv[4] = {0};
    int argc = 0;
    for (char *tok = strtok(k->cmd, " "); tok && argc < 4; tok = strtok(NULL, " "))
        argv[argc++] = tok;
    const int ok_model = k->state != UT_ST_HALT_ERROR;
    if (argc == 0) {
    } else if (!strcmp(argv[0], "/hilfe")) {
        cmd_help(k);
    } else if (!strcmp(argv[0], "/info")) {
        cmd_info(k);
    } else if (!strcmp(argv[0], "/stats")) {
        cmd_stats(k);
    } else if (!strcmp(argv[0], "/trace")) {
        cmd_trace(k, argc, argv);
    } else if (ok_model && !strcmp(argv[0], "/modus") && argc >= 2 && !strcmp(argv[1], "gierig")) {
        k->sampling = 0;
        out(k, "\r\nModus: gierig");
    } else if (ok_model && !strcmp(argv[0], "/modus") && argc >= 2 && !strcmp(argv[1], "zufall")) {
        k->sampling = 1;
        k->seed = argc >= 3 ? (uint32_t)strtoul(argv[2], NULL, 10) : 1;
        if (k->seed == 0) k->seed = 1;
        k->rng = k->seed;
        k->temperature = argc >= 4 ? (float)atof(argv[3]) : 0.8f;
        if (!(k->temperature > 0.0f)) k->temperature = 0.8f;
        outf(k, "\r\nModus: zufall (seed %lu, temp %.2f)", (unsigned long)k->seed,
             (double)k->temperature);
    } else if (!strcmp(argv[0], "/raw") && argc >= 2) {
        k->raw = !strcmp(argv[1], "an");
        outf(k, "\r\nRohausgabe: %s", k->raw ? "an" : "aus");
    } else if (ok_model && !strcmp(argv[0], "/max") && argc >= 2) {
        int n = atoi(argv[1]), cap = answer_cap(k);
        if (n < 1) {
            outf(k, "\r\n/max erwartet 1-%d", cap);
        } else if (n > cap) {
            k->max_answer = cap; /* longer answers would not fit the context */
            outf(k, "\r\nMaximale Antwortl\xC3\xA4nge: %d (Grenze des Kontexts)", cap);
        } else {
            k->max_answer = n;
            outf(k, "\r\nMaximale Antwortl\xC3\xA4nge: %d", n);
        }
    } else {
        out(k, "\r\nUnbekannter Befehl. /hilfe zeigt alle Befehle.");
    }
}

/* ---- observability (specs/002-observability) ---------------------------------------- */

static float q16(uint16_t v) { return (float)v / 65535.0f; }

/* Display label of a token: specials as <eos> etc., space as U+2423 when `visible_space`. */
static int tok_label(const ut_console *k, int tok, char *buf, int visible_space) {
    static const char *const specials[] = {"<pad>", "<bos>", "<sep>", "<eos>", "<unk>"};
    uint32_t cp = ut_codepoint_from_token(k->m, tok);
    if (cp == 0) {
        const char *s = tok >= 0 && tok <= UT_TOK_UNK ? specials[tok]
                        : (tok == UT_TOK_FN && k->m->has_fn) ? "\xE2\x9F\xA8" "fn" "\xE2\x9F\xA9"
                                                            : "<?>";
        strcpy(buf, s);
        return (int)strlen(s);
    }
    if (cp == ' ' && visible_space) cp = 0x2423;
    int n = ut_utf8_encode(cp, buf);
    buf[n] = 0;
    return 1; /* display width */
}

static void out_json_label(ut_console *k, int tok) {
    char b[8], e[20];
    tok_label(k, tok, b, 0);
    int j = 0;
    e[j++] = '"';
    for (int i = 0; b[i] && j < 16; i++) {
        unsigned char ch = (unsigned char)b[i];
        if (ch == '"' || ch == '\\') {
            e[j++] = '\\';
            e[j++] = (char)ch;
        } else if (ch < 0x20) {
            j += snprintf(e + j, sizeof e - (size_t)j, "\\u%04x", ch);
        } else {
            e[j++] = (char)ch;
        }
    }
    e[j++] = '"';
    k->io.write(k->io.user, e, (size_t)j);
}

static void out_json_int(ut_console *k, const char *key, int32_t v, int comma) {
    if (v < 0) outf(k, "%s\"%s\":null", comma ? "," : "", key);
    else outf(k, "%s\"%s\":%ld", comma ? "," : "", key, (long)v);
}

/* Records one generation step; the model distribution only when a trace is active. */
static void record_step(ut_console *k, const float *lg, int tok, int pos, uint32_t us) {
    if (k->n_steps > UT_MAX_ANSWER) return;
    ut_trace_step *s = &k->steps[k->n_steps++];
    memset(s, 0, sizeof *s);
    s->tok = (uint8_t)tok;
    s->pos = (uint16_t)pos;
    s->us = us;
    if (k->trace == UT_TRACE_OFF) return;
    const int n = k->m->vocab_size;
    ut_softmax_copy(lg, n, k->probs);
    int top[3] = {0, 0, 0};
    float tp[3] = {-1.0f, -1.0f, -1.0f};
    float h = 0.0f;
    for (int i = 0; i < n; i++) {
        float p = k->probs[i];
        if (p > 0.0f) h -= p * logf(p);
        for (int r = 0; r < 3; r++) {
            if (p > tp[r]) {
                for (int q = 2; q > r; q--) {
                    tp[q] = tp[q - 1];
                    top[q] = top[q - 1];
                }
                tp[r] = p;
                top[r] = i;
                break;
            }
        }
    }
    h *= 1.44269504f; /* nats -> bits */
    s->p = (uint16_t)(k->probs[tok] * 65535.0f + 0.5f);
    for (int r = 0; r < 3; r++) {
        s->top[r] = (uint8_t)top[r];
        s->top_p[r] = (uint16_t)(tp[r] * 65535.0f + 0.5f);
    }
    float hm = h * 1000.0f + 0.5f;
    s->h_mbit = (uint16_t)(hm > 65535.0f ? 65535.0f : hm);
}

typedef struct {
    float p_avg, p_min, h_avg;
    int p_min_i;
} trace_summary;

static trace_summary summarize(const ut_console *k) {
    trace_summary t = {0.0f, 1.0f, 0.0f, -1};
    for (int i = 0; i < k->n_steps; i++) {
        float p = q16(k->steps[i].p);
        t.p_avg += p;
        t.h_avg += (float)k->steps[i].h_mbit / 1000.0f;
        if (p < t.p_min || t.p_min_i < 0) {
            t.p_min = p;
            t.p_min_i = i;
        }
    }
    if (k->n_steps > 0) {
        t.p_avg /= (float)k->n_steps;
        t.h_avg /= (float)k->n_steps;
    } else {
        t.p_min = 0.0f;
    }
    return t;
}

static void print_trace_table(ut_console *k) {
    char b[8];
    outf(k, "\r\n--- Trace: %d Zeichen, Ende: %s ---", k->last.n, k->last.end);
    out(k, "\r\n Pos  Zeichen      p   Top-3                              H/bit       ms");
    for (int i = 0; i < k->n_steps; i++) {
        const ut_trace_step *s = &k->steps[i];
        outf(k, "\r\n%4d  ", s->pos);
        int w = tok_label(k, s->tok, b, 1);
        out(k, b);
        for (; w < 7; w++) out(k, " ");
        outf(k, " %6.3f  ", (double)q16(s->p));
        int col = 0;
        for (int r = 0; r < 3; r++) {
            int lw = tok_label(k, s->top[r], b, 1);
            out(k, b);
            outf(k, " %.3f  ", (double)q16(s->top_p[r]));
            col += lw + 8;
        }
        for (; col < 33; col++) out(k, " ");
        outf(k, "%6.3f %8.2f", (double)s->h_mbit / 1000.0, (double)s->us / 1000.0);
    }
    trace_summary t = summarize(k);
    outf(k, "\r\n\xC3\x98 p %.3f | min p %.3f", (double)t.p_avg, (double)t.p_min);
    if (t.p_min_i >= 0) {
        tok_label(k, k->steps[t.p_min_i].tok, b, 1);
        outf(k, " bei Pos %d ('", k->steps[t.p_min_i].pos);
        out(k, b);
        out(k, "')");
    }
    outf(k, " | \xC3\x98 Entropie %.3f bit | Kontext %d/%d (%d%%)", (double)t.h_avg,
         k->last.ctx_used, k->m->ctx_len, k->last.ctx_used * 100 / k->m->ctx_len);
}

static void print_trace_json(ut_console *k) {
    for (int i = 0; i < k->n_steps; i++) {
        const ut_trace_step *s = &k->steps[i];
        outf(k, "\r\n@ut {\"type\":\"token\",\"i\":%d,\"pos\":%d,\"ch\":", i, s->pos);
        out_json_label(k, s->tok);
        outf(k, ",\"stop\":%s,\"p\":%.4f,\"h\":%.3f,\"us\":%lu,\"top\":[",
             s->tok == UT_TOK_EOS ? "true" : "false", (double)q16(s->p),
             (double)s->h_mbit / 1000.0, (unsigned long)s->us);
        for (int r = 0; r < 3; r++) {
            out(k, r ? ",[" : "[");
            out_json_label(k, s->top[r]);
            outf(k, ",%.4f]", (double)q16(s->top_p[r]));
        }
        out(k, "]}");
    }
    trace_summary t = summarize(k);
    const uint32_t n = (uint32_t)k->last.n;
    double total_ms = (double)k->last.total_us / 1000.0;
    outf(k, "\r\n@ut {\"type\":\"answer\",\"n\":%d,\"steps\":%d,\"end\":\"%s\",\"aborted\":%s",
         k->last.n, k->n_steps, k->last.end, k->last.aborted ? "true" : "false");
    outf(k, ",\"prefill\":%d,\"ctx_used\":%d,\"ctx_len\":%d", k->last.prefill, k->last.ctx_used,
         k->m->ctx_len);
    outf(k, ",\"first_ms\":%.3f,\"total_ms\":%.3f,\"cps\":%.2f",
         n ? (double)k->last.first_us / 1000.0 : 0.0, total_ms,
         total_ms > 0.0 ? (double)n * 1000.0 / total_ms : 0.0);
    double sum = 0.0;
    for (int i = 0; i < k->n_steps; i++)
        if (k->steps[i].tok != UT_TOK_EOS) sum += (double)k->steps[i].us;
    outf(k, ",\"ms_avg\":%.3f,\"ms_min\":%.3f,\"ms_max\":%.3f", n ? sum / n / 1000.0 : 0.0,
         (double)k->last.us_min / 1000.0, (double)k->last.us_max / 1000.0);
    outf(k, ",\"p_avg\":%.4f,\"p_min\":%.4f,\"p_min_i\":%d,\"h_avg\":%.3f", (double)t.p_avg,
         (double)t.p_min, t.p_min_i, (double)t.h_avg);
    out(k, ",\"prof_us\":{");
    for (int i = 0; i < UT_PROF_N; i++)
        outf(k, "%s\"%s\":%lu", i ? "," : "", ut_prof_name(i), (unsigned long)k->last.prof_us[i]);
    out(k, "}}");
}

static void finish_answer(ut_console *k, int aborted, const char *end) {
    uint32_t t = now(k);
    uint32_t t_us = now_us(k);
    if (aborted) out(k, " [abgebrochen]");
    if (k->gen_count > 0) {
        k->last_first_ms = k->t_first - k->t_enter;
        uint32_t dt = t - k->t_enter;
        k->last_cps = dt > 0 ? (float)k->gen_count * 1000.0f / (float)dt : 0.0f;
    }
    /* observability snapshot */
    k->has_last = 1;
    k->last.n = k->gen_count;
    k->last.prefill = k->prefill;
    k->last.ctx_used = k->c->pos;
    k->last.aborted = aborted;
    snprintf(k->last.end, sizeof k->last.end, "%s", end);
    k->last.total_us = t_us - k->us_enter;
    k->last.first_us = k->n_steps > 0 ? k->steps[0].us : 0;
    k->last.us_min = 0;
    k->last.us_max = 0;
    int first = 1;
    for (int i = 0; i < k->n_steps; i++) {
        uint32_t us = k->steps[i].us;
        if (k->steps[i].tok == UT_TOK_EOS) continue;
        if (first || us < k->last.us_min) k->last.us_min = us;
        if (first || us > k->last.us_max) k->last.us_max = us;
        first = 0;
    }
    memcpy(k->last.prof_us, k->c->prof_us, sizeof k->last.prof_us);
    if (k->trace == UT_TRACE_ON) print_trace_table(k);
    else if (k->trace == UT_TRACE_JSON) print_trace_json(k);
    clear_line(k);
    prompt(k);
}

static void cmd_stats(ut_console *k) {
    ut_sys_stats st;
    for (int i = 0; i < (int)(sizeof st / sizeof(int32_t)); i++) ((int32_t *)&st)[i] = -1;
    if (k->io.sys_stats) k->io.sys_stats(k->io.user, &st);
    const int ok = k->state != UT_ST_HALT_ERROR;
    out(k, "\r\nSystem:");
    if (st.heap_free >= 0)
    {
        outf(k, "\r\n  Heap frei %ld B", (long)st.heap_free);
        if (st.heap_min >= 0) outf(k, ", Minimum %ld B", (long)st.heap_min); /* unknown on ESP8266 */
        if (st.heap_largest >= 0)
            outf(k, ", gr\xC3\xB6\xC3\x9F" "ter Block %ld B", (long)st.heap_largest);
    }
    else if (k->io.free_heap)
        outf(k, "\r\n  Heap frei %lu B", (unsigned long)k->io.free_heap(k->io.user));
    else
        out(k, "\r\n  Heap: unbekannt");
    if (st.stack_free >= 0)
        outf(k, "\r\n  Stack frei (Inferenz-Task) %ld B", (long)st.stack_free);
    if (ok) {
        if (k->arena_cap)
            outf(k, "\r\n  Arena %lu / %lu B (%lu%%)", (unsigned long)k->arena_bytes,
                 (unsigned long)k->arena_cap,
                 (unsigned long)(k->arena_bytes * 100 / k->arena_cap));
        else
            outf(k, "\r\n  Arena %lu B", (unsigned long)k->arena_bytes);
        outf(k, "\r\n  KV-Cache: Position %d / %d", k->c->pos, k->m->ctx_len);
        if (k->has_last)
            outf(k, " (letzte Antwort bis %d, %d%%)", k->last.ctx_used,
                 k->last.ctx_used * 100 / k->m->ctx_len);
    } else {
        outf(k, "\r\n  Modellfehler %d: %s", (int)k->model_status, ut_status_str(k->model_status));
    }
    out(k, "\r\n  CPU-Last:");
    const int cores = st.cores == 1 ? 1 : 2;
    for (int i = 0; i < cores; i++) {
        if (st.cpu_load[i] >= 0) outf(k, " Kern %d %ld %%", i, (long)st.cpu_load[i]);
        else outf(k, " Kern %d ?", i);
        if (i + 1 < cores) out(k, ",");
    }
    out(k, " (seit letztem /stats)");
    if (st.uptime_ms >= 0) outf(k, "\r\n  Laufzeit %.1f s", (double)st.uptime_ms / 1000.0);
    if (st.cpu_mhz >= 0) outf(k, ", Takt %ld MHz", (long)st.cpu_mhz);
    if (ok) {
        if (!k->has_last) {
            out(k, "\r\nLetzte Antwort: noch keine");
        } else {
            const int n = k->last.n;
            double total_ms = (double)k->last.total_us / 1000.0;
            outf(k, "\r\nLetzte Antwort: %d Zeichen (Ende: %s), Prefill %d Token", n,
                 k->last.end, k->last.prefill);
            outf(k, "\r\n  erstes Zeichen nach %.2f ms, gesamt %.1f ms, %.1f Zeichen/s",
                 n ? (double)k->last.first_us / 1000.0 : 0.0, total_ms,
                 total_ms > 0.0 ? n * 1000.0 / total_ms : 0.0);
            if (n > 0) {
                double sum = 0.0;
                for (int i = 0; i < k->n_steps; i++)
                    if (k->steps[i].tok != UT_TOK_EOS) sum += (double)k->steps[i].us;
                outf(k, "\r\n  ms pro Zeichen: \xC3\x98 %.2f, min %.2f, max %.2f",
                     sum / n / 1000.0, (double)k->last.us_min / 1000.0,
                     (double)k->last.us_max / 1000.0);
            }
            uint32_t tot = 0;
            for (int i = 0; i < UT_PROF_N; i++) tot += k->last.prof_us[i];
            if (tot == 0) {
                out(k, "\r\nProfil: nicht verf\xC3\xBCgbar (keine Uhr)");
            } else {
                outf(k, "\r\nProfil (Rechenzeit %.1f ms):", (double)tot / 1000.0);
                for (int i = 0; i < UT_PROF_N; i++)
                    outf(k, "%s %s %.1f%%", i ? " |" : "", ut_prof_name(i),
                         (double)k->last.prof_us[i] * 100.0 / (double)tot);
            }
        }
    }
    if (k->trace == UT_TRACE_JSON) {
        outf(k, "\r\n@ut {\"type\":\"sys\",\"model_ok\":%s", ok ? "true" : "false");
        out_json_int(k, "heap_free", st.heap_free, 1);
        out_json_int(k, "heap_min", st.heap_min, 1);
        out_json_int(k, "heap_largest", st.heap_largest, 1);
        out_json_int(k, "stack_free", st.stack_free, 1);
        out(k, ",\"cpu_load\":[");
        for (int i = 0; i < 2; i++) {
            if (i) out(k, ",");
            if (st.cpu_load[i] >= 0) outf(k, "%ld", (long)st.cpu_load[i]);
            else out(k, "null");
        }
        out(k, "]");
        out_json_int(k, "uptime_ms", st.uptime_ms, 1);
        out_json_int(k, "cpu_mhz", st.cpu_mhz, 1);
        if (ok) {
            outf(k, ",\"arena_need\":%lu,\"arena_buf\":%lu,\"kv_pos\":%d,\"ctx_len\":%d",
                 (unsigned long)k->arena_bytes, (unsigned long)k->arena_cap, k->c->pos,
                 k->m->ctx_len);
        }
        out(k, "}");
    }
}

static void cmd_trace(ut_console *k, int argc, char **argv) {
    static const char *const names[] = {"aus", "an", "json"};
    if (argc >= 2) {
        int found = -1;
        for (int i = 0; i < 3; i++)
            if (!strcmp(argv[1], names[i])) found = i;
        if (found < 0) {
            out(k, "\r\n/trace erwartet aus, an oder json");
            return;
        }
        k->trace = (ut_trace_mode)found;
    }
    outf(k, "\r\nTrace: %s", names[k->trace]);
}

static void on_enter(ut_console *k) {
    if (k->is_command) {
        run_command(k);
        clear_line(k);
        prompt(k);
        return;
    }
    if (k->line_len == 0 || k->state == UT_ST_HALT_ERROR) {
        clear_line(k);
        prompt(k);
        return;
    }
    out(k, "\r\n");
    k->t_enter = now(k);
    k->us_enter = now_us(k);
    k->us_last = k->us_enter;
    k->gen_count = 0;
    k->n_steps = 0;
    k->fn_mode = 0;
    k->fn_has_type = 0;
    k->fn_prefix = 0;
    k->fn_key_len = 0;
    k->fn_code = 0;
    k->rng = k->seed;
    ut_prof_reset(k->c); /* profile covers <sep> + the answer, not typing-time prefill */
    ut_feed(k->c, UT_TOK_SEP);
    k->prefill = k->c->pos;
    k->state = UT_ST_GENERATING;
}

static void on_backspace(ut_console *k) {
    if (k->is_command) {
        if (k->cmd_len > 0) {
            k->cmd_len--;
            out(k, "\b \b");
        }
        if (k->cmd_len == 0) k->is_command = 0;
        return;
    }
    if (k->line_len > 0) {
        k->line_len--;
        ut_rewind(k->c, 1);
        out(k, "\b \b");
        if (k->line_len == 0) k->state = UT_ST_READY;
    }
}

static void on_codepoint(ut_console *k, uint32_t cp) {
    if (cp < 0x20 || cp == 0x7F) return;
    if (k->line_len == 0 && !k->is_command && cp == '/') {
        k->is_command = 1;
    }
    if (k->is_command) {
        if (cp < 0x80 && k->cmd_len < UT_CMD_MAX - 1) {
            k->cmd[k->cmd_len++] = (char)cp;
            out_cp(k, cp);
        }
        return;
    }
    if (k->state == UT_ST_HALT_ERROR) return;
    int tok = ut_token_from_codepoint(k->m, cp);
    if (tok == UT_TOK_UNK) {
        if (!k->warned_unknown) {
            out(k, "  (Zeichen '");
            out_cp(k, cp);
            out(k, "' unbekannt, ignoriert)");
            k->warned_unknown = 1;
            reprint_line(k);
        }
        return;
    }
    if (k->line_len >= max_question_len(k) || k->line_len >= UT_LINE_MAX) {
        if (!k->warned_long) {
            outf(k, "  (Frage zu lang, max %d Zeichen)", max_question_len(k));
            k->warned_long = 1;
            reprint_line(k);
        }
        return;
    }
    if (ut_feed(k->c, tok) != UT_OK) return;
    k->line[k->line_len++] = cp;
    k->state = UT_ST_TYPING;
    out_cp(k, cp);
}

static void on_byte(ut_console *k, uint8_t b) {
    if (k->state == UT_ST_GENERATING) {
        if (b == 0x03) finish_answer(k, 1, "abort");
        return; /* other input is discarded while answering */
    }
    if (b == '\n' && k->last_was_cr) {
        k->last_was_cr = 0;
        return;
    }
    k->last_was_cr = (b == '\r');
    if (b == '\r' || b == '\n') {
        on_enter(k);
    } else if (b == 0x03) {
        out(k, "^C");
        clear_line(k);
        prompt(k);
    } else if (b == 0x08 || b == 0x7F) {
        on_backspace(k);
    } else {
        uint32_t cp;
        int r = ut_utf8_feed(&k->dec, b, &cp);
        if (r == 1) on_codepoint(k, cp);
    }
}

static void fn_write(void *u, const char *s, size_t n) {
    ut_console *k = (ut_console *)u;
    k->io.write(k->io.user, s, n);
}

/* End of a function answer: lookup and print the rest (contracts/function-output.md). */
static void fn_finish(ut_console *k) {
    ut_facts_finish(k->io.facts, k->fn_has_type ? &k->fn_type : NULL, k->fn_prefix, k->fn_key,
                    (size_t)k->fn_key_len, fn_write, k);
    if (k->raw) {
        out(k, "  [");
        out(k, "\xE2\x9F\xA8" "fn" "\xE2\x9F\xA9");
        if (k->fn_code) k->io.write(k->io.user, &k->fn_code, 1);
        k->io.write(k->io.user, k->fn_key, (size_t)k->fn_key_len);
        out(k, "]");
    }
}

static void generate_step(ut_console *k) {
    ut_ctx *c = k->c;
    const float *lg = ut_logits(c);
    int tok = k->sampling
                  ? ut_sample(lg, k->m->vocab_size, k->temperature, &k->rng, k->scratch)
                  : ut_argmax(lg, k->m->vocab_size);
    const int pos = c->pos;
    const int is_fn = k->m->has_fn && tok == UT_TOK_FN;
    if (tok == UT_TOK_EOS || (is_fn && k->gen_count > 0)) {
        /* <eos>, or a <fn> that is not the first token (treated as <eos>) */
        uint32_t t = now_us(k);
        record_step(k, lg, tok, pos, t - k->us_last);
        if (k->fn_mode) fn_finish(k);
        finish_answer(k, 0, "eos");
        return;
    }
    uint32_t cp = ut_codepoint_from_token(k->m, tok);
    if (is_fn) {
        k->fn_mode = 1;
    } else if (k->fn_mode == 1) {
        char code = (cp >= 'A' && cp <= 'Z') || (cp >= 'a' && cp <= 'z') ? (char)cp : 0;
        k->fn_code = code;
        k->fn_has_type = code && ut_facts_type(k->io.facts, code, &k->fn_type);
        if (k->fn_has_type) k->fn_prefix = ut_facts_prefix(k->io.facts, &k->fn_type, fn_write, k);
        k->fn_mode = 2;
    } else if (k->fn_mode == 2) {
        if (cp && k->fn_key_len + 4 <= (int)sizeof k->fn_key)
            k->fn_key_len += ut_utf8_encode(cp, k->fn_key + k->fn_key_len);
    } else if (cp) {
        out_cp(k, cp);
    }
    if (k->gen_count == 0) k->t_first = now(k);
    uint32_t t = now_us(k);
    record_step(k, lg, tok, pos, t - k->us_last);
    k->us_last = t;
    k->gen_count++;
    const int fn_full = k->fn_mode && k->gen_count >= 2 + UT_FACTS_KEY_MAX;
    if (k->gen_count >= k->max_answer || c->pos >= k->m->ctx_len || fn_full) {
        if (k->fn_mode) fn_finish(k);
        finish_answer(k, 0, k->gen_count >= k->max_answer ? "max" : (fn_full ? "eos" : "ctx"));
        return;
    }
    ut_feed(c, tok);
}

void ut_console_poll(ut_console *k) {
    int b;
    while ((b = k->io.read_byte(k->io.user)) >= 0) on_byte(k, (uint8_t)b);
    if (k->state == UT_ST_GENERATING) generate_step(k);
}
