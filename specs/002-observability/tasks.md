---

description: "Task list for 002-observability"
---

# Tasks: Observability for Device and Model

**Input**: Design documents from `/specs/002-observability/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/observability.md,
quickstart.md

**Tests**: Included. The constitution makes host build, unit tests, parity tests (III) and the
budget report (I) merge gates. FR-005 and FR-006 are verified by tests.

**Organization**: Tasks are grouped by user story (spec.md: US1 `/stats` P1, US2 `/trace` P1,
US3 live viewer P2). Field constraints are cited from [data-model.md](data-model.md) as
`Entity.field`.

**Status note**: The implementation was done before this list was aligned with the Spec Kit
template (see plan.md). Completed tasks are marked `[X]`; the Phase 0/1 design documents were
added afterwards (T024).

**Task IDs**: IDs were kept stable when this list was aligned with the template. Within the
US1 and US2 phases, the test tasks (T009, T012) are listed first by the template's convention but
carry higher IDs. The execution order is the order listed.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (US1, US2, US3)

## Path Conventions

`runtime/` (portable C11), `firmware/` (ESP-IDF), `tools/` (Python), `training/tests/` (pytest),
repository root (Makefile, README.md). The layout is unchanged from 001; see plan.md →
Project Structure.

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Nothing to initialize. The project, toolchains, CI and test harnesses come from
001. The firmware configuration for CPU-load measurement is part of US1 (T008).

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: The runtime profiling hook and display probabilities. US1 (profile in `/stats`) and
US2 (probabilities in the trace) depend on them.

- [X] T001 Add `ut_prof_stage`, `ut_clock_us_fn`, the StageProfile fields `clock_us` and `prof_us` (data-model.md `StageProfile.clock_us`, `StageProfile.prof_us`), `ut_prof_reset`, `ut_prof_name` and `ut_softmax_copy` to runtime/include/utiny.h
- [X] T002 Add clock-only `PROF()` marks for the seven stages and `ut_softmax_copy` in runtime/src/forward.c (research.md R1/R2; the invariant of data-model.md `StageProfile.clock_us` is bit-identical logits)
- [X] T003 Test: logits bit-identical with and without `clock_us`, counters filled and resettable, softmax sums to 1 and keeps the argmax, in runtime/tests/test_console_logic.c

**Checkpoint**: Profiling works on the host and parity is unchanged. The user stories can start.

---

## Phase 3: User Story 1 – See how the device is doing (Priority: P1) 🎯 MVP

**Goal**: `/stats` shows memory, CPU load, uptime/clock, the last answer's timings and the stage
profile (FR-001, FR-002).

**Independent Test**: quickstart.md Scenario C, steps 1 and 3. `/stats` shows plausible values
before and after a question, and also in HALT_ERROR.

### Tests for User Story 1

- [X] T009 [US1] Tests for `/stats` with fake `sys_stats` and `micros` in runtime/tests/test_console_logic.c:
  - before the first answer: "Letzte Antwort: noch keine", no profile (US1 acceptance 1);
  - system values, arena/KV, last answer and profile;
  - no `@ut` outside json mode;
  - HALT_ERROR.

### Implementation for User Story 1

- [X] T004 [US1] Add `ut_sys_stats` with all SysStats fields (data-model.md `SysStats.heap_free`, `.heap_min`, `.heap_largest`, `.stack_free`, `.cpu_load`, `.uptime_ms`, `.cpu_mhz`; < 0 = unknown), the optional `micros`/`sys_stats` callbacks appended to `ut_console_io`, and `arena_cap` to runtime/include/utiny_console.h
- [X] T005 [US1] Record per-step timing (data-model.md `TraceStep.tok`, `TraceStep.pos`, `TraceStep.us`, always recorded) and the end-of-answer snapshot (data-model.md `AnswerSummary.n`, `.prefill`, `.ctx_used`, `.aborted`, `.end`, `.first_us`, `.total_us`, `.us_min`, `.us_max`, `.prof_us`), resetting the profile at Enter, in runtime/src/console.c
- [X] T006 [US1] Implement `/stats` (pre-fill SysStats with −1, text output, `@ut sys` event in json mode, HALT_ERROR path) and list it in `/hilfe` in runtime/src/console.c
- [X] T007 [P] [US1] Firmware callbacks in firmware/main/console_uart.c and firmware/main/console_uart.h, and `ctx.clock_us` / `console.arena_cap` in firmware/main/main.c. Sources per data-model.md `SysStats` (research.md R3/R4); `SysStats.cpu_load` uses `vTaskGetInfo` on the idle task of each core.
- [X] T008 [P] [US1] Enable `CONFIG_FREERTOS_USE_TRACE_FACILITY` and `CONFIG_FREERTOS_GENERATE_RUN_TIME_STATS` in firmware/sdkconfig.defaults and add `heap` to `REQUIRES` in firmware/main/CMakeLists.txt

**Checkpoint**: `/stats` works on the host (unknown values shown as `?`) and in QEMU.

---

## Phase 4: User Story 2 – See how sure the model is (Priority: P1)

**Goal**: `/trace aus|an|json` with a per-character table or JSON events. With trace `aus` the
answer output is byte-identical to 001 (FR-003, FR-004, FR-005, FR-007).

**Independent Test**: quickstart.md Scenario C, steps 2, 4 and 5, and Scenario A (ctest).

### Tests for User Story 2

- [X] T012 [US2] Tests in runtime/tests/test_console_logic.c:
  - trace `aus` ⇒ output equals `"\r\n" + answer + "\r\n> "`, computed directly with the runtime;
  - `an`/`json` keep the answer bytes;
  - one `token` event per step plus one `answer` event;
  - Ctrl-C gives `Ende: abort` with exactly the produced steps;
  - mode switching and invalid argument.

### Implementation for User Story 2

- [X] T010 [US2] Static `ut_trace_step` array of `UT_MAX_ANSWER + 1` entries, with the distribution fields (data-model.md `TraceStep.p`, `TraceStep.top`, `TraceStep.top_p`, `TraceStep.h_mbit`) computed only when TraceMode ≠ `aus`, in runtime/include/utiny_console.h and runtime/src/console.c
- [X] T011 [US2] `/trace` command and TraceMode (data-model.md TraceMode), table + summary, `@ut token`/`answer` events per contracts/observability.md, printed after the answer (also on Ctrl-C), in runtime/src/console.c

**Checkpoint**: The model trace works on the host and in QEMU; trace `aus` is unchanged.

---

## Phase 5: User Story 3 – Watch it live from the PC (Priority: P2)

**Goal**: The viewer shows answers coloured by probability, plus timings, the least certain
positions, the profile and system values; it writes an optional JSONL log (FR-009).

**Independent Test**: quickstart.md Scenario B (`make observe-host`) and Scenario D
(`make observe`).

### Tests for User Story 3

- [X] T019 [US3] Parser tests and an end-to-end test against `utiny-host --console` in training/tests/test_observe.py

### Implementation for User Story 3

- [X] T013 [P] [US3] `utiny-host --console` (POSIX stdin/stdout, non-blocking read, clock hook, `uptime_ms` only) in runtime/host/utiny_host.c
- [X] T014 [P] [US3] `UT_QEMU_TCP` option (`-serial tcp::PORT,server=on,wait=on`, `-monitor none`) in tools/qemu_run.sh (research.md R7)
- [X] T015 [US3] Transport links `SerialLink`, `TcpLink`, `ExecLink` and incremental UTF-8 decoding in tools/devlib.py, keeping the `Device(port)` API
- [X] T016 [US3] Viewer in tools/observe.py:
  - options `--port/--tcp/--qemu/--host/--exec`, `--demo`, interactive mode;
  - colours from `p`, profile bars, `sys` line, `--log` JSONL;
  - starts and stops QEMU itself with `--qemu`;
  - research.md R8; events per contracts/observability.md.
- [X] T017 [US3] Targets `observe` and `observe-host` in Makefile
- [X] T018 [P] [US3] `--tcp` option and forced `/trace aus` (TraceMode persists across reconnects, data-model.md TraceMode) in tools/device_parity.py

**Checkpoint**: All user stories work independently.

---

## Phase 6: Polish & Cross-Cutting Concerns

- [X] T020 Host build + ctest + golden parity (`utiny-host --golden models/starter_golden.json`): 0 failures
- [X] T021 Firmware build for QEMU: show `/stats` + `/trace an`, and `device_parity.py --tcp` gives 24/24
- [X] T022 Budget report with the firmware build; record the numbers in specs/002-observability/measurements.md
- [X] T023 [P] "Observability" section in README.md and a pointer from specs/001-esp32-tiny-lm/contracts/serial-console.md
- [X] T024 [P] Phase 0/1 design documents: specs/002-observability/research.md, data-model.md, quickstart.md; align plan.md with the template
- [X] T025 Run the quickstart.md validation in the container: Scenarios A–E. Results:
  - Scenario D: `make observe` 5/5 in QEMU, QEMU stopped afterwards;
  - Scenario C step 4: Ctrl-C in QEMU gives a trace with `Ende: abort` over the 6 produced
    characters.
- [X] T027 [P] Default JSONL log for `make observe` / `make observe-host` (`OBSERVE_LOG`, logs/ git-ignored), `session` header event with source/model/git revision, `Log:` hint at the end, in Makefile, tools/observe.py, .gitignore, README.md and contracts/observability.md
- [ ] T026 **Deferred** (no board available; release gate, not merge gate): quickstart.md Scenario F on a real ESP32. Measure SC-003 (trace/profiling overhead ≤ 5 %) and the core-1 load while generating; record in specs/002-observability/measurements.md. Until then, the emulator logs from T027 serve as the observability record.

---

## Dependencies & Execution Order

### Phase Dependencies

- **Foundational (T001–T003)** blocks US1 (profile in `/stats`) and US2 (`ut_softmax_copy`).
- **US1** and **US2** both edit runtime/src/console.c, so they run sequentially in one working
  copy. They are independently testable. US2 reuses the step recording from T005.
- **US3** depends on US2's JSON events (T011) and on US1's `sys` event (T006).
- **Polish** comes after all stories. T026 needs hardware and is independent of the others.

### Within Each User Story

Header/types → console logic → firmware/tools → tests run green.

### Parallel Opportunities

- T007 and T008 (firmware) run in parallel with T005/T006 (runtime console).
- T013, T014 and T018 touch different files and run in parallel; T015 comes before T016.
- T023 and T024 (documentation) run in parallel.

## Parallel Example: User Story 3

```text
Task: "T013 utiny-host --console in runtime/host/utiny_host.c"
Task: "T014 UT_QEMU_TCP in tools/qemu_run.sh"
Task: "T018 --tcp in tools/device_parity.py"
```

## Implementation Strategy

1. **MVP = Foundational + US1**: `/stats` gives memory, CPU and timing visibility in QEMU.
2. **+ US2**: model trace; verify byte identity and parity before going on.
3. **+ US3**: PC viewer on top of the stable event format.
4. **Polish**: documentation, quickstart validation, budget; then the hardware measurement (T026).
