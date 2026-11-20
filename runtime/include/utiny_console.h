/*
 * Platform-independent serial console (contracts/serial-console.md,
 * data-model.md Session state machine). The firmware supplies I/O callbacks only,
 * so the whole interaction logic is host-testable.
 */
#ifndef UTINY_CONSOLE_H
#define UTINY_CONSOLE_H

#include "utiny.h"

#ifdef __cplusplus
extern "C" {
#endif

#define UT_FW_VERSION "0.1.0"
#define UT_LINE_MAX 256
#define UT_CMD_MAX 64
#define UT_ANSWER_RESERVE 32 /* positions kept free for the answer */
#define UT_MAX_ANSWER 200

typedef struct {
    int (*read_byte)(void *user); /* -1 if no byte available (non-blocking) */
    void (*write)(void *user, const char *buf, size_t n);
    uint32_t (*millis)(void *user);
    uint32_t (*free_heap)(void *user); /* optional (NULL): shown by /info */
    void *user;
} ut_console_io;

typedef enum { UT_ST_READY, UT_ST_TYPING, UT_ST_GENERATING, UT_ST_HALT_ERROR } ut_console_state;

typedef struct ut_console {
    ut_ctx *c;
    const ut_model *m;
    ut_console_io io;
    ut_status model_status;
    size_t arena_bytes;
    ut_console_state state;
    /* current input line (Session.input_len = line_len) */
    uint32_t line[UT_LINE_MAX];
    int line_len;
    int is_command;
    char cmd[UT_CMD_MAX];
    int cmd_len;
    int warned_unknown, warned_long, last_was_cr;
    ut_utf8_dec dec;
    /* Session.mode */
    int sampling;
    uint32_t seed, rng;
    float temperature;
    int max_answer;
    /* generation */
    int gen_count;
    uint32_t t_enter, t_first;
    /* stats of the last answer */
    uint32_t last_first_ms;
    float last_cps;
    float scratch[UT_MAX_VOCAB];
} ut_console;

/* ctx may be NULL when model_status != UT_OK (HALT_ERROR). */
void ut_console_init(ut_console *k, ut_ctx *c, const ut_model *m, size_t arena_bytes,
                     const ut_console_io *io, ut_status model_status);
void ut_console_banner(ut_console *k);
/* Processes all available input bytes, then performs at most one generation step. */
void ut_console_poll(ut_console *k);

#ifdef __cplusplus
}
#endif

#endif
