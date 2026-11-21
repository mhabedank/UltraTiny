# Implementation Plan: Observability for Device and Model

**Branch**: `claude/observability-002` | **Date**: 2026-11-21 | **Spec**: [spec.md](spec.md)

## Summary

Observability is added in three thin layers without touching the model math: (1) the portable
runtime gets an optional microsecond clock hook that accumulates time per forward-pass stage,
plus a side-effect-free softmax for probabilities; (2) the platform-independent console gets
`/stats` and `/trace aus|an|json`, records per-step data in a static buffer and prints it after
the answer; (3) the firmware supplies `esp_timer`, heap, stack and per-core CPU load (FreeRTOS
idle-task run-time counters). On the PC, `tools/observe.py` drives the console (serial, TCP to
QEMU, or `utiny-host --console`) and renders the JSON events.

## Technical Context

**Language/Version**: C11 (runtime, firmware), Python 3.12 (viewer)

**Primary Dependencies**: ESP-IDF v5.4.1 (`esp_timer`, `heap_caps`, FreeRTOS run-time stats);
pyserial (dev dependency, already present)

**Testing**: CTest `test_console_logic` (stats, trace modes, byte-identity with trace off,
logit identity with profiling on), golden parity (host), `device_parity.py --tcp` in QEMU,
pytest `tests/test_observe.py` (parser + end-to-end against `utiny-host --console`)

**Target Platform**: classic ESP32 (unchanged); QEMU for functional checks

**Constraints**: no heap at inference, bit-identical logits, byte-identical console output with
trace off, ≤ 5 % time overhead

## Constitution Check

| Principle | Gate | Result |
|-----------|------|--------|
| I. Hard On-Device Budget | budgets stated, report passes | ✔ arena unchanged (79,888 B / 128 KB); static DRAM 112,516 → 117,124 B of 180,736 (trace buffer 201 × 20 B + run-time stats); app 220,544 B (21.0 % of 1 MB); `budget_report.py` OK |
| II. Quantized, Allocation-Free | no heap at inference | ✔ trace buffer and probabilities are static members of `ut_console`; profiling uses no memory beyond `prof_us[7]` in `ut_ctx`. Float `logf`/softmax only for display values, outside the parity path |
| III. Reference Parity | parity unchanged | ✔ profiling only reads a clock; test compares logits with and without clock bit for bit; golden 24/24 bit-identical (host), 24/24 identical (QEMU) |
| IV. Reproducible Training & Export | format unchanged | ✔ no change to model format, exporter or training |
| V. Simplicity & Portability | SDK code isolated | ✔ all logic in portable `runtime/`; ESP-IDF calls only in `firmware/main/console_uart.c`; one code path (no compile-time variants), optional callbacks |

**Result**: PASS.

## Design decisions

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

## Complexity Tracking

None. (`logf` in the console is display-only and not part of the parity-checked path.)
