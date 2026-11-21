---

description: "Task list for 002-observability"
---

# Tasks: Observability for Device and Model

**Input**: [spec.md](spec.md), [plan.md](plan.md), [contracts/observability.md](contracts/observability.md)

**Tests**: included (constitution: host build, unit tests, parity and budget are merge gates).

## Format: `[ID] [P?] [Story] Description`

## Phase 1: Foundational (runtime)

- [X] T001 Add `ut_prof_stage`, `ut_clock_us_fn`, `clock_us`/`prof_us` in `ut_ctx`, `ut_prof_reset`, `ut_prof_name`, `ut_softmax_copy` in runtime/include/utiny.h
- [X] T002 Add clock-only `PROF()` marks per stage and `ut_softmax_copy` in runtime/src/forward.c
- [X] T003 Test: logits bit-identical with and without clock, profile counters filled, softmax sums to 1 in runtime/tests/test_console_logic.c

## Phase 2: User Story 1 – `/stats` (P1)

- [X] T004 [US1] Add `ut_sys_stats`, optional `micros`/`sys_stats` callbacks and `arena_cap` in runtime/include/utiny_console.h
- [X] T005 [US1] Record per-step timings and per-answer snapshot (prefill, first char, total, min/max, end reason, profile) in runtime/src/console.c
- [X] T006 [US1] Implement `/stats` incl. HALT_ERROR and `@ut sys` event in runtime/src/console.c; list it in `/hilfe`
- [X] T007 [P] [US1] Firmware: `micros`, heap/min/largest block, stack high-water mark, per-core CPU load via idle-task run-time counters, CPU MHz in firmware/main/console_uart.c; set `ctx.clock_us` and `console.arena_cap` in firmware/main/main.c
- [X] T008 [P] [US1] Enable `CONFIG_FREERTOS_USE_TRACE_FACILITY` and `CONFIG_FREERTOS_GENERATE_RUN_TIME_STATS` in firmware/sdkconfig.defaults
- [X] T009 [US1] Tests for `/stats` values, last answer and HALT_ERROR in runtime/tests/test_console_logic.c

## Phase 3: User Story 2 – `/trace` (P1)

- [X] T010 [US2] Static `ut_trace_step` buffer (UT_MAX_ANSWER + 1), probability/top-3/entropy only when trace is on, in runtime/src/console.c
- [X] T011 [US2] `/trace aus|an|json`, table + summary, `@ut token`/`answer` events, abort handling in runtime/src/console.c
- [X] T012 [US2] Tests: trace off ⇒ output equals `"\r\n" + answer + "\r\n> "` computed directly with the runtime; trace on/json keep the answer bytes; Ctrl-C trace; mode switching in runtime/tests/test_console_logic.c

## Phase 4: User Story 3 – live viewer (P2)

- [X] T013 [P] [US3] `utiny-host --console` (POSIX stdin/stdout, clock hook) in runtime/host/utiny_host.c
- [X] T014 [P] [US3] `UT_QEMU_TCP` option (TCP serial server, monitor off) in tools/qemu_run.sh
- [X] T015 [US3] Transport links (`SerialLink`, `TcpLink`, `ExecLink`) and incremental UTF-8 decoding in tools/devlib.py
- [X] T016 [US3] Viewer with `--port/--tcp/--qemu/--host/--exec`, `--demo`, interactive mode, colours by probability, profile bars, `/stats` line, `--log` JSONL in tools/observe.py
- [X] T017 [US3] `make observe` / `make observe-host` in Makefile
- [X] T018 [P] [US3] `--tcp` and forced `/trace aus` in tools/device_parity.py
- [X] T019 [US3] Parser + end-to-end tests in training/tests/test_observe.py

## Phase 5: Polish & verification

- [X] T020 Host build + ctest + golden parity (`utiny-host --golden models/starter_golden.json`): 0 failures
- [X] T021 Firmware build for QEMU, `/stats` + `/trace an` shown, `device_parity.py --tcp` 24/24
- [X] T022 Budget report with firmware build; record numbers in measurements.md
- [X] T023 [P] README section "Observability"
- [ ] T024 Measure SC-003 (overhead ≤ 5 %) and real CPU load on a real ESP32 board (needs hardware)
