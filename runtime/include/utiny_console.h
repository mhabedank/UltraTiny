/*
 * Platform-independent serial console (contracts/serial-console.md,
 * data-model.md Session state machine). The firmware supplies I/O callbacks only,
 * so the whole interaction logic is host-testable.
 */
#ifndef UTINY_CONSOLE_H
#define UTINY_CONSOLE_H

#include "utiny.h"
#include "utiny_knowledge.h"

#ifdef __cplusplus
extern "C" {
#endif

#define UT_FW_VERSION "0.1.0"
#define UT_LINE_MAX 256
#define UT_CMD_MAX 112 /* "/wissen <view> <key>" with keys up to 60 bytes */
#define UT_ANSWER_RESERVE 32 /* positions kept free for the answer */
/* Upper bound for /max and the size of the trace buffer; boards with little RAM may lower it
 * (the NodeMCU build uses its context length, specs/005-nodemcu-port). */
#ifndef UT_MAX_ANSWER
#define UT_MAX_ANSWER 200
#endif

/* Platform values for /stats (specs/002-observability). Any field < 0 means unknown. */
typedef struct {
    int32_t heap_free;    /* bytes */
    int32_t heap_min;     /* lowest free heap since boot, bytes */
    int32_t heap_largest; /* largest allocatable block, bytes */
    int32_t stack_free;   /* stack high-water mark of the inference task, bytes */
    int32_t cpu_load[2];  /* percent per core since the previous call */
    int32_t uptime_ms;
    int32_t cpu_mhz;
    int32_t cores; /* number of CPU cores for the CPU-load line; < 0 = unknown (2 assumed) */
} ut_sys_stats;

typedef enum { UT_TRACE_OFF = 0, UT_TRACE_ON, UT_TRACE_JSON } ut_trace_mode;

/* One generated step of the last answer (compact, statically allocated). */
typedef struct {
    uint8_t tok;      /* chosen token (UT_TOK_EOS for the final stop step) */
    uint8_t top[3];   /* three most probable tokens */
    uint16_t p;       /* probability of tok, Q16 (p * 65535) */
    uint16_t top_p[3];
    uint16_t h_mbit;  /* entropy in millibits */
    uint16_t pos;     /* position whose logits were used */
    uint32_t us;      /* time since the previous emitted character (first: since Enter) */
} ut_trace_step;

typedef struct {
    int (*read_byte)(void *user); /* -1 if no byte available (non-blocking) */
    void (*write)(void *user, const char *buf, size_t n);
    uint32_t (*millis)(void *user);
    uint32_t (*free_heap)(void *user); /* optional (NULL): shown by /info */
    void *user;
    /* optional (NULL), appended for specs/002-observability */
    uint32_t (*micros)(void *user);                       /* finer timings; else millis*1000 */
    void (*sys_stats)(void *user, ut_sys_stats *out);     /* /stats system values */
    const char *board; /* optional (NULL): board name for the banner, specs/005-nodemcu-port */
    /* optional (NULL): knowledge image for function output (UTNY v2) and /wissen,
     * specs/006-hybrid-chemielehrer and specs/008-wissens-compiler */
    ut_kb *kb;
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
    /* observability (specs/002-observability) */
    size_t arena_cap;          /* size of the platform's arena buffer, 0 = unknown */
    ut_trace_mode trace;
    uint32_t us_enter, us_last; /* micro timestamps of Enter / last emitted char */
    int prefill;               /* tokens in context when the answer started */
    int n_steps;               /* recorded steps of the current/last answer (incl. stop) */
    int has_last;              /* a finished answer exists */
    struct {
        int n, prefill, ctx_used, aborted;
        char end[6];           /* "eos", "max", "ctx", "abort" */
        uint32_t first_us, total_us, us_min, us_max;
        uint32_t prof_us[UT_PROF_N];
    } last;
    float probs[UT_MAX_VOCAB];
    ut_trace_step steps[UT_MAX_ANSWER + 1];
    /* function output (specs/006 contracts/function-output.md): 0 = text, 1 = wait for type, 2 = key */
    int fn_mode, fn_has_type, fn_prefix, fn_key_len, raw;
    char fn_code;
    ut_kb_view fn_view;
    char fn_key[4 * UT_KB_KEY_MAX];
    char model_topic[16]; /* model meta "topic" ("" = none, not checked; research R11) */
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
