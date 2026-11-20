/* Serial console state machine (contracts/serial-console.md). */
#include "utiny_console.h"

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
    k->max_answer = UT_MAX_ANSWER;
    k->state = model_status == UT_OK && c ? UT_ST_READY : UT_ST_HALT_ERROR;
    if (k->c) ut_rewind(k->c, k->c->pos);
}

void ut_console_banner(ut_console *k) {
    out(k, "\r\nUltraTiny v" UT_FW_VERSION " \xE2\x80\x94 Sprachmodell offline auf dem ESP32\r\n");
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
         name[0] ? name : "?", UT_FORMAT_VERSION, (unsigned long)k->m->n_params,
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
           "  /max <n>                     maximale Antwortl\xC3\xA4nge (1-200)\r\n"
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
    }
    if (k->io.free_heap)
        outf(k, "\r\nFreier Heap: %lu Bytes", (unsigned long)k->io.free_heap(k->io.user));
}

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
    } else if (ok_model && !strcmp(argv[0], "/max") && argc >= 2) {
        int n = atoi(argv[1]);
        if (n < 1 || n > UT_MAX_ANSWER) {
            out(k, "\r\n/max erwartet 1-200");
        } else {
            k->max_answer = n;
            outf(k, "\r\nMaximale Antwortl\xC3\xA4nge: %d", n);
        }
    } else {
        out(k, "\r\nUnbekannter Befehl. /hilfe zeigt alle Befehle.");
    }
}

static void finish_answer(ut_console *k, int aborted) {
    uint32_t t = now(k);
    if (aborted) out(k, " [abgebrochen]");
    if (k->gen_count > 0) {
        k->last_first_ms = k->t_first - k->t_enter;
        uint32_t dt = t - k->t_enter;
        k->last_cps = dt > 0 ? (float)k->gen_count * 1000.0f / (float)dt : 0.0f;
    }
    clear_line(k);
    prompt(k);
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
    k->gen_count = 0;
    k->rng = k->seed;
    ut_feed(k->c, UT_TOK_SEP);
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
        if (b == 0x03) finish_answer(k, 1);
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

static void generate_step(ut_console *k) {
    ut_ctx *c = k->c;
    const float *lg = ut_logits(c);
    int tok = k->sampling
                  ? ut_sample(lg, k->m->vocab_size, k->temperature, &k->rng, k->scratch)
                  : ut_argmax(lg, k->m->vocab_size);
    if (tok == UT_TOK_EOS) {
        finish_answer(k, 0);
        return;
    }
    uint32_t cp = ut_codepoint_from_token(k->m, tok);
    if (cp) out_cp(k, cp);
    if (k->gen_count == 0) k->t_first = now(k);
    k->gen_count++;
    if (k->gen_count >= k->max_answer || c->pos >= k->m->ctx_len) {
        finish_answer(k, 0);
        return;
    }
    ut_feed(c, tok);
}

void ut_console_poll(ut_console *k) {
    int b;
    while ((b = k->io.read_byte(k->io.user)) >= 0) on_byte(k, (uint8_t)b);
    if (k->state == UT_ST_GENERATING) generate_step(k);
}
