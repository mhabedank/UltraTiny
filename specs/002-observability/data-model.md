# Data Model: Observability for Device and Model

All entities on the device are statically allocated (FR-007). The wire formats are defined in
[contracts/observability.md](contracts/observability.md).

## StageProfile (runtime, `ut_ctx`)

| Field | Type | Rules |
|-------|------|-------|
| `clock_us` | `uint32_t (*)(void)` | `NULL` = profiling off; cleared by `ut_ctx_init`, set by the platform afterwards |
| `prof_us[UT_PROF_N]` | `uint32_t[7]` | µs per stage `embed, norm, qkv, attn, wo, ffn, head`, accumulated by every `ut_feed` until `ut_prof_reset` |

Invariant: the logits of `ut_feed` are bit-identical with or without `clock_us` (FR-006).

## SysStats (platform → console, per `/stats` call)

| Field | Type | Unit | Source (ESP32) |
|-------|------|------|----------------|
| `heap_free` | int32 | B | `esp_get_free_heap_size` |
| `heap_min` | int32 | B | `esp_get_minimum_free_heap_size` |
| `heap_largest` | int32 | B | `heap_caps_get_largest_free_block(MALLOC_CAP_8BIT)` |
| `stack_free` | int32 | B | `uxTaskGetStackHighWaterMark(NULL)` (inference task) |
| `cpu_load[2]` | int32 | % (0–100) | idle-task run-time counter delta since the previous call |
| `uptime_ms` | int32 | ms | `esp_timer_get_time` |
| `cpu_mhz` | int32 | MHz | `esp_rom_get_cpu_ticks_per_us` |

Rules: every field is pre-set to −1 by the console, and any value < 0 means unknown (shown as
`?` / `null`). The callback is optional.

## TraceStep (console, `steps[UT_MAX_ANSWER + 1]`, 20 B)

| Field | Type | Rules |
|-------|------|-------|
| `tok` | uint8 | chosen token; `UT_TOK_EOS` only for the final stop step |
| `top[3]` | uint8[3] | most probable tokens, descending |
| `p` | uint16 | probability of `tok` as Q16 (p · 65535, rounded) |
| `top_p[3]` | uint16[3] | Q16 probabilities of `top` |
| `h_mbit` | uint16 | entropy in millibit, saturating at 65535 |
| `pos` | uint16 | context position whose logits produced the step |
| `us` | uint32 | µs since the previous emitted character (first: since Enter) |

Rules:

- `tok`, `pos` and `us` are always recorded; the distribution fields (`p`, `top`, `top_p`,
  `h_mbit`) only with trace `an`/`json`, otherwise they are 0.
- At most `max_answer` characters plus one stop step, so the step count is ≤ 201.

## AnswerSummary (console, `last`)

| Field | Type | Rules |
|-------|------|-------|
| `n` | int | emitted characters (excludes the stop step) |
| `prefill` | int | context length after `<sep>`, i.e. `<bos>` + question + `<sep>` |
| `ctx_used` | int | position at the end of the answer |
| `aborted` | bool | Ctrl-C |
| `end` | enum `eos`·`max`·`ctx`·`abort` | why the answer ended |
| `first_us`, `total_us` | uint32 | Enter → first character; Enter → end |
| `us_min`, `us_max` | uint32 | over character steps only (the stop step is excluded) |
| `prof_us[7]` | uint32[7] | copy of the StageProfile at the end; covers `<sep>` plus the answer |

Derived values (computed when printed): characters/s, mean ms per character, mean/min p and its
position, mean entropy.

## TraceMode (console)

`aus` (default) → `an` → `json`, set by `/trace <mode>`.

- The mode persists until changed or rebooted, also across serial reconnects. That is why tools
  set it explicitly.
- `aus` keeps the console output byte-identical to 001 (FR-005).

## State transitions (extension of the 001 session state machine)

```text
READY/TYPING --Enter--> GENERATING   [reset profile, steps := 0, us_enter := now]
GENERATING --step--> GENERATING      [record TraceStep]
GENERATING --<eos>|max|ctx|Ctrl-C--> READY
    [snapshot AnswerSummary; print the trace if mode != aus; then the prompt]
any state --/stats--> same state     [read SysStats; also works in HALT_ERROR]
```
