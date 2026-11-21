# Implementation Plan: Observability for Device and Model

**Branch**: `claude/observability-002` | **Date**: 2026-11-21 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `/specs/002-observability/spec.md`

## Summary

Observability is added in three thin layers without touching the model math: (1) the portable
runtime gets an optional microsecond clock hook that accumulates time per forward-pass stage,
plus a side-effect-free softmax for probabilities; (2) the platform-independent console gets
`/stats` and `/trace aus|an|json`, records per-step data in a static buffer and prints it after
the answer; (3) the firmware supplies `esp_timer`, heap, stack and per-core CPU load (FreeRTOS
idle-task run-time counters). On the PC, `tools/observe.py` drives the console (serial, TCP to
QEMU, or `utiny-host --console`) and renders the JSON events. See [research.md](research.md).

## Technical Context

**Language/Version**: C11 (runtime, firmware); Python 3.12 (viewer, tests)

**Primary Dependencies**: ESP-IDF v5.4.1 (`esp_timer`, `heap_caps`, FreeRTOS run-time stats);
pyserial (existing dev dependency); no new dependencies

**Storage**: N/A (all values live in RAM; optional JSONL log file on the PC via `--log`)

**Testing**: CTest `test_console_logic` (stats, trace modes, byte identity with trace off, logit
identity with profiling on), golden parity (host), `device_parity.py --tcp` in QEMU, pytest
`tests/test_observe.py` (parser + end-to-end against `utiny-host --console`)

**Target Platform**: classic ESP32 (unchanged from 001); QEMU esp32 for functional checks; Linux /
macOS host for the PC runtime and viewer

**Project Type**: embedded firmware + portable C library + Python CLI tool

**Performance Goals**: profiling + trace ≤ 5 % generation time (SC-003); `/stats` answers
immediately (no blocking measurement)

**Constraints**: no heap at inference (II), bit-identical logits (III), byte-identical console
output with trace off (FR-005), ≤ 8 KB extra static DRAM, ≥ 10 % headroom on all budgets (I)

**Scale/Scope**: 2 console commands, 3 event types, 7 profiling stages, ≤ 201 trace steps per
answer, 1 viewer with 5 transports

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Gate | Result (pre- and post-design) |
|-----------|------|--------|
| I. Hard On-Device Budget | budgets stated, report passes | ✔ arena unchanged (79,888 B / 128 KB); static DRAM 112,516 → 117,124 B of 180,736 (trace buffer 201 × 20 B + run-time stats); app 220,544 B (21.0 % of 1 MB); `budget_report.py` OK |
| II. Quantized, Allocation-Free | no heap at inference | ✔ trace buffer and probabilities are static members of `ut_console`; profiling uses no memory beyond `prof_us[7]` in `ut_ctx`. Float `logf`/softmax only for display values, outside the parity path |
| III. Reference Parity | parity unchanged | ✔ profiling only reads a clock; test compares logits with and without clock bit for bit; golden 24/24 bit-identical (host), 24/24 identical (QEMU) |
| IV. Reproducible Training & Export | format unchanged | ✔ no change to model format, exporter or training |
| V. Simplicity & Portability | SDK code isolated | ✔ all logic in portable `runtime/`; ESP-IDF calls only in `firmware/main/console_uart.c`; one code path (no compile-time variants), optional callbacks |

**Result**: PASS before Phase 0. **Post-design re-check** (after [research.md](research.md),
[data-model.md](data-model.md), [contracts/](contracts/observability.md),
[quickstart.md](quickstart.md)): PASS, nothing changed. Every design entity is static (TraceStep
array, SysStats on the stack of `/stats`, StageProfile in `ut_ctx`). The wire format needs no
library. No new dependency. The model format is untouched.

## Design decisions

Summary; rationale and alternatives are in [research.md](research.md) (R1–R8).

- **Clock hook in `ut_ctx`, not a global**: keeps the runtime free of global state; `NULL` =
  zero cost except one branch per stage.
- **Stages**: embed, norm, qkv (incl. KV quantization), attn, wo (+ residual), ffn (+ residual),
  head. Granularity is per stage over all layers (7 counters), enough to see attention growth
  with context vs. fixed matmul cost.
- **Trace printed after the answer**: keeps per-character timings undistorted by UART output and
  keeps the streamed answer byte-identical even with trace on.
- **Compact steps**: probabilities as Q16, entropy in millibit → 20 B per step, 201 steps.
- **Distribution only when trace is on**: timing per step is always recorded (cheap); softmax,
  top-3 and entropy only with `/trace an|json`.
- **CPU load**: idle-task run-time counter deltas against `esp_timer` per call of `/stats`
  (`vTaskGetInfo`, since `ulTaskGetRunTimeCounter` is not available in IDF 5.4).
- **QEMU over TCP**: `UT_QEMU_TCP` in `qemu_run.sh` (server, wait for client) so the viewer sees
  the boot banner; `--qemu` in the viewer starts and stops QEMU itself.
- **`utiny-host --console`**: same console on stdin/stdout, lets the viewer and tests run without
  an emulator.

## Project Structure

### Documentation (this feature)

```text
specs/002-observability/
├── plan.md              # This file
├── research.md          # Phase 0
├── data-model.md        # Phase 1
├── quickstart.md        # Phase 1
├── contracts/
│   └── observability.md # console commands, @ut events, runtime/console API additions
├── measurements.md      # results (QEMU, host)
└── tasks.md             # Phase 2
```

### Source Code (repository root)

```text
runtime/include/utiny.h          # clock hook, stage enum, ut_prof_*, ut_softmax_copy
runtime/src/forward.c            # PROF() marks, softmax copy
runtime/include/utiny_console.h  # ut_sys_stats, ut_trace_step, io callbacks
runtime/src/console.c            # /stats, /trace, recording, table + JSON output
runtime/host/utiny_host.c        # --console
runtime/tests/test_console_logic.c
firmware/main/console_uart.c|.h  # micros, sys_stats (heap, stack, CPU load), clock
firmware/main/main.c             # ctx.clock_us, console.arena_cap
firmware/sdkconfig.defaults      # FreeRTOS trace facility + run-time stats
tools/devlib.py                  # SerialLink / TcpLink / ExecLink
tools/observe.py                 # viewer
tools/device_parity.py           # --tcp, forces /trace aus
tools/qemu_run.sh                # UT_QEMU_TCP
training/tests/test_observe.py
Makefile                         # observe, observe-host
```

**Structure Decision**: The existing layout from 001 is unchanged:

- `runtime/` holds all observability logic and stays SDK-free.
- `firmware/main/` is the only place with ESP-IDF calls.
- `tools/` holds the host tools.
- Tests go next to the existing ones (`runtime/tests/`, `training/tests/`).

## Complexity Tracking

None. (`logf` in the console is display-only and not part of the parity-checked path.)
