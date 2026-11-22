---

description: "Task list for 006-hybrid-chemielehrer"
---

# Tasks: Hybrid Chemistry Teacher on the NodeMCU

**Input**: Design documents from `specs/006-hybrid-chemielehrer/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/, quickstart.md

**Tests**: Included where the constitution or the spec requires them:
- Parity of model math and fact-table rendering, Python vs. C (Principle III, FR-014)
- Builder checks for fact correctness (FR-005)
- Determinism (FR-015)
- The budget gate (Principle I)

No other test tasks.

**Organization**: Tasks are grouped by user story:
- **Foundational**: format changes (UTNY v2, `<fn>`, UTFT) and the fact table. Every story and every
  trained model needs them.
- **Final phase**: the full Spark training and the board measurements need the data of all three stories.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies on incomplete tasks)
- **[Story]**:
  - US1 = factual questions via function output (P1)
  - US2 = short explanations, greetings and refusals from the model (P2)
  - US3 = honest evaluation and one-command training (P3)
- 🔌 = needs the real NodeMCU board; cannot run in CI or the cloud container
- 🖥️ = needs the DGX Spark (or a long CPU run)
- 👤 = needs a review or decision by the user

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Constants, configs and file skeletons that later tasks fill in

- [ ] T001 [P] Define `UT_FACTS_FLASH_OFFSET 0x100000`, `UT_FACTS_AREA_SIZE 0x10000` and `UT_FACTS_MAX` (90 % of the area) per contracts/fact-table-format.md "Placement" in firmware-nodemcu/include/layout.h. Update the flash map comment in firmware-nodemcu/ld/eagle.flash.4m.ultratiny.ld (comment only, no section change).
- [X] T002 [P] Create training/configs/chemie-hybrid.toml:
  - NodeMCU dims as configs/chemie-nodemcu-spark.toml, `ctx_len` 104, 30000 steps, `qat_steps` 3000
  - `[data]`: `facts`, `templates = ["data/templates/hybrid.toml"]`, `explanations = "data/facts/chemie_kurz.tsv"`, `kurzarbeit = "data/eval/kurzarbeit.tsv"`, `kurzarbeit_sha256`, mix weights per research R7
  - `[eval]` thresholds per contracts/eval-sets.md "Report"
- [X] T003 [P] Create training/configs/hybrid-smoke.toml: tiny model (e.g. 2 × 64, ctx 104), 200 steps, all quality thresholds 0, the same data files as chemie-hybrid.toml.
- [X] T004 [P] Add `facts`, `explanations`, `kurzarbeit`, `kurzarbeit_sha256`, `mix` and `[eval]` threshold fields (`combo_min`, `family_min`, `kurzarbeit_min`, `wrong_fact_max`) with defaults to the config dataclasses in training/src/ultratiny/config.py. Old configs must keep loading (tests/test_nodemcu_config.py stays green).
- [X] T005 [P] Create the empty skeletons:
  - training/data/templates/hybrid.toml (header comment with the family rules of data-model.md `Question form.family`)
  - training/data/eval/ (README with the column format of contracts/eval-sets.md)
  - new curated TSV headers: training/data/facts/chemie_gleichungen.tsv, chemie_saeuren_basen.tsv, chemie_nachweise.tsv

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: The `<fn>` token and UTNY v2 (research R1, R12), the verified fact table (R3–R6), and its
identical rendering in Python and C (R11).

**⚠️ CRITICAL**: No user story work can begin until this phase is complete.

### Model format v2 and `<fn>`

- [X] T006 Add special `<fn>` (id 5, code point `0xFFFF0005`) to training/src/ultratiny/alphabet.py:
  - `N_SPECIAL` = 6, `FN = 5`
  - `encode` maps `\x01` → 5, and `decode` maps 5 → `\x01`
  - `from_code_points` accepts 5 specials (v1) and 6 specials (v2)
  - Spec: contracts/function-output.md "Token sequence"
- [X] T007 Write UTNY version 2 when the alphabet has `<fn>` and read versions 1 and 2, in training/src/ultratiny/export.py (`FORMAT_VERSION`, `read_model`).
- [X] T008 Make the runtime accept UTNY v1 and v2:
  - runtime/include/utiny.h: `UT_FORMAT_VERSION 2`, `UT_TOK_FN 5`, `int has_fn` and `int n_special` in `ut_model`
  - runtime/src/model.c: specials table check per contracts/function-output.md "UTNY v2"
  - runtime/src/alphabet.c: search text characters from `n_special`
- [X] T009 [P] Extend the parity tests to a tiny v2 model with `<fn>`:
  - fixture generation in training/tests/test_export_reference.py
  - a new `parity_tiny_v2` and `parity_tiny_v2_checked` case in runtime/CMakeLists.txt
  - The v1 fixtures (`models/nodemcu.utny`, starter) must still pass unchanged.

### Fact builder (FR-004, FR-005)

- [X] T010 [P] Extend training/tools/periodic.py with rule functions per research R6: main group, outer electrons, shells, electron arrangement (Z ≤ 20 and Ga–Kr), typical ion and charge, valence, neutrons = round(mass) − Z. Add unit tests in training/tests/test_factgen.py:
  - Na arrangement = `2, 8, 1`
  - S outer electrons = 6
  - O ion = `O2-`
  - Ne has no ion
  - every arrangement sums to Z
- [X] T011 Implement training/src/ultratiny/factgen.py. It builds Objects and Fact records from:
  - training/data/facts/wikidata_elemente_chemie.tsv
  - the periodic.py rules (T010)
  - the computed binary ionic compounds (11 metals × 8 anions: formula from charges, German name, molar mass)
  - the bond type for every compound, computed from its elements (research R6), with curated overrides
  - training/data/facts/chemie_verbindungen.tsv and the new curated files

  It enforces:
  - data-model.md `Object.key` (unique, case-sensitive, ≤ 12 B, alphabet only)
  - `Object.name` (≤ 40 B, unique per kind)
  - `Object.kind`, `Object.source` (allowed prefixes)
  - `Object.aliases` (training only, not exported)
  - `Fact record.value` (≤ 60 B finished string)
  - `Fact record.object` / `Fact record.type` (applicability)
  - `Fact record.source`
- [X] T012 Add the builder checks of data-model.md "Fact record" validation to training/src/ultratiny/factgen.py: balanced equations, neutral ionic formulas, consistent molar masses, element identities, unambiguous reverse types, rendered length ≤ 100 B. Test each check with one failing example in training/tests/test_factgen.py.
- [X] T013 Define the 26 question types of research R4 in training/data/templates/hybrid.toml (section `[types.<code>]`), with fields per data-model.md `Question type.code`, `Question type.name`, `Question type.kinds`, `Question type.needs_value`, `Question type.reverse_of`, `Question type.template` (non-empty prefix rule, values outside the alphabet allowed per data-model.md "Fact record" validation) and `Question type.not_applicable`. The forms (`Question type.forms`) are added in T020.
- [X] T014 [P] Curate training/data/facts/chemie_gleichungen.tsv: ~30 grade 7–10 reaction equations with slug key, German name and equation; `source` = `own` or `rlp-bb`. They must pass the balance check (T012).
- [X] T015 [P] Curate training/data/facts/chemie_saeuren_basen.tsv (~15: name, formula, `Säure`/`Lauge` and pH range) and training/data/facts/chemie_nachweise.tsv (~20: slug, name and the short description ≤ 50 B, data-model.md `Fact record.value`); equations in chemie_gleichungen.tsv are also ≤ 50 B. Record the new sources in DATA_LICENSES.md.

### UTFT writer and reader (Python, C)

- [X] T016 Implement training/src/ultratiny/facttable.py:
  - write and read UTFT v1 exactly as in contracts/fact-table-format.md: header, sorted tables, string area, slot control bytes, both CRCs
  - `lookup(type, key)` and `render(tokens)` per "Lookup" and contracts/function-output.md "Console behaviour" (prefix, rest, fallbacks)
  - the fixed texts `UNKNOWN`, generic not applicable and missing
  - size limit `UT_FACTS_MAX`
- [X] T017 [P] Add the CLI command `ut facts --config C --out DIR` to training/src/ultratiny/cli.py. It writes `facts.utft`, `facts.json` (readable dump) and a summary: types, records per type, size, checks.
- [X] T018 Implement runtime/include/utiny_facts.h and runtime/src/facts.c:
  - `ut_facts_open(h, read_fn, user, area_size)` returns OK/MISSING/CORRUPT
  - `ut_facts_type(h, code)`, `ut_facts_prefix(...)` and `ut_facts_render_rest(...)` with a write callback
  - one static-size 128 B read buffer in the handle, aligned reads only, no heap, no float
  - binary search plus the reverse scan, exactly as in contracts/fact-table-format.md "Lookup"
- [X] T019 Add host tests for facts.c in runtime/tests/test_facts.c, plus `test_facts_checked` in runtime/CMakeLists.txt:
  - Fixtures from `facttable.py`: a small UTFT and the expected rendered bytes for forward, reverse `o29`, not applicable `iNe`, unknown key, unknown type, `{X}` profile, missing (all `FF`) and corrupt (CRC)
  - The C output must equal the Python bytes.
  - Fixture generator: training/tests/test_facttable.py writes runtime/tests/fixtures/facts_*.

**Checkpoint**:
- `ut facts` builds a valid table.
- Python and C render identical bytes.
- v1 and v2 models load.

---

## Phase 3: User Story 1 – Factual question in your own words (Priority: P1) 🎯 MVP

**Goal**: Factual questions in many phrasings produce `<fn>` + type + key. The board prints the
verified answer from the fact table (FR-001, FR-002, FR-004, FR-006, FR-007, FR-011, FR-012).

**Independent Test**:
- Train `hybrid-smoke` (CPU), then the full model (final phase).
- On the host, `utiny-host --facts` answers "Welche Ordnungszahl hat Kupfer?", "Was ist N?" and
  "Was ist CO?" from the table.
- Every printed fact value equals the table (quickstart §2, §6, §7).

- [X] T020 [US1] Write ≥ 12 question forms in ≥ 4 families for each of the 26 types in training/data/templates/hybrid.toml, filling data-model.md `Question type.forms` per `Question form.text`, `Question form.family` and `Question form.type`:
  - exam phrasings ("Nenne", "Gib … an", "Berechne", "Stelle … auf", "Wie viele")
  - short forms
  - reverse forms with `{key}` for `s`, `o`, `f`
  - "Was ist {name}?" → `E`, and "Was ist {key}?" → `s` (element) or `f` (compound)
  - a `multi` family of two-fact forms ("Symbol und Ordnungszahl von {name}?") whose target is the first named type (research R7)
- [X] T021 [US1] Generate the factual training pairs in training/src/ultratiny/datagen.py, with targets per data-model.md "Training pair":
  - every (type, object, form), including `Object.aliases` as extra names
  - the target is `\x01` + `Question type.code` + `Object.key`
  - noise applied only to the question and never to the key part; symbols and formulas inside the question (`{key}` slots) are protected from lowercasing and typos, names may be lowercased (FR-012, research R7)
  - both directions for symbol, atomic number and formula (FR-006)
  - The existing relation-based path stays for old configs.
- [X] T022 [US1] Add unknown-object negatives to training/src/ultratiny/datagen.py per research R5:
  - made-up and out-of-curriculum compound names → `Das weiß ich leider nicht.` as text
  - unknown formulas copied as a key (caught by lookup rule 3)
  - inapplicable combinations (e.g. ion of a noble gas) → the normal `<fn>` target (the table answers "not applicable")
- [X] T023 [US1] Make `Reference.generate()` return token ids including `<fn>` and stop at `<eos>` or after 12 key characters, per contracts/function-output.md, in training/src/ultratiny/reference.py. Add `answer_text(question, facts)`, which returns the printed bytes via `facttable.render`.
- [X] T024 [US1] Implement the console fn sub-state in runtime/src/console.c and runtime/include/utiny_console.h:
  - FN_TYPE / FN_KEY / RESOLVE as in contracts/function-output.md "Console behaviour" and data-model.md "Board state"
  - prefix on the type character, a 16 B key buffer, the rest on `<eos>`/12 chars/ctx
  - the ` – ` fallback after a printed prefix, Ctrl-C abort
  - a `facts` handle in `ut_console_io`; update every `ut_console_io` initializer so the `-Wextra -Werror` builds stay green: runtime/host/utiny_host.c, runtime/tests/test_console_logic.c and the legacy firmware/main/console_uart.c (`facts = NULL`)
  - `/info` facts line, `/raw on|off`, `/trace` label `⟨fn⟩`
- [ ] T025 [US1] Add console tests in runtime/tests/test_console_logic.c, with a fake model output stream and a fixture table:
  - prefix timing (printed before the key is complete)
  - each fallback
  - missing table
  - Ctrl-C in FN_KEY
  - a `<fn>` that is not the first token is treated as `<eos>`
- [X] T026 [US1] Add `--facts FILE` to runtime/host/utiny_host.c. Golden checking compares tokens **and** the `text` field; `text` is optional, so existing golden files (starter, nodemcu) keep passing on tokens only. Update training/src/ultratiny/golden.py to write `facts_sha256` and the per-case `text` (contracts/function-output.md "Host and reference").
- [ ] T027 [US1] Board glue in firmware-nodemcu/src/main.cpp:
  - flash-read callback via `ESP.flashRead` at `UT_FACTS_FLASH_OFFSET` (aligned)
  - `ut_facts_open` at boot, with a `yield()` every 4 KB of the CRC
  - boot status line, `io.facts`
  - Static DRAM growth ≤ 1 KB (check with tools/budget_report.py `--pio-build`).
- [ ] T028 [P] [US1] Add `FACTS ?=`, `NODEMCU_FACTS_ADDR 0x100000`, `NODEMCU_FACTS_MAX 58982` and the target `nodemcu-flash-facts` (size check, then `$(ESPTOOL) write_flash 0x100000`) to the Makefile. Document it in firmware-nodemcu/README.md.
- [ ] T029 [P] [US1] Add the `facts` budget entry (file size ≤ 90 % of the 64 KB area, outside the mapped window) to tools/budget_report.py, with tests in training/tests/test_budget_report.py. Add `--facts FILE` to the CI budget step in .github/workflows/ci.yml.
- [ ] T030 [P] [US1] Make tools/device_parity.py compare printed answer text from the golden `text` field, and tools/device_smoke.py check the `/info` facts line.

**Checkpoint**: `hybrid-smoke` trains on CPU. `utiny-host --facts` renders function outputs from the
table, with golden tokens and text bit-identical in the normal and the checked build.

---

## Phase 4: User Story 2 – Short explanations, greetings, refusals (Priority: P2)

**Goal**: The model writes greetings, refusals and curriculum explanations of ≤ 60 characters itself (FR-003, FR-008).

**Independent Test**:
- Explanation and off-topic questions in the smoke and full model produce plain text (no `<fn>`).
- Explanations are ≤ 60 chars and contain the keywords; off-topic questions are refused (quickstart §7).

- [ ] T031 [US2] Write training/tools/shorten_llm.py (🖥️ Spark, reusing the client and prompt handling of training/tools/augment_llm.py):
  - For each `frei` entry of chemie_rlp_*.tsv and chemie_reaktionen.tsv, propose an answer ≤ 60 chars ("keine neuen Fakten")
  - Write the proposals to training/data/facts/chemie_kurz.tsv, with columns per data-model.md `Short explanation.id`, `Short explanation.questions` and `Short explanation.answer`, plus `reviewed` = `no`
- [ ] T032 [US2] Implement the automatic check of research R8 in training/src/ultratiny/augment.py (`check_short_explanation`), with tests in training/tests/test_augment.py. It rejects a proposal that is longer than 60 characters, uses characters outside the alphabet, adds a number, formula or symbol, or lacks the key term, or contains a value the fact table holds as a fact (FR-002). Entries whose content is a table fact (e.g. "Was ist Kalk chemisch?") are marked `to_fact` and turned into factual questions with an alias.
- [ ] T033 [US2] 🖥️ Run shorten_llm.py on the Spark and the check locally, then commit training/data/facts/chemie_kurz.tsv with check results. Record its source (own curriculum text, shortened by an LLM, reviewed) in DATA_LICENSES.md.
- [ ] T034 [US2] 👤 The user reviews training/data/facts/chemie_kurz.tsv in the PR and sets `reviewed = yes`. Datagen uses only reviewed rows.
- [ ] T035 [US2] Generate explanation, greeting and refusal pairs in training/src/ultratiny/datagen.py:
  - reviewed short explanations with their phrasings and paraphrases
  - chemie_persona.tsv and the refusal data as today
  - repeat weights from the config `mix` (research R7: ~55 % facts, 30 % explanations, 15 % other)
  - pairs that don't fit ctx 104 are rejected loudly (counted and listed, not silently dropped)

**Checkpoint**: The datagen report shows explanations ≤ 60 chars, no dropped curriculum entries and the configured mix.

---

## Phase 5: User Story 3 – Honest measurement, one-command training (Priority: P3)

**Goal**: Held-back combinations, families and the short-test set are kept out of training and reported
separately; one command runs the whole pipeline (FR-009, FR-010, FR-015).

**Independent Test**: `ut pipeline --config configs/hybrid-smoke.toml` writes the per-set report of
contracts/eval-sets.md, and two runs with the same seed are identical (quickstart §3, §4).

- [X] T036 [US3] Draft training/data/eval/kurzarbeit.tsv with ≥ 120 rows, per data-model.md `Short-test item.id`, `Short-test item.question`, `Short-test item.kind`, `Short-test item.expected` and `Short-test item.grade`, written independently of hybrid.toml. Mix per research R9: ~70 % fact, 15 % explain, 10 % refuse/unknown, 5 % multi/tricky (N/Na/Co/CO).
- [ ] T037 [US3] 👤 The user reviews the short-test set. Then pin its SHA-256 as `kurzarbeit_sha256` in training/configs/chemie-hybrid.toml and hybrid-smoke.toml.
- [X] T038 [US3] Implement the held-back sets in training/src/ultratiny/datagen.py per data-model.md "Held-back sets" (`combo`, `family`, `kurzarbeit`, `explain`, `refusal`):
  - stable hash with the seed, and the coverage rules
  - pin check: fail if the hash differs
  - drop normalised prompts equal to a short-test question
  - write the files of contracts/eval-sets.md, including `heldback.json` and a `dataset.sha256` that covers `facts.utft`
- [X] T039 [US3] Extend the datagen report in training/src/ultratiny/datagen.py: types, forms and families per type, two-way coverage, sizes of all sets, dropped short-test matches. Fail if SC-006 is not met (≥ 20 types × ≥ 10 forms).
- [ ] T040 [US3] Implement the scoring and report of contracts/eval-sets.md in training/src/ultratiny/evaluate.py:
  - function-output match, or the same rendered answer
  - wrong-fact and decline rules, explanation keyword and length check, refusal and false refusal
  - per-type and per-kind breakdowns
  - Tests in training/tests/test_evaluate_hybrid.py (one case per row of the scoring table).
- [X] T041 [US3] Rewire `cmd_pipeline` in training/src/ultratiny/cli.py: facts → datagen → train → export (v2) → eval (all sets) → golden (with text) → budget (model + facts). It copies `facts.utft` into the run and fails on any `[eval]` threshold. Record the facts hash and held-back hash in the model meta (training/src/ultratiny/train.py / export.py).
- [ ] T042 [US3] Add a determinism test for the hybrid path in training/tests/test_determinism.py: two `hybrid-smoke` datagen runs and a short train give byte-identical data, `facts.utft` and model (apart from the meta `git`).
- [ ] T043 [P] [US3] Show the new eval lines (combo, family, kurzarbeit, wrong fact) in the run cards and the all-values table of tools/loss_viewer.py.

**Checkpoint**: The smoke pipeline runs end to end on CPU, with a per-set report, deterministic outputs and budgets OK.

---

## Phase 6: Training, board and polish

**Purpose**: The real model, measurements on the board, documentation

- [ ] T044 🖥️ Train `chemie-hybrid` on the Spark (quickstart §5, seed 1234) and copy `model.utny`, `facts.utft`, `golden.json` and `eval.json` to models/chemie-hybrid*. Record the per-set results against SC-001–SC-006 in specs/006-hybrid-chemielehrer/measurements.md. If a threshold is missed, record the baseline and the agreed adjustment (spec checklist note).
- [ ] T045 Run host parity with the trained model (`utiny-host --model models/chemie-hybrid.utny --facts models/chemie-hybrid.utft --golden …`) and add the files to CI parity in runtime/CMakeLists.txt.
- [ ] T046 🔌 Flash the model and the table onto the NodeMCU and run quickstart §7:
  - `/info`
  - the six example questions
  - prefix latency per question type and chars/s (SC-007)
  - heap after boot
  - `tools/device_parity.py` (SC-008)

  Record the results in specs/006-hybrid-chemielehrer/measurements.md.
- [ ] T047 🔌 FR-013 check on the board: erase the table area, then reboot. `/info` must show `fehlt`, a factual question must give the "missing" text, and greetings and explanations must still work. Record the result in measurements.md.
- [ ] T048 [P] Update the documentation:
  - README.md (hybrid mode, `make nodemcu-flash-facts`)
  - training/README.md and training/SPARK.md (`ut facts`, chemie-hybrid config, review steps)
  - specs/001-esp32-tiny-lm/contracts/model-format.md (pointer to UTNY v2)
- [ ] T049 Run `make budget BOARD=nodemcu`, the full CTest suite and pytest. Confirm CI is green, including the `firmware-nodemcu` job with the facts budget entry.

---

## Dependencies & Execution Order

### Phase dependencies

- **Setup (T001–T005)**: no dependencies; all [P].
- **Foundational (T006–T019)**: after Setup.
  - T006 → T007 → T008 → T009 (format chain).
  - T010 → T011 → T012. T013 needs T005. T014 and T015 are [P] and feed T011/T012.
  - T016 needs T011–T013. T017 needs T016. T018 needs the format of T016. T019 needs T016 and T018.
- **US1 (T020–T030)**: after Foundational.
  - T020 → T021 → T022. T023 needs T006/T016. T024 needs T018. T025 needs T024. T026 needs T023/T024.
  - T027 needs T018/T024. T028, T029 and T030 are [P] after T016.
- **US2 (T031–T035)**: after Foundational. T031 → T032 → T033 → T034 → T035. It is independent of US1
  except for the shared datagen file (do T035 after T021/T022 to avoid conflicts).
- **US3 (T036–T043)**: T036 → T037. T038 needs T021, T035 and T037. T039 needs T038. T040 needs T023.
  T041 needs T038–T040. T042 needs T041.
- **Final (T044–T049)**: T044 needs US1–US3 and the user reviews (T034, T037). T045 needs T044.
  T046 and T047 need T027/T028 and T044.

### User story dependencies

- **US1** is the MVP: it can be shown with the smoke model on the host, and with the real model after T044.
- **US2** shares only the datagen file with US1.
- **US3** needs the targets of US1 and US2 to score them, but its set and report code (T038–T040) can be
  written in parallel against the smoke data.

## Parallel Examples

```text
Setup:        T001 | T002 | T003 | T004 | T005
Foundational: (T006→T007→T008→T009) | (T010→T011→T012) | T013 | T014 | T015
US1 after T016/T018: T028 | T029 | T030 while T020–T022 (datagen) and T024–T025 (console) run in parallel
US2:          T031/T032 (code) while US1 runs; T033 on the Spark when free
US3:          T036 (short-test draft) any time after Setup; T040 (evaluate) in parallel with T038
```

## Implementation Strategy

1. **MVP (US1 on the host)**: Setup → Foundational → T020–T026.
   - Train `hybrid-smoke`.
   - `utiny-host --facts` shows table answers for factual questions, with parity.
2. **Data for real (US2 + reviews)**:
   - Short explanations proposed on the Spark.
   - The user reviews `chemie_kurz.tsv` and `kurzarbeit.tsv`. These reviews are the long pole, so start T031/T036 early.
3. **Honest evaluation (US3)**: held-back sets, report, pipeline thresholds, determinism.
4. **Full run and board (Phase 6)**: Spark training, then measurements on the NodeMCU, then documentation and CI.
5. Commit after each task or logical group. Push only on `claude/keen-feynman-z2sszl`.
