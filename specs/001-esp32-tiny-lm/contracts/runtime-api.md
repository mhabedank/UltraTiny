# Contract: Portable Runtime C API (`runtime/include/utiny.h`)

Plain C11, no heap allocation, no global mutable state outside the context struct. Used by the
firmware and by the host CLI/tests.

```c
typedef enum {
  UT_OK = 0,
  UT_ERR_MAGIC, UT_ERR_VERSION, UT_ERR_HEADER_CRC, UT_ERR_PAYLOAD_CRC,
  UT_ERR_SIZE, UT_ERR_DIMS, UT_ERR_ARENA, UT_ERR_CONTEXT_FULL
} ut_status;

typedef struct ut_model ut_model;      /* read-only view into the mapped model file */
typedef struct ut_ctx   ut_ctx;        /* session: KV cache, activations, pos */

/* Validate and parse a model image (e.g. memory-mapped flash). No copy. */
ut_status ut_model_open(ut_model *m, const void *data, size_t size);

/* Bytes of arena required for this model (static buffer sized at build time). */
size_t ut_arena_size(const ut_model *m);

ut_status ut_ctx_init(ut_ctx *c, const ut_model *m, void *arena, size_t arena_size);
void      ut_ctx_reset(ut_ctx *c);                 /* pos = 0, feeds <bos> */

/* Feed one token at the current position (incremental prefill). */
ut_status ut_feed(ut_ctx *c, int token);
void      ut_rewind(ut_ctx *c, int n);             /* backspace: pos -= n */

/* Logits for the last fed position; returns pointer into arena (vocab_size floats). */
const float *ut_logits(const ut_ctx *c);

int ut_argmax(const float *logits, int n);
int ut_sample(const float *logits, int n, float temperature, uint32_t *rng_state);

/* Alphabet mapping */
int      ut_token_from_codepoint(const ut_model *m, uint32_t cp);  /* -> id or UT_TOK_UNK */
uint32_t ut_codepoint_from_token(const ut_model *m, int token);
```

Guarantees:

- Same model + same token sequence ⇒ bit-identical `ut_logits` on host and ESP32 (parity tests).
- `ut_feed` returns `UT_ERR_CONTEXT_FULL` instead of writing past `ctx_len`.
- All functions are reentrant per `ut_ctx`.

## Console (`runtime/include/utiny_console.h`)

Platform-independent console state machine (data-model.md Session); the firmware only supplies
I/O and time callbacks, so the logic is host-testable.

```c
typedef struct {
  int      (*read_byte)(void *user);              /* -1 if no byte available (non-blocking) */
  void     (*write)(void *user, const char *buf, size_t n);
  uint32_t (*millis)(void *user);
  uint32_t (*free_heap)(void *user);       /* optional (NULL), shown by /info */
  void     *user;
} ut_console_io;

typedef struct ut_console ut_console;             /* holds Session state, line buffer, stats */

void ut_console_init(ut_console *k, ut_ctx *c, const ut_model *m, size_t arena_bytes,
                     const ut_console_io *io, ut_status model_status); /* != UT_OK -> HALT_ERROR */
void ut_console_banner(ut_console *k);
void ut_console_poll(ut_console *k);               /* process available input, generate step(s) */
```

Behavior and texts are defined in [serial-console.md](serial-console.md).

Host CLI `utiny-host`:

```text
utiny-host --model model.utny [--prompt "Frage"] [--greedy | --sample SEED TEMP] [--max N]
utiny-host --model model.utny --golden golden.json   # parity check, exit 0 on match
utiny-host --model model.utny --info                 # header fields + arena size (JSON)
```
