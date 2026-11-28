---

description: "Task list for 008-wissens-compiler"
---

# Tasks: Knowledge Compiler (Topic-Independent)

**Input**: Design documents from `specs/008-wissens-compiler/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/, quickstart.md

**Tests**: Included where the constitution or the spec requires them:
- Validation stops bad topic data and names file, line and rule (FR-004, FR-007)
- Parity of lookup and rendering, Python vs. C, on host and board (Principle III, FR-014)
- Compat against the frozen UTFT v1 answers (FR-015, SC-001)
- Determinism of the build (Principle IV, SC-007)
- The budget gate (Principle I, SC-003, SC-006)

No other test tasks.

**Organization**: Tasks are grouped by user story:
- US1 = chemistry topic compiled into a UTKI image, same answers as 006 (P1, MVP)
- US2 = reverse directions as lists and build-time rules, new chemistry facts (P2)
- US3 = second mini-topic (chess) without a code change, topic check (P2)
- US4 = LLM fact proposals with human review (P3, optional)

Board steps are marked 🔌, Spark steps 🖥️.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies on incomplete tasks)
- **[Story]**: US1–US4 as above; Setup, Foundational and Polish tasks have no story label

## Path Conventions

- Topics: `topics/<id>/` (repository root)
- Compiler and Python reference: `training/src/ultratiny/knowledge/`, tests in `training/tests/`
- C engine: `runtime/src/knowledge.c`, `runtime/include/utiny_knowledge.h`, tests in `runtime/tests/`
- Firmware: `firmware-nodemcu/src/main.cpp`; tools in `tools/`; images in `models/`

---

## Phase 1: Setup (freeze what UTFT v1 knows, create the skeleton)

**Purpose**: Everything that needs the old fact table must happen before it is removed (research R10, R13).

- [X] T001 Write the one-off oracle export in training/src/ultratiny/knowledge/compat.py (`export_oracle(utft_path, factset, out)`): render every (letter, key) pair through `facttable.answer_bytes` — every applicable pair, every not-applicable pair (each object of another class per letter), one unknown key per letter, the missing-table case — and write `letter, key, outcome, answer` as in `data-model.md` "Compat oracle" and contracts/topic-format.md `compat/`. Run it on `ut facts --config configs/chemie-hybrid.toml` and commit topics/chemie/compat/utft1_answers.tsv (record the UTFT sha256 `398b433c…` in its header comment).
- [X] T002 [P] Add the subcommand `image` to tools/bench.py and training/src/ultratiny/bench/pc.py (`bench.py image --facts IMAGE --suite S --out R.json`): image-only result with R3 (bytes), F7 (answerable facts) and R5 (R3 / F7), research R13. For UTFT v1, F7 is the number of facts.tsv rows the table renders as `fact`. Run it on the 006 table and commit bench/results/chemie-hybrid-utft1_chemie_image.json (F7 2,379, R5 12.23).
- [X] T003 [P] Create the package skeleton training/src/ultratiny/knowledge/{__init__.py,topic.py,rules.py,compile.py,image.py,propose.py} with module docstrings pointing to the contracts, and the directories topics/chemie/, topics/chemie/facts/, topics/chemie/compat/ (README line in topics/README.md: "a topic is data only", FR-001).
- [X] T004 [P] Create the fixture topics under training/tests/fixtures/topics/: `mini/` (2 classes with `order_by` and file order, relations of every type `text|int|dec|enum|ref`, `card one|many`, `reverse none|one|many`, views of every kind, one list long enough to be shortened, every rule kind) and one `bad_*` topic per validation rule of `data-model.md` Fact "Validation" (wrong type, second value for `card one`, duplicate, missing source, `llm:` source, key outside the alphabet, key > 12 B, name > 40 B, value > 60 B, rendered answer > 100 B, non-unique `reverse one`, rule conflict, list whose first item does not fit).

**Checkpoint**: oracle and 006 image result committed; skeleton and fixtures in place.

---

## Phase 2: Foundational (compiler core and Python reference)

**Purpose**: Topic loading, validation, image writer and reader. Every story needs them.

**⚠️ CRITICAL**: No user story work can begin until this phase is complete.

- [X] T005 Implement topic loading in training/src/ultratiny/knowledge/topic.py per contracts/topic-format.md: `topic.toml` (`data-model.md` Topic.id, Topic.schema_version, Topic.object_files/fact_files with sorted globs, Topic.alphabet, Topic.budget_bytes, Topic.compat), `schema.toml` texts (`data-model.md` Topic texts), classes (`data-model.md` Concept class.name, Concept class.order_by; ≤ 8 classes), relations (`data-model.md` Relation.name, Relation.subject, Relation.type, Relation.values, Relation.decimals, Relation.target, Relation.card, Relation.reverse), views (`data-model.md` View.name, View.kind, View.relation, View.classes, View.template, View.not_applicable, View.more, View.letter) and competency questions (`data-model.md` Competency question.view, .question, .key, .expect). Every error carries file, line or TOML key, and rule (contracts/topic-format.md "Errors").
- [X] T006 Implement object and fact validation in training/src/ultratiny/knowledge/topic.py: `data-model.md` Object.key, Object.name, Object.class, Object.source and Fact.subject, Fact.relation, Fact.value, Fact.source, plus the build-level checks of `data-model.md` Fact "Validation". Sources come from `datagen.allowed_source_prefixes()`; the prefix `llm:` is rejected for objects and facts (research R14). Record `data-model.md` Fact.origin (file:line). Ties under `order_by` are an error.
- [X] T007 Implement reverse directions in training/src/ultratiny/knowledge/rules.py: for every relation with `reverse ≠ none` build value → subjects in class order; `reverse = one` with two subjects stops the build naming both (FR-005, US2 scenario 2).
- [X] T008 Implement the UTKI v1 writer in training/src/ultratiny/knowledge/compile.py per contracts/image-format.md: header (80 B, CRCs, topic, schema version, `data_sha` over all source files in read order), string area (each distinct string once), classes, objects in class order, key index, relations with sorted value tables, 1/2-byte columns, posting-list blocks, views with slot bytes (`{r:…}` → `0x04` + relation index), topic texts, 4-byte alignment. Check every view prefix is non-empty and the image ≤ `data-model.md` Topic.budget_bytes. Write `build.json` (counts, size per section, F7, R5, provenance; `data-model.md` "Build report") deterministically.
- [X] T009 Implement the UTKI reader and Python reference in training/src/ultratiny/knowledge/image.py per contracts/query.md: validation (status `OK|MISSING|CORRUPT`, `data-model.md` Knowledge image), `view()` by letter or name, `prefix()`, `lookup()` with the outcomes of `data-model.md` Query (key length per Query.key), rendering of `na`/`unknown`/fallback, `{key}`/`{name}`/`{v}` per view kind (`data-model.md` View, table "What {key}, {name} and {v} mean"), `query()` for `/wissen` strings, `answer_bytes()` and `function_output()` with the signatures of facttable.py. Single values only here; lists in T028.
- [X] T010 Add `ut knowledge build|check|cases` to training/src/ultratiny/cli.py per contracts/cli.md (check steps 1–3 now; `--compat` in T014) and implement the answerable-fact count (distinct (view, key) with outcome `fact`, research R9) used for F7 and `n_answerable`.
- [X] T011 [P] Tests in training/tests/test_knowledge_topic.py: the `mini` fixture loads; each `bad_*` fixture fails with the expected file, line and rule.
- [X] T012 [P] Tests in training/tests/test_knowledge_image.py: build `mini`, read it back, check every competency question, every outcome (`fact`, `na`, `unknown`, `missing` for erased/corrupt data), header CRC and offset validation, and that two builds give byte-identical `.utki` and `build.json` (SC-007).

**Checkpoint**: `ut knowledge build` and `check` work on the fixture topic; the Python reference answers it.

---

## Phase 3: User Story 1 — Chemistry image with the same answers as 006 (Priority: P1) 🎯 MVP

**Goal**: The chemistry topic compiles into one UTKI image that answers every 006 question byte for byte, on the PC and on the board, and UTFT v1 is gone.

**Independent Test**: `ut knowledge check --topic ../topics/chemie --compat` reports 0 unlisted differences; `utiny-host --kb-cases` and `device_knowledge.py` match the Python cases; the 006 golden `printed` cases still pass (quickstart §1, §2, §4, §7).

### Chemistry topic

- [X] T013 [US1] Write topics/chemie/prepare.py (research R3, contracts/topic-format.md `prepare.py`): run `ultratiny.factgen.build` with training/configs/chemie-hybrid.toml and write topics/chemie/objects.tsv (classes `element`, `verbindung`, `reaktion`, `nachweisreaktion`; element order by atomic number) and topics/chemie/facts/generated/*.tsv (one file per class, relation names of `data-model.md` "Legacy mapping for chemistry", the 006 display values unchanged, sources as in factgen); `--check` exits 1 when the committed files differ. Commit the generated files.
- [X] T014 [US1] Write topics/chemie/topic.toml and topics/chemie/schema.toml: texts (`Das weiß ich leider nicht.`, `: dazu habe ich keine Angabe.`, `– `, `, `, ` und `), the classes, the relations of the 26 legacy views and the 26 views with letters, templates and not-applicable texts copied from training/data/templates/hybrid.toml (`{K}`/`{O}` → `{r:kategorie}`/`{r:ordnungszahl}`), one competency question per view; then implement `ut knowledge check --compat` in training/src/ultratiny/knowledge/compat.py (oracle vs. image through legacy letters, `data-model.md` "Compat oracle and change list": `changes.tsv`.reviewed = `yes` required) and make it pass with an empty topics/chemie/compat/changes.tsv.
- [X] T015 [US1] Build models/chemie.utki and models/chemie.build.json (`make knowledge`, new target in Makefile that builds every `topics/*/`), and models/chemie_cases.tsv with `ut knowledge cases` (contracts/query.md "Cases file"). Record image size, section sizes, F7 and R5 in specs/008-wissens-compiler/measurements.md (new file, same layout as 006).

### C engine, console and firmware

- [X] T016 [US1] Write runtime/include/utiny_knowledge.h and runtime/src/knowledge.c per contracts/image-format.md and contracts/query.md: `ut_kb_open` (validation, 128 B aligned read buffer, status `OK|MISSING|CORRUPT|WRONG_TOPIC`), `ut_kb_status_str`, `ut_kb_view_by_letter`, `ut_kb_view_by_name`, `ut_kb_prefix`, `ut_kb_finish` (rest, `na`, `unknown` with fallback separator, `missing`), `ut_kb_query` (full answer for `/wissen`), `ut_kb_topic`; no heap, no float, ≤ 1 KB static RAM (SC-006). Single values only here; lists in T030.
- [X] T017 [US1] Switch the console to the new API in runtime/src/console.c and runtime/include/utiny_console.h: the 006 `<fn>` state machine unchanged (contracts/query.md "Console: function output"), `/info` line `Wissen: …`, the new command `/wissen` (overview, letter + key, view name + key with the rest of the line as key, `/trace an` timing line; contracts/query.md "Direct query command", research R12), help text in `/hilfe`.
- [X] T018 [US1] Update runtime/host/utiny_host.c: `--facts` loads `.utki` into the 0xFF-filled 64 KB area with the alignment trap; new `--kb-cases FILE` and `--query "<view> <key>"` (contracts/query.md "Host tool").
- [X] T019 [US1] Tests and CMake in runtime/tests/test_knowledge.c, runtime/tests/test_console_logic.c and runtime/CMakeLists.txt: status cases, lookups and outcomes on a fixture image; the `<fn>` console path; `/wissen`; `--kb-cases` parity for models/chemie.utki against models/chemie_cases.tsv; the same in the `UT_IMAGE_ACCESS_CHECK` build (`knowledge_checked`, parity checked). Regenerate runtime/tests/fixtures/ (`kb_small.utki` from the `mini` fixture topic, `tiny_v2` golden with models/chemie.utki) via training/tools/make_runtime_fixtures.py.
- [X] T020 [US1] Update firmware-nodemcu/src/main.cpp: `static ut_kb kb`, `ut_kb_open` with the existing `facts_read` callback at boot, boot line `Wissen: …` (contracts/query.md "/info and boot lines"); keep firmware/main/console_uart.c building with `io->kb = NULL`. Run `pio run` and tools/budget_report.py (firmware ≤ 360,448 B, static RAM growth ≤ 1 KB vs. 006).

### Remove UTFT v1 and switch every user

- [X] T021 [US1] Remove runtime/src/facts.c, runtime/include/utiny_facts.h, runtime/tests/test_facts.c and the UTFT fixtures; remove training/src/ultratiny/facttable.py and its tests, and the `ut facts` command (contracts/cli.md "Removed"); keep `hybrid.build_facts` returning the fact set for datagen without writing `.utft`.
- [X] T022 [US1] Switch the Python users to `ultratiny.knowledge.image`: training/src/ultratiny/hybrid.py, golden.py (`facts_sha256` of the `.utki`), export.py and cli.py (`ut pipeline` builds the image of the config's `[knowledge] topic`, `ut export --facts` takes `.utki`), training/src/ultratiny/bench/subject.py and pc.py, training/configs/chemie-hybrid.toml and hybrid-smoke.toml (`[knowledge] topic = "../topics/chemie"`); update training/tests/test_evaluate_hybrid.py, test_bench_pc.py and test_determinism.py (compare `.utki` bytes).
- [X] T023 [US1] Switch the tools: tools/budget_report.py and training/src/ultratiny/cli.py budget check (`UTKI` magic, limit 58,982 B), Makefile (`FACTS ?= models/chemie.utki`, `nodemcu-flash-facts` checks `UTKI`), tools/devlib.py (parse `Wissen: …`, new `query(view, key)`), tools/device_smoke.py (accept `Wissen: OK`), training/src/ultratiny/bench/board.py (identity from the UTKI `data_sha`).
- [X] T024 [US1] Update .github/workflows/ci.yml: `prepare.py --check`, `ut knowledge check --topic ../topics/chemie --image ../models/chemie.utki --compat`, knowledge parity in CTest, budget report with models/chemie.utki in `runtime-host` and `firmware-nodemcu`.
- [X] T025 [US1] 🔌 Flash firmware and models/chemie.utki; write tools/device_knowledge.py (contracts/cli.md: every case as `/wissen` under `/trace an`, compare, report max/median lookup µs) and run it against models/chemie_cases.tsv. Record `/info`, case result, lookup times (SC-005 ≤ 50 ms) and free heap in specs/008-wissens-compiler/measurements.md.

**Checkpoint**: chemistry answers are byte-identical to 006 on PC and board; UTFT v1 is gone; CI green. MVP done.

---

## Phase 4: User Story 2 — Reverse lists and build-time rules (Priority: P2)

**Goal**: Two-way relations answer reverse questions as lists, three rule kinds derive facts at build time, and chemistry gains ≥ 20 % answerable facts at ≤ 70 % bytes per fact.

**Independent Test**: build report shows F7 ≥ 2,855 and R5 ≤ 8.56; every derived fact has its rule and inputs in `build.json`; reverse queries render identically on PC, host and board (quickstart §1, §3, §4).

- [X] T026 [US2] Implement the rule kinds in training/src/ultratiny/knowledge/rules.py per research R8: `class` (`equals` or `between`, `except`), `chain`, `table` (`data-model.md` Rule.id, Rule.kind, Rule.if_relation, Rule.equals/between, Rule.except, Rule.first/then, Rule.from/map, Rule.add_relation/add_value), the fixpoint (≤ 32 rounds, ≤ 65,535 facts), the derived-fact states `new|same|conflict` (`data-model.md` Rule "States of a derived fact"), and provenance in `build.json` (`data-model.md` Fact.origin).
- [X] T027 [P] [US2] Tests in training/tests/test_knowledge_rules.py: every rule kind on the `mini` fixture; a conflict with an explicit fact and between two rules stops the build naming both origins (FR-007); a growing rule set stops at the limit; derived facts equal to explicit ones are dropped.
- [X] T028 [US2] Implement `card many` forward values and reverse lists in the writer (posting lists already in T008) and the list rendering in training/src/ultratiny/knowledge/image.py per contracts/query.md "Lists" (budget `100 − A`, full list or `L(k)` with `more`, at least one item); in training/src/ultratiny/knowledge/compile.py check that `L(1)` fits for every list (`data-model.md` View.more required for multi-item views).
- [X] T029 [P] [US2] Extend training/tests/test_knowledge_image.py with list cases: full list, shortened list with `{n}`, one-item list, item order (value order forward, class order reverse).
- [X] T030 [US2] Implement the same list rendering in runtime/src/knowledge.c (count pass and print pass over the posting list, no buffer) and extend runtime/tests/test_knowledge.c with the `mini` list cases; regenerate the fixture cases.
- [X] T031 [US2] Extend the chemistry topic (research R9): add `gruppe_nr` to topics/chemie/prepare.py output, the `hauptgruppe` table rule and the family class rules (`gruppe_nr` 1 except H → Alkalimetalle, 2 → Erdalkalimetalle, 17 → Halogene, 18 → Edelgase) in topics/chemie/schema.toml, and reverse views with templates, `more` texts and competency questions for protonen, elektronen, atommasse, molare_masse, neutronen, gruppe_nr, periode, familie, kategorie, zustand, aussenelektronen, schalen, wertigkeit, bindung, saeure_base. Templates avoid inflection (grammar is spec 010).
- [X] T032 [US2] Rebuild models/chemie.utki, run the compat check and review every new difference into topics/chemie/compat/changes.tsv (`data-model.md` "Compat oracle and change list": `changes.tsv`.reason and `changes.tsv`.reviewed; expected: families filled by rules); rebuild models/chemie_cases.tsv. Record F7, R5, size per section in measurements.md; if SC-002/SC-003 are missed, apply the R6/R9 fallbacks and record the measurement.
- [X] T033 [US2] 🔌 Run tools/device_knowledge.py with the new cases (reverse lists included) and record lookup times for the longest lists in measurements.md.

**Checkpoint**: ≥ 2,855 answerable facts, ≤ 8.56 B per fact, every derived fact traceable, lists identical on PC and board.

---

## Phase 5: User Story 3 — Chess topic without a code change (Priority: P2)

**Goal**: A second topic compiles and answers on PC and board in a change set that touches only topic data and its test cases; a model of another topic is detected.

**Independent Test**: quickstart §5 (`git diff --stat` of the chess commit shows no code) and §7 (chess cases on the board, wrong-topic line).

### Topic check (code, before the chess data)

- [X] T034 [US3] Write `"topic"` into the model meta from the config's `[knowledge] topic` in training/src/ultratiny/export.py and cli.py `cmd_export` (`data-model.md` Topic.id), research R11.
- [X] T035 [US3] Implement the topic check: runtime/src/console.c reads `topic` from the meta (via `meta_str`), firmware-nodemcu/src/main.cpp and runtime/host/utiny_host.c set `WRONG_TOPIC` on a mismatch (`data-model.md` Knowledge image status), print `Wissen: falsches Thema (Bild …, Modell …)` and answer fact questions with the missing text; `/info` adds `Thema nicht geprüft` for models without `topic`. Host test in runtime/tests/test_console_logic.c with a fixture model whose meta names another topic.
- [X] T036 [US3] Register topic-generic test hooks so a new topic needs no code: CMake loops over `models/*_cases.tsv` (runtime/CMakeLists.txt), CI loops over `topics/*/` for `check --image` (.github/workflows/ci.yml), pytest parametrises the competency check over `topics/*/` (training/tests/test_knowledge_topics.py).

### Chess data (data only, own commit)

- [X] T037 [US3] Write topics/schach/topic.toml, topics/schach/schema.toml, topics/schach/objects.tsv and topics/schach/facts/figuren.tsv per `data-model.md` "Second topic: chess pieces" (≈ 30–36 facts, source `own`, rules `wert = 3 → Leichtfigur` and `wert between [5, 9] → Schwerfigur`, a competency question for every view); build models/schach.utki, models/schach.build.json and models/schach_cases.tsv. Commit only these files; check with `git diff --stat` that no line in training/src/ultratiny/knowledge/, runtime/, firmware-nodemcu/ or contracts/image-format.md changed (SC-004).
- [ ] T038 [US3] 🔌 Flash models/schach.utki, run tools/device_knowledge.py with models/schach_cases.tsv, then boot with a model whose meta names `chemie` and check the wrong-topic line, the missing text for a fact question and a greeting for `Hi`. Record in measurements.md.

**Checkpoint**: chess passes on PC and board with zero code lines in its change set; a wrong topic is reported.

---

## Phase 6: User Story 4 — LLM fact proposals with review (Priority: P3, optional)

**Goal**: An LLM proposes missing facts into a review list; only accepted rows with a real source enter the topic.

**Independent Test**: quickstart §9.

- [X] T039 [P] [US4] Implement `ut knowledge propose` and `ut knowledge accept` in training/src/ultratiny/knowledge/propose.py and cli.py per contracts/cli.md and research R14 (`data-model.md` Fact proposal.subject/relation/value, Fact proposal.source, Fact proposal.reason, Fact proposal.accepted), using the Spark client of training/tools/shorten_llm.py; `propose` writes only topics/<id>/proposals/<date>.tsv, `accept` writes only topics/<id>/facts/accepted.tsv.
- [X] T040 [P] [US4] Tests in training/tests/test_knowledge_propose.py with a fake LLM client: no fact file changes on `propose`; `accept` copies only `yes` rows with an allowed non-`llm:` source and reports the rest.
- [ ] T041 [US4] 🖥️ Run one proposal round for an existing chemistry gap on the Spark, review it with the user, and record the counts (proposed, accepted, rejected) in measurements.md.

**Checkpoint**: proposals never change facts without a person's decision.

---

## Phase 7: Benchmark, demo and polish

**Purpose**: Measurement against baseline and 006 (FR-020), the demo (FR-021), documentation.

- [X] T042 [P] Add F7 and R5 to the KPI tables in training/src/ultratiny/bench/report.py (names, direction, source, threshold 0), board.py (`not_measured`) and the result format doc specs/007-benchmark-kpi-bericht/contracts/result-format.md (KPI table rows, "added by spec 008").
- [X] T043 [P] Add `--topic` to tools/bench_export_facts.py (rows from views with a legacy letter, research R13); compare its output with bench/suites/chemie/facts.tsv; if it differs beyond the reviewed changes, bump `version` in bench/suites/chemie/suite.toml, re-pin, and record the reason in measurements.md.
- [X] T044 Run `tools/bench.py image` on models/chemie.utki, write bench/results/chemie_chemie_image_<date>.json and the report bench/results/008.md and .html against the baseline and the 006 image result (quickstart §6).
- [X] T045 Write bench/demo/008.tsv (10–15 items: fact questions the 006 model understands, ≥ 3 reverse queries and ≥ 2 rule results as `/wissen` items) and let tools/bench_demo.py and training/src/ultratiny/bench/demo.py send `/wissen` items as commands (`—` on boards without it).
- [ ] T046 🔌 Run the demo next to `chemie-nodemcu` (needs `chemie-hybrid` from spec 006 T044) and commit bench/results/demo_008.md; run tools/device_parity.py with the 006 golden cases and the 007 board benchmark with models/chemie.utki (first character ≤ 2 s, ≥ 5 chars/s).
- [ ] T047 🔌 Erase the fact area (`esptool erase_region 0x100000 0x10000`), reboot and check `Wissen: fehlt`, the missing text for a fact question and model answers for greetings and explanations. Record in measurements.md.
- [X] T048 [P] Update the documentation: README.md (knowledge images, `make knowledge`, `/wissen`), training/README.md (`ut knowledge`, topic layout), topics/README.md (how to write a topic), DATA_LICENSES.md (`llm:` not allowed as a fact source), specs/006-hybrid-chemielehrer/contracts/fact-table-format.md (pointer: superseded by UTKI v1).
- [X] T049 Update specs/ROADMAP.md: step 3 status with F7, R5 and image size, KPI table rows F7 and R5, "Zweites Testthema" decided (chess), open points.
- [ ] T050 Run `make budget BOARD=nodemcu`, the full CTest suite (including checked builds) and pytest; confirm CI is green; walk through quickstart.md and tick the spec checklist.

---

## Dependencies & Execution Order

### Phase dependencies

- **Setup (T001–T004)**: T001 and T002 need the UTFT v1 code, so they must finish before T021. T003 and T004 are [P].
- **Foundational (T005–T012)**: after T003/T004. T005 → T006 → T007 → T008 → T009 → T010. T011 needs T006; T012 needs T009/T010.
- **US1 (T013–T025)**: after Foundational. T013 → T014 → T015. T016 → T017 → T018 → T019 (T019 needs T015). T020 needs T016/T017. T021 needs T001, T002, T014 (compat green) and T019. T022 and T023 need T021. T024 needs T022/T023. T025 needs T020/T015.
- **US2 (T026–T033)**: after Foundational; the chemistry part needs US1. T026 → T027. T028 → T029. T030 needs T016 and T028. T031 needs T026, T028 and T014. T032 needs T031 and T030. T033 needs T025 and T032.
- **US3 (T034–T038)**: T034 and T035 need US1 (console, firmware). T036 needs T019/T024. T037 needs T034–T036 and T028 (chess has lists). T038 needs T037 and T025.
- **US4 (T039–T041)**: after Foundational; independent of the others.
- **Polish (T042–T050)**: T042/T043 after T002 and T015. T044 needs T032 and T042. T045 needs T031. T046 needs T045 and spec 006 T044. T047 needs T025. T048–T050 last.

### User story dependencies

- **US1** is the MVP and stands alone after Foundational.
- **US2** adds rules and lists; its compiler part is independent, its chemistry part builds on the US1 topic and C engine.
- **US3** needs the US1 engine and, for its lists, the US2 list rendering; its data commit must come after every code change it relies on (SC-004).
- **US4** only needs the Foundational compiler.

## Parallel Examples

```text
Setup:        T001 | T002 | T003 | T004
Foundational: T011 alongside T007–T010 once T006 is done; T012 after T010
US1:          (T013→T014→T015) | (T016→T017→T018), then T019; T023 alongside T022
US2:          (T026→T027) | (T028→T029); then T030 and T031
US3:          T034 | T036 while T035 runs
US4:          T039 | T040 at any time after Foundational
Polish:       T042 | T043 | T048
```

## Implementation Strategy

### MVP first (User Story 1)

1. Setup: freeze the oracle and the 006 image result while UTFT v1 still exists.
2. Foundational: compiler and Python reference on the fixture topic.
3. US1: chemistry topic, compat green, C engine, console, firmware; then remove UTFT v1.
4. **Stop and validate**: compat check, host parity, board cases (quickstart §1, §2, §4, §7).

### Incremental delivery

1. MVP (US1): same answers, new image, one code path.
2. US2: rules and reverse lists → F7 and R5 targets.
3. US3: chess topic proves topic independence; wrong-topic check.
4. Polish: benchmark report, demo next to `chemie-nodemcu`, roadmap.
5. US4 when a topic needs filling.

### Notes

- The board demo with the chemistry model (T046) waits for `chemie-hybrid` (spec 006 T044); everything
  else can be done and measured without it.
- Commit after each task or logical group; the chess data (T037) is its own commit.
