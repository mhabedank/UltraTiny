---

description: "Task list for spec 007: benchmark and KPI report"
---

# Tasks: Benchmark and KPI Report

**Input**: Design documents from `specs/007-benchmark-kpi-bericht/`

**Prerequisites**: [plan.md](plan.md), [spec.md](spec.md), [research.md](research.md),
[data-model.md](data-model.md), [contracts/](contracts/), [quickstart.md](quickstart.md)

**Tests**: Included. The spec requires measurable checks: SC-006 (pins), SC-007 (CI detects a
change) and SC-008 (49/50 agreement with a person). The plan lists `training/tests/test_bench_*.py`.

**Organization**: Tasks are grouped by user story so each story can be built and checked on its own.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies on incomplete tasks)
- **[Story]**:
  - US1 = PC measurement with one command (P1)
  - US2 = comparison report (P1)
  - US3 = committed baseline (P1)
  - US4 = board measurement (P2)
  - US5 = demo runner (P2)
  - US6 = CI check (P3)
- 🔌 = needs the real NodeMCU board; cannot run in CI or the cloud container
- 🖥️ = needs the DGX Spark (where `chemie-nodemcu` is)
- 👤 = needs a review or decision by the user

All commands run from `training/` (`uv run …`), as in [contracts/cli.md](contracts/cli.md).

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Directories, package skeleton and documentation stubs

- [X] T001 Create the `bench/` tree per plan.md "Source Code":
  - `bench/suites/chemie/{sets,text}/`, `bench/suites/allgemein/{sets,text}/`, `bench/results/`, `bench/demo/`
  - `bench/README.md`: what lives here, that nothing in `bench/` is ever trained (FR-005), how to run and how to re-pin
- [X] T002 [P] Create the package skeleton `training/src/ultratiny/bench/__init__.py` with empty modules:
  - `suite.py`, `scoring.py`, `subject.py`, `lm.py`, `pc.py`, `board.py`, `report.py`, `demo.py`
  - each with a module docstring naming its research entry (R2–R10)
- [X] T003 [P] Create the entry points with argument parsing only (help text, exit codes 0/1/2 per contracts/cli.md):
  - `tools/bench.py` (subcommands `pc`, `board`)
  - `tools/bench_report.py`, `tools/bench_demo.py`, `tools/bench_s2.py`, `tools/bench_export_facts.py`
  - each imports `ultratiny.bench` like the other tools import `ultratiny`

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Suite loading with pin checks and answer scoring, needed by every story

**⚠️ CRITICAL**: No user story work can begin until this phase is complete

- [X] T004 Implement suite loading in `training/src/ultratiny/bench/suite.py` per contracts/suite-format.md:
  - parse `suite.toml` with `tomllib`; resolve paths relative to the suite, allowing outside paths only when pinned
  - check every pin before anything else and fail with the file name, both hashes and exit code 2 (data-model.md `Suite.files`)
  - load value classes (data-model.md `Value class.kind`, `Value class.case_sensitive`, `Value class.decimals`, `Value class.units`)
  - load properties (data-model.md `Property.value_class`, `Property.canonical`, `Property.reverse`)
  - load thresholds (data-model.md `Suite.thresholds`), board sample (`Suite.board_sample`) and `Suite.not_applicable`
  - load `facts.tsv`, rejecting duplicate (`object`, `property`) pairs (data-model.md `Reference fact.object`, `Reference fact.property`)
  - load question sets, validating data-model.md `Test item.kind`, `Test item.question` (≤ 70 characters) and `Test item.expected` (every property and object must exist); derive `Test item.type`
  - expose the test-set version (suite version + file SHA-256, data-model.md `Suite.version`)
  - `all_questions()` lists every question of every suite under `bench/suites/` (for FR-005)
- [X] T005 Implement answer scoring in `training/src/ultratiny/bench/scoring.py` per research.md R5:
  - normalisation (NFC, collapse spaces, keep case) and refusal detection from `refusal_forms`
  - known-value extraction per value class: whole tokens; case-sensitive where data-model.md `Value class.case_sensitive` says so; numbers with `,`/`.`, rounding to `Value class.decimals`, optional `Value class.units`
  - the subject-name rule (the question's object name is not a wrong value)
  - the four classes `correct`, `wrong_fact`, `refused`, `no_answer` for `fact`/`multi`
  - spec 006 rules for `explain` (all keywords, ≤ `explain_max`, not refused) and for `refuse`/`unknown` (correct when refused; a known value counts as a wrong fact)
- [X] T006 Implement KPI aggregation in `training/src/ultratiny/bench/scoring.py` per contracts/result-format.md "KPI definitions":
  - F1 with per-property detail, F2, F3 with per-set detail, F4, F5, F6
  - R2–R4 from file sizes
  - each KPI value with `value`, `n`, `detail` and `status` (data-model.md "KPI value")
  - F1 keeps never-learned question types in the denominator (spec clarification 2026-11-23)
- [X] T007 [P] Write `training/tests/test_bench_suite.py`:
  - a tiny suite fixture under `training/tests/fixtures/bench_mini/` loads
  - one changed byte gives a pin error naming the file (SC-006)
  - unknown property or object in `expected`, duplicate fact and a too-long question are rejected
- [X] T008 [P] Write `training/tests/test_bench_scoring.py`:
  - a hand-labelled sample of 50 answers in `training/tests/fixtures/bench_scoring_sample.tsv` (columns: question, expected, answer, class by hand) covering free-text and template answers, Co/CO, N/Na, decimal comma, units, refusal forms, subject name, two values of one class, multi, explain, unknown
  - assert ≥ 49/50 agreement (SC-008) and exact agreement on the listed edge cases from spec "Edge Cases"

**Checkpoint**: Suites load with pin checks and answers can be scored. User story work can start.

---

## Phase 3: User Story 1 - Measure a model on the PC with one command (Priority: P1) 🎯 MVP

**Goal**: `tools/bench.py pc` writes one result file with every PC KPI for any suite and any model kind.

**Independent Test**:
- Run quickstart §2 (repo model, allgemein suite) and §3 (hybrid smoke model, chemie suite).
- Two runs on the same inputs give identical quality KPIs.

### Tests for User Story 1

- [X] T009 [P] [US1] Write `training/tests/test_bench_lm.py` with the fixture model `runtime/tests/fixtures/tiny_v2.utny`:
  - S1 sliding-window bits are finite, and coverage counts characters outside the alphabet
  - stride and window follow research.md R6
  - for a synthetic S2 probe, the control text and the recall rule give the expected recalled/not-recalled split
  - a distance beyond `ctx_len` is never recalled
- [X] T010 [P] [US1] Write `training/tests/test_bench_pc.py`:
  - a PC run on the mini suite with `tiny_v2.utny` produces every KPI key of contracts/result-format.md
  - two runs give byte-identical `kpis` and `items`
  - `--jobs 2` gives the same result as `--jobs 1`
  - a v2 model without `--facts` scores fact items `no_answer`

### Implementation for User Story 1

- [X] T011 [US1] Implement the subject adapter in `training/src/ultratiny/bench/subject.py` per research.md R2:
  - an interface with `answer(question)` and `bits(text, positions)`
  - the transformer adapter wraps `ultratiny.reference.Reference`
    - renders v2 answers with `facttable.answer_bytes()` when a fact table is given
    - greedy, `max_len = ctx_len − 3`
    - flags `too_long` questions
  - identity (data-model.md "Result file" `model`, `knowledge`): SHA-256, size, params, ctx, meta git/date/seed
- [X] T012 [US1] Implement S1 and S2 in `training/src/ultratiny/bench/lm.py`:
  - S1 per research.md R6: window `ctx_len`, stride `ctx_len/2`, scores the second half, bits from float64 softmax, topic, general and total, coverage
  - S2 per research.md R7 and spec FR-009: bits on the target span with full history up to `ctx_len − 1`; recalled when ≤ `recall_ratio` × the control bits; S2 = largest distance with ≥ `recall_min` recalled, plus the curve
  - fields per data-model.md `S2 probe.distance`, `S2 probe.target_start`, `S2 probe.target_len`, `S2 probe.text`, `S2 probe.control`
- [X] T013 [P] [US1] Implement the S2 probe generator in `tools/bench_s2.py` per research.md R7:
  - invented target words of 6–8 letters from the alphabet, fixed seed
  - filler from the general half of the S1 text
  - distances from `suite.toml` `[s2]`, 13 probes each
  - each control text has the same length as its probe text (data-model.md `S2 probe.control`)
  - the output TSV is deterministic
- [X] T014 [US1] Implement the PC run in `training/src/ultratiny/bench/pc.py` and wire `tools/bench.py pc` per contracts/cli.md:
  - check pins, then load the subject and ask every set
  - F6 via the canonical questions over `facts.tsv`
  - S1, S2, and the S3 answers
  - overlap with `--train-data` (normalised as in `hybrid.py`; `unknown` without the file)
  - `--jobs N` over fresh-context questions
  - `--only` marks the result partial
  - write the result JSON (keys sorted, two-space indent, data-model.md "Result file" `kind`, `label`, `suite`, `env`, `overlap`, `complete`, `items`) and a one-line-per-KPI summary
- [X] T015 [US1] Implement the S3 rating sheet in `training/src/ultratiny/bench/pc.py`:
  - write `<out>.s3.tsv` with `id`, `answer_sha256`, `answer`, `grammar_ok`
  - keep existing ratings only where data-model.md `Rating sheet.answer_sha256` still matches
  - S3 = share of `ja` among rated answers, else "not rated"
- [X] T016 [P] [US1] Write the allgemein suite configuration in `bench/suites/allgemein/` (deterministic, no LLM):
  - `facts.tsv` from `training/data/facts/starter.tsv`: capitals and element symbols, in both directions where the template set has both
  - `suite.toml` with value classes (`city`, `country`, `symbol`, `element_name`), properties with canonical questions, refusal forms of the starter model, thresholds from spec FR-018, board sample, `[s2]`
- [X] T017 [P] [US1] Implement the proposal generator `training/tools/bench_propose_llm.py`, reusing the Ollama client, judge prompt, alphabet check and cache of `training/tools/augment_llm.py`:
  - subcommands `questions` (new phrasings per property, given the canonical question and object names), `unknown` (invented or out-of-topic objects in the topic's question forms), `offtopic`, `s3` (greetings, explanations, refusals) and `text` (topic text in short paragraphs)
  - `--suite DIR` reads properties and objects from the suite's `facts.tsv`/`suite.toml`; nothing is topic-specific in the code
  - drops every candidate whose normalised form equals a training prompt (`training/data/**`, `kurzarbeit.tsv`) or another proposal
  - the LLM only proposes question text; the expected answer (`property: object`) comes from the request, never from the LLM
  - writes `bench/suites/<suite>/proposals/<kind>.tsv` with a `source = llm:<model>` column; it never writes `sets/` or `text/`
  - only models allowed by `DATA_LICENSES.md` (`gemma4:*`, `gpt-oss:*`, `qwen3*`); others are refused
- [X] T018 [US1] 🖥️ On the Spark, run `bench_propose_llm.py` for both suites (all subcommands) with an allowed local model and commit `bench/suites/*/proposals/*.tsv`
- [X] T019 [US1] Assemble the allgemein sets from the proposals in `bench/suites/allgemein/sets/`:
  - `unseen.tsv` (≥ 60 questions over all properties)
  - `unknown.tsv` and `offtopic.tsv` (≥ 20 each)
  - `s3.tsv` (20 prompts incl. self-description)
  - the selection is a deterministic script step (fixed seed, balanced per property), so the sets can be rebuilt from the proposals
- [X] T020 [US1] Write the S1 texts per research.md R6:
  - `bench/suites/allgemein/text/s1.txt` and `bench/suites/chemie/text/s1.txt`
  - topic half per suite (10,000 characters each) from the `text` proposals: chemie gets grade 7–10 chemistry text, allgemein gets geography and general-knowledge text (countries, capitals, currencies)
  - general half, the same in both suites: 10,000 characters of public-domain German prose with the source named in a `#` comment line
  - add a check in `training/tests/test_bench_suite.py` that no 40-character span of either text occurs in `training/data/**`
- [X] T021 [US1] Generate `bench/suites/allgemein/text/s2.tsv` and `bench/suites/chemie/text/s2.tsv` with `tools/bench_s2.py`, then pin all allgemein files in `bench/suites/allgemein/suite.toml`
- [X] T022 [US1] 👤 The user spot-checks `bench/suites/allgemein/sets/*.tsv` and both `text/s1.txt` files (and agrees to the public-domain source). Record the review in `bench/README.md` (FR-006), then re-pin in `bench/suites/allgemein/suite.toml` if anything changed.
- [X] T023 [US1] Run quickstart §1 and §2 on `models/nodemcu.utny`:
  - commit `bench/results/nodemcu_allgemein_pc.json` (stable name used by CI) and its `.s3.tsv`
  - record the run time and the S2 sanity check (recall up to ≤ 96, none at ≥ 128) in `specs/007-benchmark-kpi-bericht/measurements.md`
- [X] T024 [US1] Implement `tools/bench_export_facts.py` per research.md R4: build the spec 006 fact set with `ultratiny.factgen.build` and write `bench/suites/chemie/facts.tsv` (`object`, `object_name`, `property`, `value`, property names = question type names of `data/templates/hybrid.toml`)
- [X] T025 [US1] Write the chemie suite configuration `bench/suites/chemie/suite.toml`:
  - value classes for every property of `facts.tsv`, including numbers with decimals and units
  - canonical questions per property and refusal forms (`UNKNOWN`, `REFUSAL_ANSWER`, the not-applicable form)
  - thresholds from spec FR-018 and `explain_max = 60`
  - `[sets]` with `kurzarbeit = "../../../training/data/eval/kurzarbeit.tsv"`, pinned to `cd2a36bf…`
- [X] T026 [US1] Assemble the chemie sets from the proposals (same deterministic step as T019):
  - `bench/suites/chemie/sets/unseen.tsv`: ≥ 200 fact questions covering every property
  - `sets/unknown.tsv` (≥ 40) and `sets/offtopic.tsv` (≥ 40, none from `data/facts/abweisen.tsv` or `data/augment/abweisen.tsv`)
  - `sets/s3.tsv` (20 prompts)
  - 10 long T3 prompts appended to `unseen.tsv` and listed in `[board_sample] t3`
- [X] T027 [US1] 👤 The user reviews the chemie sets (spot checks, as for `kurzarbeit.tsv`). Record the review (date, scope) in `bench/README.md` (FR-006). Then pin all chemie files in `bench/suites/chemie/suite.toml`.
- [X] T028 [US1] Run quickstart §3:
  - `make hybrid-smoke`, then `tools/bench.py pc` on the smoke model with and without `--facts`
  - check that `items[].answer` are printed sentences
  - record the chemie run time (SC-002 ≤ 15 min) in `specs/007-benchmark-kpi-bericht/measurements.md`

**Checkpoint**: One command measures any model on either suite; the repo model's result is committed.

---

## Phase 4: User Story 2 - Compare a step with the baseline and its predecessor (Priority: P1)

**Goal**: `tools/bench_report.py` turns result files into a Markdown and HTML report with verdicts, budget and parity status and changed answers.

**Independent Test**:
- Quickstart §4 on the committed `nodemcu` result plus a modified copy.
- Verdicts match research.md R9 by hand for three KPIs.

### Tests for User Story 2

- [X] T029 [P] [US2] Write `training/tests/test_bench_report.py`:
  - **verdicts**: F1 +2 points gives "unchanged" and +4 gives "better"; with 3 seeds a change counts only above 2 × spread; exact KPIs count any change
  - **not comparable**: shown on different test-set versions
  - **budget**: a model above the area limit or an arena above 35 KB shows "budget broken"
  - **parity**: a parity mismatch shows "parity broken"
  - **changed answers**: listed per question
  - **determinism**: two renders are identical apart from the "generated" line

### Implementation for User Story 2

- [X] T030 [US2] Implement the report model in `training/src/ultratiny/bench/report.py` per research.md R9 and contracts/result-format.md "Report":
  - group results by `label` and `kind`, merging PC and board results of one label
  - seeds: mean and sample spread
  - Δ to the baseline and to the predecessor
  - verdicts per data-model.md "Comparison report" (better, worse, unchanged, not comparable, not measured, not applicable) using `Suite.thresholds` from the result's suite
  - the changed-answers list
  - overlap and incomplete-run notes
- [X] T031 [US2] Implement the budget section in `training/src/ultratiny/bench/report.py`:
  - limits from `tools/budget_report.py` `PROFILES["nodemcu"]` and `HEADROOM`, plus the roadmap gate arena ≤ 35 KB
  - rows: model, arena and reserve, firmware (when given), fact area, each with value, limit and ok/broken
  - summary flags "budget broken" and "parity broken"
- [X] T032 [US2] Implement Markdown and HTML rendering in `training/src/ultratiny/bench/report.py` per research.md R10:
  - the same sections in both formats
  - HTML: one self-contained file with inline CSS and light/dark colours, inline SVG for the S2 curve and F1 per property, no JavaScript
  - sorted output with a single "generated" line
- [X] T033 [US2] Wire `tools/bench_report.py` per contracts/cli.md (`--baseline`, `--predecessor`, `--ratings`, `--md`, `--html`, `--strict`) and run quickstart §4

**Checkpoint**: Any set of result files gives an honest comparison report.

---

## Phase 5: User Story 4 - Measure speed and resources on the board (Priority: P2)

**Goal**: `tools/bench.py board` measures T1–T3, R1 and the board sample over the existing console and checks parity with the PC.

**Independent Test**:
- Quickstart §6 against `utiny-host --console` without hardware.
- Quickstart §7 on a NodeMCU with `nodemcu` (🔌).

(Placed before US3 because the baseline needs the board mode.)

### Tests for User Story 4

- [X] T034 [P] [US4] Write `training/tests/test_bench_board.py` with a scripted fake link (devlib-compatible `read`/`write`):
  - parse `/info`, `/stats` (`@ut {"type":"sys"…}`) and `/trace json` lines
  - T3 from steps with `pos ≥ 0.9 × ctx_len`
  - an identity mismatch stops the run (exit 2)
  - a boot banner mid-run is recorded as a reset and the run continues, marked `complete: false`
  - a timeout is recorded as a hang
  - CRLF/trailing-space normalisation before the parity compare
  - a question with a character outside the model alphabet gives the same answer on the PC adapter and on `utiny-host --console` (spec "Edge Cases")
  - T2 from per-step times of characters 2…n (without the first-character wait) and T3 from steps at `pos ≥ 0.9 × ctx_len` (spec FR-009)

### Implementation for User Story 4

- [X] T035 [US4] Implement the board run in `training/src/ultratiny/bench/board.py` per research.md R8:
  - with `--port`: RTS reset first (no flashing), so the first `/stats` gives R1 after boot
  - identity check from `/info` against `--model`/`--facts` (data-model.md "Result file" `board`)
  - `/trace json` on for the whole run; pasted pass over the board sample; typed pass for the first `typed` items at 100 ms per character; the T3 prompts; `/trace aus` at the end
  - per answer: `first_ms` from `/info` (T1), per-step times from the trace lines (T2 over characters 2…n, T3 over steps at `pos ≥ 0.9 × ctx_len`), `/info` chars/s as information only
  - `/stats` at start and end for R1
  - per-item parity against the PC adapter
  - events for resets, hangs and timeouts (data-model.md "Result file" `events`, `complete`)
  - never sends flash or erase commands
- [X] T036 [US4] Wire `tools/bench.py board` per contracts/cli.md (`--port` or `--exec` via `devlib.ExecLink`, `--firmware`, `--sample all|parity`):
  - T1 typed/pasted median and max, T2 median, T3, R1
  - write the board result JSON
  - exit 1 on any parity mismatch
- [X] T037 [US4] Run quickstart §6 (`--exec` against `build/utiny-host --console`, allgemein suite, `--sample parity`) and fix any console parsing differences between host and board output
- [ ] T038 [US4] 🔌 Run quickstart §7 on the NodeMCU with `nodemcu` flashed, with `--firmware ../firmware-nodemcu/.pio/build/nodemcuv2/firmware.bin`:
  - commit `bench/results/nodemcu_allgemein_board_<date>.json`
  - record T1, T2, R1 and the run time (≤ 30 min) in `specs/007-benchmark-kpi-bericht/measurements.md`; the SC-003 comparison with spec 005 is made in T040 with `chemie-nodemcu`

**Checkpoint**: Board KPIs are measured by one command, with parity.

---

## Phase 6: User Story 3 - Commit the baseline once (Priority: P1)

**Goal**: Results for `chemie-nodemcu` and `nodemcu` and the baseline report are in the repository, so comparisons work without the Spark or a board.

**Independent Test**: Quickstart §8 in a fresh checkout: the baseline report is reproduced from committed files alone (SC-001).

- [ ] T039 [US3] 🖥️ On the Spark, run `tools/bench.py pc --suite ../bench/suites/chemie --model <chemie-nodemcu.utny> --label chemie-nodemcu` (with `--train-data` of its run, if still present) and commit `bench/results/chemie-nodemcu_chemie_pc_<date>.json`
- [ ] T040 [US3] 🔌 Flash `chemie-nodemcu` (specs/005 quickstart), run `tools/bench.py board --suite ../bench/suites/chemie … --firmware ../firmware-nodemcu/.pio/build/nodemcuv2/firmware.bin` and commit `bench/results/chemie-nodemcu_chemie_board_<date>.json`. Check SC-003: T1 typed and T2 within 10 % of spec 005 (158 ms, 5.1 chars/s) or the difference explained in `specs/007-benchmark-kpi-bericht/measurements.md`. If the board is not available, the baseline report shows the board KPIs as "not measured" with the reason in measurements.md.
- [ ] T041 [US3] 👤 The user fills in the S3 rating sheets `bench/results/chemie-nodemcu_chemie_pc_<date>.s3.tsv` and `bench/results/nodemcu_allgemein_pc.s3.tsv` (20 answers each, `grammar_ok` = `ja`/`nein`, data-model.md `Rating sheet.grammar_ok`), so S3 has a value in the baseline (SC-004).
- [ ] T042 [US3] Generate and commit `bench/results/baseline.md` and `bench/results/baseline.html` with `tools/bench_report.py` from the four results. Check in a clean clone without `models/` and `runs/` that the same command reproduces them (SC-001), and that every KPI shows a value, "not applicable" or a stated reason (SC-004).

**Checkpoint**: The roadmap's comparison point exists in the repository.

---

## Phase 7: User Story 5 - Run the demo script on two models side by side (Priority: P2)

**Goal**: `tools/bench_demo.py` puts two models' answers to a fixed demo script side by side.

**Independent Test**: Quickstart §9 with `chemie-nodemcu` and `nodemcu`: two boards, or one board with `--single` twice and `--merge`.

- [X] T043 [P] [US5] Write the demo script for this step `bench/demo/007.tsv` (12 questions: chemistry facts, a reverse question, a refusal, a greeting, one capital) per data-model.md "Demo script" (10–15 rows)
- [X] T044 [US5] Implement `training/src/ultratiny/bench/demo.py` and wire `tools/bench_demo.py` per contracts/cli.md:
  - two-board mode, `--single` run JSON and `--merge`
  - Markdown table with #, question, answer A/B and first character A/B (ms)
  - test with two `--a-exec`/`--b-exec` host consoles in `training/tests/test_bench_board.py`
- [ ] T045 [US5] 🔌 Run the demo for `chemie-nodemcu` vs. `nodemcu` and commit `bench/demo/007-chemie-nodemcu-vs-nodemcu.md`

**Checkpoint**: Every later step can show its demo with one command.

---

## Phase 8: User Story 6 - CI computes the PC KPIs of the repo model (Priority: P3)

**Goal**: CI fails when the repo model's quality KPIs or per-question classes change (clarified: any change, including improvements).

**Independent Test**: Quickstart §5: exit 0 unchanged; exit 1 with the question listed after a simulated change (SC-007).

- [X] T046 [US6] Implement `--check FILE` in `training/src/ultratiny/bench/pc.py`:
  - compare F1–F6, S1, S2, the S3 answers and every `items[].class` with the committed result; ignore `env`, timings and identity
  - print each changed KPI and question
  - exit 1 on any difference, exit 2 on a pin mismatch
- [X] T047 [P] [US6] Add a test in `training/tests/test_bench_pc.py`: checking against a copy with one changed item class fails, names that item, and an unchanged copy passes
- [X] T048 [US6] Add the CI steps in `.github/workflows/ci.yml` :
  - `python` job after pytest: `uv run python ../tools/bench.py pc --suite ../bench/suites/allgemein --model ../models/nodemcu.utny --check ../bench/results/nodemcu_allgemein_pc.json`
  - `runtime-host` job after the parity step: `tools/bench.py board --exec "../build/utiny-host --model ../models/nodemcu.utny --console" --sample parity`
  - confirm the python step finishes within 10 min (FR-024) and record its time in measurements.md

**Checkpoint**: Drift of answers, test sets or reference is caught on every pull request.

---

## Phase 9: Polish & Cross-Cutting Concerns

**Purpose**: Training exclusion, licenses, documentation

- [X] T049 Drop benchmark questions from training data (FR-005):
  - in `training/src/ultratiny/datagen.py` (v1 pipeline) and `training/src/ultratiny/hybrid.py` (beside the `kurzarbeit` drop), remove every training prompt whose normalised form equals one from `ultratiny.bench.suite.all_questions()`
  - report the count as `dropped_bench_match` in the data summary
  - add a test in `training/tests/test_datagen.py`
  - check that `make hybrid-smoke` and `test_determinism.py` still pass
- [X] T050 [P] Update `DATA_LICENSES.md`: add a `public-domain` row for the S1 general text (work, author, source URL); note that everything under `bench/` is evaluation-only, that its questions and topic texts were proposed by an allowed local LLM (`llm:<model>` per row in `bench/suites/*/proposals/`, spec FR-006) and spot-checked by the user, and that expected answers never come from the LLM
- [X] T051 [P] Complete `bench/README.md` with the commands of contracts/cli.md, the re-pin procedure (suite version bump), the rating-sheet workflow for S3 and the rule that test sets never enter training
- [ ] T052 [P] Update `specs/ROADMAP.md` step 1: mark spec 007 as done once T042 is committed, link `bench/results/baseline.md`, and replace the KPI draft table with a link to contracts/result-format.md "KPI definitions"
- [ ] T053 Run the whole quickstart.md (§1–§6, plus §7–§9 where hardware was available), check that `ruff check`, `ruff format --check` and `pytest -q` pass, and complete `specs/007-benchmark-kpi-bericht/measurements.md`

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: no dependencies.
- **Foundational (Phase 2)**: needs Phase 1 and blocks all stories.
- **US1 (Phase 3)**: needs Phase 2.
- **US2 (Phase 4)**: needs Phase 2. It can be built in parallel with US1, but quickstart §4 (T033) needs a result from T023.
- **US4 (Phase 5)**: needs US1 (T011 subject for parity, T016–T021 allgemein suite).
- **US3 (Phase 6)**: needs US1 (chemie suite T024–T027), US2 (report) and US4 (board mode). T041 (S3 ratings) needs T039 and T023.
- **US5 (Phase 7)**: needs US4's board link handling (T035).
- **US6 (Phase 8)**: needs T023 (committed result) and T037 (host board mode).
- **Polish (Phase 9)**: T049 needs T004; the rest come at the end.

### Within User Story 1

- T009 and T010 come first and fail until T011–T014 are done.
- T011 → T012 → T014 → T015.
- Allgemein data: T016 → T019 → T020 → T021 → T022 → T023; proposals: T017 → T018 (🖥️) → T019, T020, T026.
- Chemie data: T024 → T025 → T026 → T027 → T028.
- T013 must exist before T021.

### Human and hardware steps

| Task | Who | Blocks |
|------|-----|--------|
| T018 | 🖥️ | T019, T020, T026 (all test-set data) |
| T022 | 👤 | T023 |
| T027 | 👤 | T028, T039 |
| T038 | 🔌 | — (T040 can still run) |
| T039 | 🖥️ | T041, T042 |
| T040 | 🔌 | — (baseline can show "not measured") |
| T041 | 👤 | T042 (otherwise S3 shows "not rated") |
| T045 | 🔌 | — |

## Parallel Example: User Story 1

```text
# After Phase 2, in parallel:
T009 test_bench_lm.py        T010 test_bench_pc.py
T013 tools/bench_s2.py       T016 allgemein suite config      T017 bench_propose_llm.py
# Then the chain T011 → T012 → T014 while T018 (Spark) and T024 → T026 (chemie data) proceed.
```

## Parallel Example: User Story 2

```text
T029 test_bench_report.py   (parallel with any US1 implementation task)
T030 → T031 → T032 → T033
```

## Implementation Strategy

### MVP first (User Story 1 on the allgemein suite)

1. Phase 1 and Phase 2.
2. T009–T023: PC measurement of `nodemcu.utny`, result committed. The code (T009–T017) can be built
   and tested on the mini fixture suite while the Spark run (T018) is pending.
3. **Stop and validate**: quickstart §1–§2; this already gives reproducible PC KPIs for the repo model.

### Incremental delivery

1. **US1 (allgemein)** → **US2 report** → **US6 CI**. Everything except the proposal run (T018 🖥️)
   runs in the container; drift protection is in place early.
2. **US1 (chemie)**: needs the user review (T027).
3. **US4 board**: the host console first (T037), then the real board (T038 🔌).
4. **US3 baseline** (🖥️ + 🔌) → **US5 demo** → **Polish**.

### Notes

- The `[P]` tasks touch different files and have no open dependencies.
- Commit after each task or logical group. Pins change only together with a suite version bump.
- Every task that adds or changes a test set ends with a re-pin and, after the first comparison, a
  version bump (FR-004, FR-018).
