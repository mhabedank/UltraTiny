---

description: "Task list for 005-nodemcu-port"
---

# Tasks: UltraTiny PoC on NodeMCU (ESP8266)

**Input**: Design documents from `specs/005-nodemcu-port/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/, quickstart.md

**Tests**: Included where the constitution requires them: parity tests for every runtime change
(Principle III) and the budget gate (Principle I). No other test tasks.

**Organization**: Tasks are grouped by user story. The runtime change, the trained NodeMCU model
and the NodeMCU budget gate are foundational: every story needs them, and the constitution
requires every pull request to pass the budget report against the NodeMCU budgets.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: US1 = demo on the NodeMCU (P1), US2 = training + budget check (P2),
  US3 = device parity (P3)
- 🔌 = needs a real NodeMCU board (the user's hardware); cannot run in CI or the cloud container

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Skeleton for the new firmware and shared constants

- [X] T001 Create the `firmware-nodemcu/` skeleton per plan.md: `platformio.ini` (`platform = espressif8266` pinned to an exact version, `board = nodemcuv2`, `framework = arduino`, `board_build.f_cpu = 160000000L`, `build_flags = -ffp-contract=off -fno-fast-math -fsingle-precision-constant -I../runtime/include`, a local library `lib/utiny/library.json` (`srcDir`/`includeDir` pointing at ../runtime) so `../runtime/src/*.c` is compiled, `board_build.ldscript = eagle.flash.4m.ultratiny.ld` with `-Lld` (PlatformIO needs `.flash.4m` in the name)) in firmware-nodemcu/platformio.ini
- [X] T002 [P] Define `UT_MODEL_FLASH_OFFSET 0x58000`, `UT_MODEL_AREA_SIZE 0xA8000`, mapped address `0x40258000` and `UT_ARENA_MAX (36 * 1024)` per contracts/flash-layout.md and data-model.md `Board budget profile.firmware_arena` in firmware-nodemcu/include/layout.h
- [X] T003 [P] Add `firmware-nodemcu/.pio/` and `firmware-nodemcu/.pio-cache/` to .gitignore

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Word-access-safe runtime (contracts/runtime-image-access.md), the trained NodeMCU
model, and the NodeMCU budget gate in CI. All three block every user story.

**⚠️ CRITICAL**: No user story work can begin until this phase is complete

### Runtime: word-access safe image reads (Principle III: parity before and after)

- [X] T004 Record the baseline on the unchanged runtime: `cmake -S runtime -B build && cmake --build build -j`, then `ctest --test-dir build` and `./build/utiny-host --model models/starter.utny --golden models/starter_golden.json`; note the results in specs/005-nodemcu-port/measurements.md
- [X] T005 Add `static inline uint32_t ut_ld32(const void *p)` (aligned 32-bit load; with `UT_IMAGE_ACCESS_CHECK` assert `((uintptr_t)p & 3) == 0`) and a word-based `ut_dot_i8` that unpacks four int8 weights per load (little-endian), keeping `ut_matvec`'s float order unchanged, in runtime/src/mathx.h and runtime/src/mathx.c
- [X] T006 Change `ut_model_open` to copy the 64-byte header via `ut_ld32` before parsing, copy the meta JSON into a new `char meta_buf[256]` member (longer meta → `UT_ERR_SIZE`, `m->meta` points to the copy), and reject `d_model`, `d_ff` or `head_dim` not divisible by 4 with `UT_ERR_DIMS`, in runtime/src/model.c and runtime/include/utiny.h
- [X] T007 [P] Rewrite `ut_crc32` to read the data word by word via `ut_ld32`, masking a final partial word, in runtime/src/crc32.c
- [X] T008 Read token/position embeddings and all other image-resident int8/float data in the forward pass through `ut_ld32` (no direct dereference of `m->...` image pointers), in runtime/src/forward.c
- [X] T009 Add an `UT_IMAGE_ACCESS_CHECK` CMake option that builds `test_runtime` and the parity tests a second time with the define, plus a CTest `image_access_lint` that fails if `runtime/src/*.c` dereferences `->w[`, `->scale[`, `->alphabet[` or `tok_emb.w`/`pos_emb.w` outside `mathx.h`, in runtime/CMakeLists.txt
- [X] T010 Run the baseline commands from T004 again plus the access-check build; all golden cases must stay bit-identical (no change to runtime/tests/fixtures or models/starter_golden.json allowed); record in specs/005-nodemcu-port/measurements.md
- [ ] T011 [P] Confirm the legacy ESP32 firmware still builds with the changed runtime (`idf.py build` in firmware/ or the CI `firmware` job) and that `sizeof(ut_model)` growth (+256 B) fits its static RAM; note in specs/005-nodemcu-port/measurements.md

### NodeMCU model

- [X] T012 [P] Update the self-description facts from ESP32 to NodeMCU/ESP8266 (chip name, RAM ~80 KB, "läuft offline auf einer NodeMCU") in training/data/facts/starter.tsv and the matching expected answers in training/data/demo_prompts.tsv (FR-010)
- [X] T013 [P] Create the NodeMCU config with the values of data-model.md `NodeMCU model configuration.name`, `NodeMCU model configuration.model.d_model`, `NodeMCU model configuration.model.n_layers`, `NodeMCU model configuration.model.n_heads`, `NodeMCU model configuration.model.n_kv_heads`, `NodeMCU model configuration.model.d_ff`, `NodeMCU model configuration.model.ctx_len`, `NodeMCU model configuration.data.facts`, `NodeMCU model configuration.data.max_answer_len`, `NodeMCU model configuration.eval.demo_min` and `NodeMCU model configuration.eval.heldout_min` (train schedule copied from configs/starter.toml) in training/configs/nodemcu.toml
- [X] T014 Add a training test that loads configs/nodemcu.toml, checks the arena size from `reference.arena_size()` is ≤ 36,864 B (data-model.md `NodeMCU model configuration.model.ctx_len` rule) and that datagen keeps ≥ 99 % of the starter pairs, in training/tests/test_nodemcu_config.py
- [ ] T015 Train and export: `uv run ut pipeline --config configs/nodemcu.toml --out runs/nodemcu --device cpu`; copy the model, eval, run metadata and golden file to models/nodemcu.utny, models/nodemcu_eval.json, models/nodemcu_run.json, models/nodemcu_golden.json (demo ≥ 80 %, held-out ≥ 60 %, SC-002; if missed, iterate on noisy copies/steps as documented in 001 measurements and record each run)
- [ ] T016 Add a CTest `parity_nodemcu` that runs `utiny-host --model models/nodemcu.utny --golden models/nodemcu_golden.json` (normal and access-check build) in runtime/CMakeLists.txt, and the same step to the `runtime-host` job in .github/workflows/ci.yml

### NodeMCU budget gate (constitution: every pull request MUST pass it)

- [X] T017 Add board profiles to the budget report per contracts/budget-report.md, with the values of data-model.md `Board budget profile.model_max`, `Board budget profile.arena_max`, `Board budget profile.firmware_arena`, `Board budget profile.firmware_max`, `Board budget profile.mapped_window` and `Board budget profile.headroom` for `nodemcu` (default) and `esp32`, plus `"board"` in the `--json` output, in tools/budget_report.py
- [ ] T018 [P] Add tests for the budget report: nodemcu.utny passes, starter.utny fails on `arena` with `--board nodemcu` and passes with `--board esp32`, in training/tests/test_budget_report.py
- [X] T019 Switch the CI model gates: `runtime-host` runs the report with `--board nodemcu --model ../models/nodemcu.utny` and `--board esp32 --model ../models/starter.utny`; the legacy `firmware` job passes `--board esp32`, in .github/workflows/ci.yml

**Checkpoint**: Runtime is word-access safe and bit-identical; `models/nodemcu.utny` exists, passes host parity and the NodeMCU budget gate in CI.

---

## Phase 3: User Story 1 – Ask the NodeMCU and watch it answer (Priority: P1) 🎯 MVP

**Goal**: The PoC model answers demo prompts over the serial console on a NodeMCU, offline.

**Independent Test**: quickstart.md step 4 – flash firmware and model, ask demo prompts, check
banner and answers (incl. "Auf welchem Chip läufst du?").

- [X] T020 [US1] Write the linker script that limits the firmware (irom) to the 352 KB firmware area and leaves `0x58000`–`0xFFFFF` free for the model, based on the Arduino core's 4 MB layout (keep the core's SDK config sectors at the end of flash), in firmware-nodemcu/ld/eagle.flash.4m.ultratiny.ld
- [X] T021 [US1] Implement the platform layer: Wi-Fi off at boot (`WiFi.mode(WIFI_OFF)`, `WiFi.forceSleepBegin()`), `Serial.begin(115200)`, static 16-byte-aligned arena of `UT_ARENA_MAX`, `ut_model_open` on the mapped model area (`0x40258000`, size `UT_MODEL_AREA_SIZE`), boot check that `ut_arena_size()` ≤ `UT_ARENA_MAX` (else `HALT_ERROR` via `UT_ERR_ARENA`, data-model.md "State transitions"), `ut_console_io` callbacks (`read_byte` → `Serial.read`, `write` → `Serial.write`, `millis`, `micros`, `free_heap` → `ESP.getFreeHeap()`), one `ut_console_step` per `loop()` followed by `yield()` (research R8), in firmware-nodemcu/src/main.cpp
- [X] T022 [US1] Add the NodeMCU device status of data-model.md `Device status.board`, `Device status.cpu_mhz`, `Device status.free_heap`, `Device status.free_stack`, `Device status.reset_reason` and `Device status.per-core load` (printed as `-`) via the `sys_stats` callback, and the board name in the boot banner, in firmware-nodemcu/src/main.cpp (extend `ut_sys_stats`/banner hooks in runtime/include/utiny_console.h and runtime/src/console.c only if the existing fields can't carry them)
- [X] T023 [US1] Clamp the default and `/max` answer length so prompt + answer never exceed `ctx_len` (FR-006), keeping the existing behaviour for ctx 256 models, in runtime/src/console.c; add a case to runtime/tests/test_console_logic.c
- [X] T024 [P] [US1] Add `nodemcu-build`, `nodemcu-flash`, `nodemcu-flash-model` (magic `UTNY` + size ≤ data-model.md `Board budget profile.model_max` check, then `esptool.py write_flash 0x58000`) and `nodemcu-monitor` targets per contracts/flash-layout.md in Makefile
- [X] T025 [P] [US1] Add a `firmware-nodemcu` CI job (`pip install platformio`, `pio run` in firmware-nodemcu/) in .github/workflows/ci.yml
- [X] T026 [US1] Build locally/CI (`pio run`) and fix compile/link issues until the image links inside the 352 KB firmware area; record image size and static DRAM in specs/005-nodemcu-port/measurements.md
- [X] T027 [US1] Add `--pio-build` (firmware.bin size and static DRAM from the map/ELF) and the mapped-window check per contracts/budget-report.md to tools/budget_report.py, and run it in the `firmware-nodemcu` CI job (`--board nodemcu --model models/nodemcu.utny --pio-build firmware-nodemcu/.pio/build/nodemcuv2`) in .github/workflows/ci.yml
- [ ] T028 [US1] 🔌 Gate G-Speed (plan.md): flash firmware + model, send 5 demo prompts, record first-character latency, chars/s, free heap/stack from `/info` and `/stats` in specs/005-nodemcu-port/measurements.md; if first character > 2 s, apply research R7 mitigations in order (160 MHz check, `IRAM_ATTR` on `ut_dot_i8`/`ut_matvec`, batched prefill), **re-running T010 and T016 (host parity, bit-identical) after each runtime change**, and re-measure; if still over budget, stop and write a budget-amendment proposal instead of continuing
- [ ] T029 [US1] 🔌 Console and robustness checks on the board, recorded in specs/005-nodemcu-port/measurements.md: (a) FR-002 behaviour – a prompt with ä/ö/ü/ß displays and answers correctly, the abort key stops a running answer, empty input re-shows the prompt, an emoji is skipped with a notice, the same prompt twice gives the same answer; (b) FR-009 – erased model area, a model with one flipped byte, and models/starter.utny (arena too large for `UT_ARENA_MAX`) each give a `HALT_ERROR` message, the console stays responsive, single boot
- [X] T030 [US1] Write the NodeMCU build/flash/run guide (board identification via `esptool.py flash_id`, CP2102/CH340 drivers, Make targets, demo prompts, known limits: ctx 104, answers ≤ 72 chars) in firmware-nodemcu/README.md and link it from README.md (FR-011)

**Checkpoint**: The NodeMCU answers demo prompts offline; MVP complete.

---

## Phase 4: User Story 2 – Train a NodeMCU-sized model with the existing pipeline (Priority: P2)

**Goal**: A developer can retrain and check NodeMCU-sized models with one command; the budget
gate itself is already in place (T017–T019, T027).

**Independent Test**: quickstart.md steps 2 and 3 – train with configs/nodemcu.toml twice
(byte-identical on CPU), budget report passes for nodemcu.utny and fails for starter.utny.

- [X] T031 [P] [US2] Update the `budget` target to default to the NodeMCU profile and add a `nodemcu` training target (`uv run ut pipeline --config configs/nodemcu.toml --out runs/nodemcu`) in Makefile
- [ ] T032 [US2] Reproducibility check: run the NodeMCU pipeline twice on CPU with the same seed, confirm byte-identical model files, record in specs/005-nodemcu-port/measurements.md
- [X] T033 [P] [US2] Document the NodeMCU config and budgets in training/README.md

**Checkpoint**: NodeMCU models can be reproduced and checked with one command each.

---

## Phase 5: User Story 3 – Prove the NodeMCU gives exactly the reference answers (Priority: P3)

**Goal**: 100 % of the golden cases give identical text on the board (SC-001).

**Independent Test**: quickstart.md step 5 – `device_parity.py` against a flashed NodeMCU.

- [X] T034 [P] [US3] Make the device scripts board-neutral: replace ESP-IDF/`parttool.py` hints with a `--board nodemcu|esp32` option that only changes the printed flash instructions, in tools/devlib.py, tools/model_swap_check.py and tools/device_smoke.py
- [X] T035 [US3] Adjust `device_parity.py` defaults for the slower board (larger per-answer timeout, `--char-delay` suitable for 115200 baud without flow control) in tools/device_parity.py
- [ ] T036 [US3] 🔌 Run `tools/device_parity.py --golden models/nodemcu_golden.json` on the board; on any mismatch, compare per-step logits with `utiny-host` to locate the stage (soft-float vs. host) and fix it in the runtime with a host golden test; record the result in specs/005-nodemcu-port/measurements.md
- [ ] T037 [US3] 🔌 Model swap without rebuilding: flash runtime/tests/fixtures/tiny.utny with `make nodemcu-flash-model`, then models/nodemcu.utny again, confirm banner and answers change (001 User Story 3 on the NodeMCU); record in specs/005-nodemcu-port/measurements.md

**Checkpoint**: Device parity proven; all user stories independently verified.

---

## Phase 6: Polish & Cross-Cutting Concerns

- [ ] T038 🔌 Endurance: `tools/soak.py --count 100` (≥ 1 h), check no reset and stable free heap (SC-005, FR-012); record in specs/005-nodemcu-port/measurements.md
- [ ] T039 🔌 Fresh-checkout walkthrough of quickstart.md steps 1–4 with a pre-built model, timed (SC-006 < 30 min); fix any doc gaps in specs/005-nodemcu-port/quickstart.md and firmware-nodemcu/README.md
- [X] T040 [P] Mark the ESP32 docs as legacy (one note at the top pointing to firmware-nodemcu/) in firmware/README.md and specs/001-esp32-tiny-lm/quickstart.md
- [ ] T041 Complete specs/005-nodemcu-port/measurements.md with the final table (budgets, speed, parity, soak, walkthrough) and update the "Results" section of README.md

---

## Dependencies & Execution Order

### Phase dependencies

- **Setup (Phase 1)**: none
- **Foundational (Phase 2)**: runtime tasks T004–T011 and model tasks T012–T016 can start immediately; the budget gate T017–T019 needs models/nodemcu.utny (T015). Blocks all stories.
- **US1 (Phase 3)**: after Phase 2. T027 needs T026's build output. T028/T029 need the user's board.
- **US2 (Phase 4)**: after Phase 2; independent of US1.
- **US3 (Phase 5)**: after US1's firmware runs on the board (T028).
- **Polish (Phase 6)**: after the stories it measures.

### Within Phase 2

- T004 → T005 → (T006, T007 in parallel, T008) → T009 → T010 → T011
- T012, T013 in parallel → T014 → T015 → T016 (T016 also needs T010)
- T015 → T017 → T019, with T018 in parallel to T019

### Within US1

- T020 → T021 → T022 → T026 → T027 → T028 → T029; T023, T024, T025 in parallel with T020–T022; T030 after T028

---

## Parallel Example

```text
# Phase 2, two independent tracks, then the gate:
Track A (runtime):  T004 → T005 → T006 ∥ T007 → T008 → T009 → T010
Track B (model):    T012 ∥ T013 → T014 → T015
Gate:               T017 → T018 ∥ T019

# US1 once Phase 2 is done:
T024 (Makefile) ∥ T025 (CI job) ∥ T023 (console clamp)  while  T020 → T021 → T022

# US2 alongside US1:
T031 ∥ T033, then T032
```

---

## Implementation Strategy

### MVP first (User Story 1)

1. Phase 1 + Phase 2 (runtime change, model and budget gate, all verifiable in CI without
   hardware)
2. US1 up to T027 (firmware builds, links and passes the firmware budget gate in CI)
3. **Hand over to the user for T028 (gate G-Speed on the board).** Stop and decide on mitigations
   or a budget amendment before continuing if the first character is over 2 s.
4. Demo the PoC.

### Incremental delivery

- US2 can be done in the cloud container while the user tests US1 on the board.
- US3 and the 🔌 polish tasks need the board and can run in one hardware session.

### Hardware tasks (🔌)

T028, T029, T036, T037, T038, T039 need a NodeMCU on the user's machine. Everything else runs in
CI or the cloud container.
