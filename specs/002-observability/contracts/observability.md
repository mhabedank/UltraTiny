# Contract: Observability (console commands, events, runtime hooks)

Extends [001 serial-console](../../001-esp32-tiny-lm/contracts/serial-console.md) and
[001 runtime-api](../../001-esp32-tiny-lm/contracts/runtime-api.md). With `/trace aus` (default),
the answer output, the banner and the output of all 001 commands except `/hilfe` are unchanged
byte for byte (spec FR-005). `/hilfe` additionally lists `/stats` and `/trace`.

## Commands

| Command | Output |
|---------|--------|
| `/stats` | system values, last answer timings, stage profile (+ `@ut` `sys` event in json mode); also in HALT_ERROR |
| `/trace` | current mode: `Trace: aus|an|json` |
| `/trace aus` | no trace (default) |
| `/trace an` | after every answer: table + summary (below) |
| `/trace json` | after every answer: `@ut` `token` events + one `answer` event |

### `/stats` (example from QEMU)

```text
System:
  Heap frei 189868 B, Minimum 185744 B, größter Block 110592 B
  Stack frei (Inferenz-Task) 5848 B
  Arena 79888 / 98304 B (81%)
  KV-Cache: Position 1 / 256 (letzte Antwort bis 74, 28%)
  CPU-Last: Kern 0 1 %, Kern 1 23 % (seit letztem /stats)
  Laufzeit 90.1 s, Takt 240 MHz
Letzte Antwort: 35 Zeichen (Ende: eos), Prefill 39 Token
  erstes Zeichen nach 4.07 ms, gesamt 172.0 ms, 203.4 Zeichen/s
  ms pro Zeichen: Ø 4.74, min 4.06, max 7.23
Profil (Rechenzeit 162.8 ms): embed 0.4% | norm 1.3% | qkv 11.1% | attn 38.3% | wo 10.6% | ffn 36.8% | head 1.6%
```

Values the platform does not provide are left out or shown as `?` in text, and are `null` in
JSON. CPU load is the non-idle share
per core since the previous `/stats` (FreeRTOS idle-task run-time counters).

### `/trace an`

Printed after the answer, before the prompt. One row per step; `␣` = space; the final `<eos>`
row is the model's decision to stop (only when the answer ended that way).

```text
--- Trace: 35 Zeichen, Ende: eos ---
 Pos  Zeichen      p   Top-3                              H/bit       ms
  39  D        1.000  D 1.000  ␣ 0.000  I 0.000         0.000     4.07
  ...
  74  <eos>    1.000  <eos> 1.000  1 0.000  ! 0.000     0.000     5.90
Ø p 1.000 | min p 1.000 bei Pos 70 ('R') | Ø Entropie 0.000 bit | Kontext 74/256 (28%)
```

- `Pos`: context position whose logits produced the step. `p`: probability of the chosen token
  (softmax at temperature 1, also in sampling mode). `H`: entropy of the distribution in bit.
  `ms`: time since the previous character (first: since Enter, incl. the `<sep>` step).
- End reasons: `eos`, `max` (`/max` reached), `ctx` (context full), `abort` (Ctrl-C).

## JSON events (`/trace json`)

Each event is one line `\r\n@ut <json>`; everything else is human text. Strings are UTF-8;
special tokens appear as `"<eos>"`, `"<sep>"` etc.

```json
{"type":"token","i":0,"pos":14,"ch":"I","stop":false,"p":0.9989,"h":0.014,"us":3379,
 "top":[["I",0.9989],["M",0.0009],["G",0.0001]]}
{"type":"answer","n":60,"steps":61,"end":"eos","aborted":false,"prefill":14,"ctx_used":74,
 "ctx_len":256,"first_ms":3.9,"total_ms":260.0,"cps":231.0,"ms_avg":4.2,"ms_min":3.3,
 "ms_max":6.3,"p_avg":0.9998,"p_min":0.9975,"p_min_i":4,"h_avg":0.002,
 "prof_us":{"embed":570,"norm":3570,"qkv":30080,"attn":82440,"wo":27760,"ffn":94570,"head":4370}}
{"type":"sys","model_ok":true,"heap_free":190084,"heap_min":185744,"heap_largest":110592,
 "stack_free":5880,"cpu_load":[0,7],"uptime_ms":2300,"cpu_mhz":240,"arena_need":79888,
 "arena_buf":98304,"kv_pos":1,"ctx_len":256}
```

(Shown wrapped; on the wire each event is a single line.) Unknown values are `null`.
`token.stop` is true for the `<eos>` step. `answer.p_min_i` indexes the token events.
`tools/observe.py --log` adds `ts` (and `prompt` for answer events) and writes a
`{"type":"result","prompt","answer","expected","match"}` record per question.

## Runtime API additions (`runtime/include/utiny.h`)

```c
typedef enum { UT_PROF_EMBED, UT_PROF_NORM, UT_PROF_QKV, UT_PROF_ATTN, UT_PROF_WO,
               UT_PROF_FFN, UT_PROF_HEAD, UT_PROF_N } ut_prof_stage;
typedef uint32_t (*ut_clock_us_fn)(void);
/* in ut_ctx: */ ut_clock_us_fn clock_us;  uint32_t prof_us[UT_PROF_N];
void ut_prof_reset(ut_ctx *c);
const char *ut_prof_name(int stage);
void ut_softmax_copy(const float *logits, int n, float *out);
```

`clock_us == NULL` (default after `ut_ctx_init`) disables profiling. Profiling only reads the
clock between stages; logits stay bit-identical. The console resets the profile at Enter, so it
covers `<sep>` and the answer, not the prefill while typing.

## Console I/O additions (`runtime/include/utiny_console.h`)

```c
typedef struct { int32_t heap_free, heap_min, heap_largest, stack_free, cpu_load[2],
                 uptime_ms, cpu_mhz; } ut_sys_stats;          /* < 0 = unknown */
/* appended to ut_console_io (optional, may be NULL): */
uint32_t (*micros)(void *user);
void (*sys_stats)(void *user, ut_sys_stats *out);
/* ut_console: */ size_t arena_cap;  /* platform arena buffer, 0 = unknown */
```

## Transports for tools

- Real board: serial port (115200 8N1).
- QEMU: `UT_QEMU_TCP=<port> tools/qemu_run.sh` exposes the console as a TCP server
  (`-serial tcp::<port>,server=on,wait=on`; QEMU waits for the first client).
- PC: `utiny-host --model M --console` runs the same console logic on stdin/stdout.
