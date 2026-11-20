---

description: "Task list for 001-esp32-tiny-lm"
---

# Tasks: Tiny Language Model Demo on a Classic ESP32

**Input**: Design documents from `/specs/001-esp32-tiny-lm/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/, quickstart.md

**Tests**: Included. The constitution makes parity tests (Principle III), budget reports
(Principle I) and host builds mandatory quality gates, and FR-014 requires a PC reference.

**Organization**: Tasks are grouped by user story. Because the device demo (US1) needs a trained
model, the Foundational phase contains a minimal end-to-end model path (alphabet → data →
train → export → reference → C runtime) on a small fact subset; US2 then turns it into the full,
reproducible GPU/CPU pipeline on the complete knowledge base.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (US1, US2, US3)

## Path Conventions

`training/` (Python, uv), `runtime/` (portable C11), `firmware/` (ESP-IDF), `tools/`, repo root
— as defined in plan.md → Project Structure.

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Project skeletons, tooling, CI scaffold

- [ ] T001 Create the directory layout from plan.md (training/, runtime/, firmware/, tools/) with placeholder README.md files and a root Makefile with empty targets `test`, `flash-model`, `budget` in Makefile
- [ ] T002 Initialize the uv project with Python 3.12, deps torch>=2.5, numpy, tomli-w, pytest, ruff and console script `ut = ultratiny.cli:main` in training/pyproject.toml
- [ ] T003 [P] Create runtime/CMakeLists.txt that calls `idf_component_register` when `ESP_PLATFORM` is set, else builds static lib `utiny`, executable `utiny-host` and enables CTest; flags `-std=c11 -Wall -Wextra -Werror -ffp-contract=off -fno-fast-math -fsingle-precision-constant`
- [ ] T004 [P] Create the ESP-IDF project skeleton with `EXTRA_COMPONENT_DIRS ../runtime` in firmware/CMakeLists.txt and an empty app_main in firmware/main/main.c plus firmware/main/CMakeLists.txt
- [ ] T005 [P] Add partition table per research.md R7 (nvs, phy_init, factory 1 MB, model data/0x40 2 MB @0x110000) in firmware/partitions.csv
- [ ] T006 [P] Add sdkconfig defaults: target esp32, custom partition table, 4 MB flash, `CONFIG_BT_ENABLED=n`, console UART0 115200, CPU 240 MHz, compiler optimize for performance in firmware/sdkconfig.defaults
- [ ] T007 [P] Configure ruff (lint+format) in training/pyproject.toml and add .editorconfig and a clang-format config in .clang-format
- [ ] T008 [P] Create CI workflow with jobs `python` (uv sync, ruff, pytest), `runtime-host` (cmake build + ctest), `firmware` (espressif/idf pinned image, `idf.py build`) in .github/workflows/ci.yml
- [ ] T009 [P] Create DATA_LICENSES.md listing sources `wikidata` (CC0 1.0) and `own` (MIT) with the rule from constitution IV

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Shared format, math and a minimal trained model that every story needs

**⚠️ CRITICAL**: No user story work can begin until this phase is complete

### Shared definitions (Python)

- [ ] T010 [P] Implement the alphabet with reserved IDs and code-point table per data-model.md Alphabet (IDs 0–4 reserved, vocab ≤ 96) and research.md R2 symbol set; encode/decode with `<unk>` fallback in training/src/ultratiny/alphabet.py
- [ ] T011 [P] Implement shared quantization rules (per-row absmax/127, round-half-away-from-zero, clamp ±127; per-vector activation quantization) per contracts/model-format.md "Quantization rules" in training/src/ultratiny/quant.py
- [ ] T012 [P] Define ModelConfig dataclass and TOML loader with fields per data-model.md ModelConfig (vocab_size, d_model, n_layers, n_heads, n_kv_heads, head_dim, d_ff, ctx_len, norm_eps) and validation `d_model % n_heads == 0`, `n_kv_heads == 1` in training/src/ultratiny/config.py
- [ ] T013 [P] Create configs training/configs/v1.toml (R1 sizes, full data), training/configs/starter.toml (R1 sizes, starter data only) and training/configs/tiny-test.toml (d=32, 1 layer, 4 heads, ctx 64), each listing its fact/template files and the allowed topics
- [ ] T014 [P] Unit tests for alphabet round-trip incl. ä ö ü Ä Ö Ü ß and `<unk>`, and quantization edge cases (zero row, ±max, .5 rounding) in training/tests/test_alphabet_quant.py

### Minimal data + model path

- [ ] T015 [P] Create a starter fact set (~200 facts, relations `hauptstadt_von`, `element_symbol`, `wer_bist_du`) as TSV with columns per data-model.md Fact (id, topic, relation, subject, object, source) in training/data/facts/starter.tsv, plus the topic list referenced by data-model.md Fact.topic in training/data/topics.toml
- [ ] T016 [P] Create starter German templates per data-model.md QuestionTemplate/AnswerTemplate (≥ 8 question templates per relation, ≥ 2 with `split = heldout`, ≥ 1 answer template) in training/data/templates/starter.toml
- [ ] T017 Implement datagen: load facts/templates, validate data-model.md Fact.id (unique), Fact.topic (listed in training/data/topics.toml), Fact.relation (has templates), Fact.subject/Fact.object (alphabet characters only) and Fact.source (listed in DATA_LICENSES.md); validate data-model.md QuestionTemplate.relation (matches a Fact.relation) and QuestionTemplate.text (contains `{subject}` and/or `{object}`); build TrainingExample sequences `<bos> q <sep> a <eos>` with length ≤ ctx_len (data-model.md TrainingExample), add case/punctuation/typo noise, write train.txt / heldout.jsonl / demo.jsonl / dataset.sha256 in training/src/ultratiny/datagen.py
- [ ] T018 Implement the PyTorch model per research.md R1 (tied emb, learned pos emb, pre-RMSNorm, MQA, ReLU FFN, no biases) with optional fake-quant hooks for weights/activations/KV in training/src/ultratiny/model.py
- [ ] T019 Implement a basic training loop (AdamW, cosine LR, loss on answer tokens only, seeding of python/numpy/torch, device auto mps→cpu) writing ckpt.pt and run.json with data-model.md RunMetadata (config, seed, data hash, git commit, device, wall time) in training/src/ultratiny/train.py
- [ ] T020 Implement UTNY v1 exporter (64-byte header, alphabet block, meta JSON, tensor order, 4-byte alignment, CRC-32s) exactly per contracts/model-format.md in training/src/ultratiny/export.py
- [ ] T021 Implement the NumPy bit-exact reference per research.md R4/R5 (int8×int8→int32 matmuls, per-vector act quant, int8 KV with per-position scales, float32 RMSNorm/softmax with sequential reductions, project-owned `exp` polynomial, greedy + xorshift sampling) loading UTNY files in training/src/ultratiny/reference.py
- [ ] T022 Implement the `ut` CLI with subcommands datagen/train/export/golden and a minimal `pipeline` (datagen → train → export → golden → model budget check) with common options `--seed`, `--device` per contracts/training-cli.md in training/src/ultratiny/cli.py
- [ ] T023 Implement golden vector generation (prompts → per-step tokens + logits JSON) in training/src/ultratiny/golden.py
- [ ] T024 [P] Tests: export→reference round trip on a random tiny-test model, header/CRC fields, reference vs PyTorch fake-quant forward agreement (argmax equal, logits within 1e-3) in training/tests/test_export_reference.py

### Portable C runtime (host-testable)

- [ ] T025 [P] Write the public API exactly per contracts/runtime-api.md (ut_status codes, ut_model, ut_ctx, open/arena_size/ctx_init/reset/feed/rewind/logits/argmax/sample, alphabet mapping) in runtime/include/utiny.h
- [ ] T026 [P] Implement CRC-32 (IEEE) in runtime/src/crc32.c
- [ ] T027 [P] Implement project-owned math (`ut_expf` polynomial identical to reference, RMSNorm, softmax with sequential sums, int8 dot product, per-vector quantization) in runtime/src/mathx.c
- [ ] T028 Implement model loader and validation (all rejection rules and distinct error codes per contracts/model-format.md "Validation rules"), arena size computation per research.md R3 in runtime/src/model.c
- [ ] T029 Implement forward pass for one token with KV-cache append (data-model.md Session.kv: int8 K/V + per-position scales in the arena), `ut_feed` returning `UT_ERR_CONTEXT_FULL` at ctx_len, `ut_rewind` (data-model.md Session.pos), argmax and xorshift sampling in runtime/src/forward.c
- [ ] T030 [P] Implement UTF-8 decode/encode and code point ↔ token mapping via the model's alphabet table in runtime/src/alphabet.c
- [ ] T031 Implement host CLI `utiny-host` (`--model`, `--prompt`, `--greedy|--sample`, `--max`, `--golden` parity check with exit code) per contracts/runtime-api.md in runtime/host/utiny_host.c
- [ ] T032 [P] Generate and commit a tiny random-weight fixture model and its golden vectors (via `ut export`/`ut golden` with tiny-test config, fixed seed) in runtime/tests/fixtures/tiny.utny and runtime/tests/fixtures/tiny_golden.json
- [ ] T033 C unit tests: loader accepts fixture and rejects each corruption (bad magic, version, header CRC, payload CRC, truncated, oversized dims); feed/rewind/context-full behavior; parity vs tiny_golden.json bit-exact in runtime/tests/test_runtime.c (registered in runtime/CMakeLists.txt)

- [ ] T034 Implement the budget report: model bytes and arena bytes from the model header (via reference sizing), plus app/static DRAM from `idf.py size --format json` when a firmware build exists; fail on < 10% headroom per data-model.md BudgetReport; add `budget` target in Makefile and run it in the `runtime-host` and `firmware` CI jobs in tools/budget_report.py and .github/workflows/ci.yml
- [ ] T035 Train the starter model end to end with `uv run ut pipeline --config configs/starter.toml --out runs/starter` (M3 or CPU), verify `utiny-host --golden` passes, and document the command in training/README.md

**Checkpoint**: Starter model answers starter questions on the host via `utiny-host`, bit-identical to the reference.

---

## Phase 3: User Story 1 - Ask the board and watch it answer (Priority: P1) 🎯 MVP

**Goal**: Firmware runs the model from flash and streams German answers over the serial console.

**Independent Test**: Flash firmware + starter (or released) model, radios off, type a demo
prompt → answer streams; second prompt works without reset (quickstart.md Scenario A).

### Tests for User Story 1

- [ ] T036 [P] [US1] Host test of the console line-editing logic (printable echo, unknown char notice once per line, Backspace → rewind, empty Enter, too-long line, Ctrl-C abort) using a fake I/O backend in runtime/tests/test_console_logic.c (registered as CTest in runtime/CMakeLists.txt)
- [ ] T037 [P] [US1] On-device smoke script: open serial port, wait for banner, type 5 demo prompts at human speed (100 ms per character) and check answers and `/info` first-char latency/chars/s against SC-001/SC-002; additionally send one prompt at once (paste) and report its latency separately (informational) in tools/device_smoke.py
- [ ] T038 [P] [US1] On-device parity script (SC-006): set `/modus gierig`, `/max` to the golden length, type every golden prompt and compare the streamed answer byte-for-byte with the reference text in golden.json; exit ≠ 0 on any mismatch in tools/device_parity.py

### Implementation for User Story 1

- [ ] T039 [US1] Implement the console state machine (READY/TYPING/GENERATING/HALT_ERROR, incremental prefill while typing, reserve of 32 positions, max answer length default 200) per data-model.md Session.state/Session.pos/Session.input_len and contracts/serial-console.md, as platform-independent code with the I/O callback API from contracts/runtime-api.md "Console" in runtime/include/utiny_console.h and runtime/src/console.c
- [ ] T040 [US1] Implement model partition lookup + `esp_partition_mmap` (data, read-only) returning pointer/size in firmware/main/model_partition.c
- [ ] T041 [US1] Implement UART0 I/O backend (non-blocking read, Ctrl-C detection during generation, UTF-8 output) in firmware/main/console_uart.c
- [ ] T042 [US1] Wire app_main: no Wi-Fi/BT init, open model, static arena (`static uint8_t arena[UT_ARENA_MAX]`, size checked via `ut_arena_size`), print banner per contracts/serial-console.md, run console loop; on model error print `FEHLER: Modell ungültig (…)` and enter HALT_ERROR without reboot in firmware/main/main.c
- [ ] T043 [US1] Implement commands `/hilfe`, `/info` (header fields, arena use, first-char latency ms, chars/s, free heap), `/modus gierig|zufall [seed] [temp]`, `/max <n>` per contracts/serial-console.md and data-model.md Session.mode in runtime/src/console.c
- [ ] T044 [US1] Add `flash-model` target wrapping `parttool.py --partition-name model write_partition --input $(MODEL)` and `monitor` shortcut in Makefile
- [ ] T045 [US1] Create the demo prompt list with expected German answers (≥ 30 entries, covering every relation) in training/data/demo_prompts.tsv
- [ ] T046 [US1] Flash the starter model to a real board, run tools/device_smoke.py, run tools/device_parity.py, record measured chars/s and first-char latency in specs/001-esp32-tiny-lm/measurements.md
- [ ] T047 [US1] Only if T046 measurements miss SC-001/SC-002: apply the research.md R6 fallbacks (batched prefill of 16 tokens, dual-core row split) and re-measure, keeping parity green, in runtime/src/forward.c

**Checkpoint**: MVP — the board answers German questions offline over serial.

---

## Phase 4: User Story 2 - Train and export a model on a PC (Priority: P2)

**Goal**: One command trains the full knowledge base on the M3 GPU (CPU fallback), evaluates via
the quantized reference, and exports a reproducible release model.

**Independent Test**: `uv run ut pipeline --config configs/v1.toml --out runs/v1` finishes
≤ 2 h on M3 with eval/budget reports; two CPU runs give byte-identical model files
(quickstart.md Scenario B).

### Tests for User Story 2

- [ ] T048 [P] [US2] Determinism test: tiny-test pipeline run twice on CPU with same seed → identical model.utny SHA-256 in training/tests/test_determinism.py
- [ ] T049 [P] [US2] Datagen tests: held-out templates never appear in train.txt (data-model.md QuestionTemplate.split), every relation has ≥ 8 question templates, invalid characters/sources are rejected (data-model.md Fact.subject, Fact.object, Fact.source) in training/tests/test_datagen.py

### Implementation for User Story 2

- [ ] T050 [P] [US2] Implement the one-off Wikidata snapshot fetcher (SPARQL queries for countries/capitals/continents, German states, cities, rivers, mountains, chemical elements, planets/moons, inventions) writing TSV with `source = wikidata:<QID>` (data-model.md Fact.source) in training/tools/fetch_wikidata.py
- [ ] T051 [US2] Run the fetcher once and commit the snapshot (~2,700 facts) in training/data/facts/*.tsv
- [ ] T052 [P] [US2] Write own German facts about the ESP32 and the project (~150, `source = own`) in training/data/facts/esp32_projekt.tsv
- [ ] T053 [P] [US2] Write German question/answer templates for every relation (≥ 8 questions, ≥ 2 held out; data-model.md QuestionTemplate.split, QuestionTemplate.relation, QuestionTemplate.text) in training/data/templates/*.toml
- [ ] T054 [US2] Add MPS-specific handling (`torch.mps.manual_seed`, deterministic flags where supported, CPU fallback for unsupported ops, device recorded in data-model.md RunMetadata) in training/src/ultratiny/train.py
- [ ] T055 [US2] Add quantization-aware fine-tuning phase (fake-quant weights/activations/KV, STE) triggered when quantized eval drops > 2 pp in training/src/ultratiny/train.py
- [ ] T056 [US2] Implement evaluation via the quantized reference: demo set (SC-003, normalized edit distance ≤ 0.1) and held-out phrasings (SC-004) → eval.json per data-model.md EvalSet in training/src/ultratiny/evaluate.py
- [ ] T057 [US2] Implement `ut eval` and extend `ut pipeline` with eval and QAT (datagen → train → export → eval → golden → budget check; non-zero exit on failed thresholds) per contracts/training-cli.md in training/src/ultratiny/cli.py
- [ ] T058 [US2] Train the release model `runs/v1` on the M3, check eval thresholds (demo ≥ 0.80, held-out ≥ 0.60); repeat the MPS run with the same seed and confirm eval results agree within ±1 pp; record results and training times in specs/001-esp32-tiny-lm/measurements.md

**Checkpoint**: Reproducible release model + eval report; US1 runs with it unchanged.

---

## Phase 5: User Story 3 - Flash a new model without rebuilding the firmware (Priority: P3)

**Goal**: Models are swapped by flashing only the model partition; bad models are rejected safely.

**Independent Test**: Flash firmware once, flash two different models in turn, then a corrupted
one → banners change accordingly, corrupt model shows error, no reboot loop (quickstart.md
Scenario D).

### Tests for User Story 3

- [ ] T059 [P] [US3] Host test: loader rejects a model whose payload exceeds the partition size and one whose arena exceeds `UT_ARENA_MAX` with distinct codes in runtime/tests/test_runtime.c
- [ ] T060 [P] [US3] Device script: flash model A, check banner; flash model B, check banner; flash truncated file, check `FEHLER` and that no second boot banner appears within 30 s in tools/model_swap_check.py

### Implementation for User Story 3

- [ ] T061 [US3] Show model name, format version, n_params and meta (git commit, train date from the meta JSON) in the banner and `/info` in runtime/src/console.c
- [ ] T062 [US3] Make HALT_ERROR fully responsive (`/hilfe`, `/info` show error code + text; watchdog fed; no panic/reboot) in firmware/main/main.c
- [ ] T063 [US3] Add `make flash-model` input validation (file exists, size ≤ 2 MB, magic `UTNY`) before flashing in Makefile

**Checkpoint**: All user stories independently functional.

---

## Phase 6: Polish & Cross-Cutting Concerns

- [ ] T064 [P] Implement endurance script (100 prompts ≥ 1 h, detect resets, track free heap via `/info`) for SC-005 in tools/soak.py
- [ ] T065 [P] Write the top-level README (what it is, hardware, quickstart, demo prompts, limitations: correct only on trained facts) in README.md
- [ ] T066 [P] Document training on the M3 (uv, MPS, CPU fallback, expected time) in training/README.md and firmware build/flash in firmware/README.md
- [ ] T067 Publish the release model as a GitHub release asset and link it from README.md
- [ ] T068 Run all quickstart.md scenarios A–F on real hardware, time Scenario A from a fresh checkout (SC-008, < 30 min), and record results in specs/001-esp32-tiny-lm/measurements.md

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: none
- **Foundational (Phase 2)**: after Setup — blocks all stories
- **US1 (Phase 3)**: after Foundational (uses starter model from T035)
- **US2 (Phase 4)**: after Foundational; independent of US1 (host-only), its release model plugs into US1
- **US3 (Phase 5)**: after US1 (needs firmware + console)
- **Polish (Phase 6)**: after the desired stories

### Key task dependencies

- T010, T011, T012 → T017, T018, T020, T021
- T018 → T019 → T035; T020 + T021 → T023 → T032 → T033
- T025 → T026–T030 → T031 → T033 → T035; T022 + T034 → T035
- T046 → T047 (only if measurements miss targets); T038 needs golden.json from T023/T035
- T039 → T042, T043; T040 + T041 → T042 → T046
- T050 → T051; T051–T053 → T058; T054–T057 → T058

### Parallel Opportunities

- Setup: T003–T009 in parallel
- Foundational: Python definitions (T010–T016) in parallel with C runtime headers/math (T025–T027, T030)
- US1 tests T036/T037/T038 in parallel; US2 data tasks T050, T052, T053 in parallel
- US2 can proceed in parallel with US1 once Foundational is done

---

## Parallel Example: User Story 2

```bash
Task: "Implement Wikidata snapshot fetcher in training/tools/fetch_wikidata.py"
Task: "Write own German facts about the ESP32 in training/data/facts/esp32_projekt.tsv"
Task: "Write German templates for every relation in training/data/templates/*.toml"
Task: "Determinism test in training/tests/test_determinism.py"
```

---

## Implementation Strategy

### MVP First (User Story 1)

1. Phase 1 Setup → Phase 2 Foundational (starter model passes host parity)
2. Phase 3 US1 → flash starter model → **STOP and VALIDATE** on the board (speed, latency)
3. Demo-ready with ~200 facts

### Incremental Delivery

1. + US2 → full knowledge base (~3,000 facts), reproducible release model, eval report
2. + US3 → model swapping and robust error handling
3. Polish → endurance test, docs, release asset (budget gate is already in CI from Phase 2)

---

## Notes

- Tasks that require the physical board or the M3 Mac (T035, T046, T047, T058, T060, T067, T068) must be
  run by the user on their hardware; everything else runs in CI/containers.
- Commit after each task or logical group; keep parity tests green at every commit.
