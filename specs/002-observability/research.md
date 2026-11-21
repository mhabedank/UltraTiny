# Research: Observability for Device and Model

The Technical Context in [plan.md](plan.md) has no open NEEDS CLARIFICATION. Each decision below
uses the format Decision / Rationale / Alternatives considered.

## R1. Where to measure the forward-pass stages

- **Decision**: An optional clock callback `ut_clock_us_fn clock_us` in `ut_ctx`. A `PROF(stage)`
  mark between the stages of `ut_feed` adds the elapsed µs to `prof_us[stage]`. There are seven
  stages (embed, norm, qkv, attn, wo, ffn, head), summed over all layers.
- **Rationale**:
  - The runtime has no global state (constitution V). Storing the clock in the context keeps it
    that way.
  - `NULL` disables profiling at the cost of one branch per stage.
  - Reading a clock does not change float operations, so parity holds (constitution III).
  - Seven counters are enough to see attention grow with the context while the matmul cost
    stays fixed.
- **Alternatives considered**:
  - Counters per layer and stage: 28+ counters and more output, little extra insight at 4 layers.
  - A compile-time `#ifdef UT_PROFILE`: a second build variant that is not parity-tested.
    Rejected (constitution V: one code path).
  - Sampling profiler / JTAG trace: needs hardware tooling and does not work in QEMU or CI.

## R2. Which clock

- **Decision**:
  - Firmware: `esp_timer_get_time()`, a 64-bit µs counter truncated to `uint32_t`.
  - Host: `clock_gettime(CLOCK_MONOTONIC)`.
  - Only differences are used, so 32-bit wraparound (every 71 min) is harmless.
- **Rationale**:
  - `esp_timer_get_time` costs ~1 µs, against ~30 ms per token on the target, so profiling costs
    about 0.1 %.
  - The function is available in QEMU.
- **Alternatives considered**:
  - `xthal_get_ccount()` cycle counter: per core, wraps after 18 s at 240 MHz, and changes with
    DFS.
  - `millis`: too coarse for stages.

## R3. CPU load per core on ESP-IDF 5.4

- **Decision**:
  - Enable `CONFIG_FREERTOS_USE_TRACE_FACILITY` and `CONFIG_FREERTOS_GENERATE_RUN_TIME_STATS`.
  - On each `/stats`, read the idle task's run-time counter per core with
    `vTaskGetInfo(xTaskGetIdleTaskHandleForCore(core), …)`.
  - Load = 100 − Δidle / Δwall, with Δwall from `esp_timer`.
- **Rationale**:
  - This is the standard FreeRTOS method, and the default run-time clock in IDF 5.x is
    `esp_timer` (µs).
  - `ulTaskGetRunTimeCounter` is **not** declared in IDF 5.4's FreeRTOS kernel (the build failed);
    `vTaskGetInfo` works.
  - "Since the previous `/stats`" means no background task or timer is needed (constitution V).
- **Alternatives considered**:
  - A periodic sampling task: costs a task stack and timer and complicates the core-1 pinning.
  - `vTaskGetRunTimeStats` text dump: needs a large buffer and string parsing.
  - The inference task itself is pinned to core 1 and does not yield while generating, so core 1
    is expected near 100 % during answers.

## R4. Memory values

- **Decision**:
  - Heap: `esp_get_free_heap_size`, `esp_get_minimum_free_heap_size`, and
    `heap_caps_get_largest_free_block(MALLOC_CAP_8BIT)`.
  - Stack: `uxTaskGetStackHighWaterMark(NULL)`, called from the inference task. ESP-IDF reports it
    in bytes, not words.
  - Arena: needed size (`ut_arena_size`) and buffer size (`console.arena_cap`).
  - KV fill: `pos / ctx_len`.
- **Rationale**: These are cheap, side-effect-free calls that answer the usual questions: is
  there a leak (minimum), fragmentation (largest block), stack headroom, and how full is the
  static arena.
- **Alternatives considered**: `heap_caps_print_heap_info` prints too much and cannot be parsed
  well.

## R5. Model trace content and cost

- **Decision**:
  - For each generated step: the chosen token, position, µs since the previous character, and,
    only when the trace is on, the softmax probability at T = 1, top-3 tokens and entropy in bit.
  - Storage is compact: Q16 probabilities and millibit entropy, 20 B per step, a static array of
    `UT_MAX_ANSWER + 1` steps (≈ 4 KB).
  - The trace is printed after the answer.
- **Rationale**:
  - FR-007 (no heap) and budget I: 4 KB static DRAM is acceptable with 35 % DRAM free.
  - The softmax over 96 logits plus `logf` costs ≪ 1 % of a forward pass (~0.6 M MAC).
  - Printing after the answer keeps the streamed text byte-identical, and per-character timings
    are not distorted by UART throughput (JSON at 115200 baud ≈ 15 ms per line).
  - T = 1 shows the model's own confidence even in sampling mode.
- **Alternatives considered**:
  - Streaming the trace per character: distorts timings and breaks byte identity of the answer.
  - Full float storage (28 B per step): 40 % more RAM for no visible gain at 3–4 digits.
  - The full distribution per step: 96 × 4 B × 200 = 77 KB, does not fit.

## R6. Machine-readable format

- **Decision**: Line-based events `\r\n@ut <json>` with types `token`, `answer` and `sys`. The
  JSON is written by hand with `snprintf`.
- **Rationale**:
  - Tools can find events with a prefix check, while human text and events can still share one
    serial stream.
  - No JSON library on the device (constitution V).
- **Alternatives considered**:
  - CBOR/binary: not readable in a terminal.
  - A separate UART: needs extra hardware pins and does not work in QEMU without more setup.

## R7. Transport between the PC and the device or emulator

- **Decision**:
  - `tools/devlib.py` gets three links: `SerialLink` (board), `TcpLink` (QEMU) and `ExecLink`
    (local process).
  - `qemu_run.sh` with `UT_QEMU_TCP=<port>` uses `-serial tcp::<port>,server=on,wait=on` and
    `-monitor none`.
  - `utiny-host --console` runs the same console logic on stdin/stdout.
- **Rationale**:
  - `wait=on` makes QEMU wait for the viewer, so the boot banner is not lost.
  - With the host console, the viewer and its tests run without an emulator, including in CI.
  - The existing scripts (`device_parity.py` etc.) keep their API.
- **Alternatives considered**:
  - A PTY (`-serial pty`): the device path is not predictable and macOS behaves differently.
  - `mon:stdio` and parsing QEMU's stdout: mixes in monitor escapes and needs a terminal.

## R8. Viewer presentation

- **Decision**:
  - ANSI true-colour per character: red (p = 0) → yellow (0.5) → green (1).
  - The three least certain positions (p < 0.95) with alternatives.
  - Profile bars sorted by share, a compact system line after each answer and the full `/stats`
    at the end.
  - `--log` writes JSONL with `ts` and `prompt`.
  - Colour is off for `NO_COLOR` or a non-TTY output.
- **Rationale**: Uncertainty is visible at a glance, and the details sit where they are needed.
  JSONL can be read by `jq` and pandas.
- **Alternatives considered**:
  - A TUI/curses dashboard: more code and harder to log or pipe.
  - A web UI: needs a server and more dependencies (YAGNI).
