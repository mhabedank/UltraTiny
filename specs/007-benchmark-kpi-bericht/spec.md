# Feature Specification: Benchmark and KPI Report

**Feature Branch**: `claude/benchmark-kpi-bericht-rhojdq`

**Created**: 2026-11-23

**Status**: Draft

**Input**: User description: "Schritt 1 aus specs/ROADMAP.md (Spec 007: Benchmark und KPI-Bericht). Lies vorher specs/ROADMAP.md (Entscheidungen, Regeln, KPI-Entwurf), die dort unter „Grundlage“ verlinkten Befunde in research/2026-11-architektur/ und specs/006-hybrid-chemielehrer/ (vorhandene Testmengen und Messungen)."

## Background

The roadmap (`specs/ROADMAP.md`, 2026-11-23) plans seven steps from today's chemistry model to a
topic-independent knowledge kit (specs 006, 008–013). Rule 3 of the roadmap says every step runs
through the same benchmark and is compared against a fixed baseline and against its predecessor.
Today every spec measures in its own way:

- Spec 005 reports "held-out phrasings" from the data generator of that run (70.0 % for the repo
  model `nodemcu`, 80.9 % for `chemie-nodemcu`), so the number changes whenever the generator or
  its templates change, and two specs cannot be compared on it.
- Spec 006 adds the frozen short-test set `training/data/eval/kurzarbeit.tsv` (130 questions;
  98 fact, 4 multi, 16 explain, 8 refuse, 4 unknown), but its other held-back sets are again
  produced by the generator of each run.
- Board timings (first character 158 ms, 5.1 chars/s, free heap 4,960 B) were measured once by
  hand with `device_smoke.py` for one typed prompt; pasted prompts and full context were not
  measured.
- Nothing measures language quality (bits per character on unseen text) or usable context,
  although research 4 names exactly these as the deciding quantities for the core change in specs
  011–013 ([04 Offene Fragen](../../research/2026-11-architektur/04-architekturen.md#offene-fragen)).

Research 1 §8 ([Methodik](../../research/2026-11-architektur/01-performance-boost.md)) adds the
method: check the budget first, compare with several seeds, and count an improvement only when it
exceeds a noise threshold fixed in advance (at 60K parameters the model shape alone moved loss by
22.6 %, more than any architecture effect).

The baseline model `chemie-nodemcu` (spec 005, trained on the DGX Spark) exists only on the Spark.
The repo model `nodemcu` (`models/nodemcu.utny`) is trained on general knowledge (capitals,
element symbols, self-description), not on the chemistry curriculum.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Measure a model on the PC with one command (Priority: P1)

The developer has a trained model (with or without a knowledge image, e.g. the fact table of spec
006) and runs one command on the PC. The command asks the frozen benchmark questions through the
bit-exact PC reference, scores every answer automatically and writes one result file with all PC
KPIs: fact quality (F1–F6), resources from the build (R2–R4) and language (S1, S2, and the S3
answers ready for rating). The same command works for any topic for which a benchmark suite exists.

**Why this priority**: Every later step is judged by these numbers. Without a stable PC
measurement there is no baseline, no report and no CI check.

**Independent Test**: Run the command on `models/nodemcu.utny` with the general-knowledge suite
and on a chemistry model with the chemistry suite; check that the result file holds every PC KPI
with its test-set versions, and that a second run on the same inputs gives identical quality
values.

**Acceptance Scenarios**:

1. **Given** a model file and a benchmark suite, **When** the developer runs the PC benchmark,
   **Then** a result file is written that contains F1–F6, R2–R4, S1, S2, the S3 answer sample, the
   identity of the model, knowledge image, suite and test sets (content hashes), the git commit,
   the date and the machine.
2. **Given** the same model, knowledge image and suite, **When** the PC benchmark runs twice,
   **Then** all quality KPIs (F, S1, S2, S3 answers) are identical.
3. **Given** a model that answers in free text (spec 005 style) and a model that answers through a
   knowledge image (spec 006 style), **When** both are measured with the same suite, **Then** both
   are scored on the answer text the user would see, so their F-KPIs are directly comparable.
4. **Given** an answer to a fact question, **When** it is scored, **Then** it falls into exactly
   one class: correct, wrong fact, refused, or no usable answer, and the result lists the class
   per question.
5. **Given** a test-set file whose content does not match its pinned hash, **When** the benchmark
   starts, **Then** it stops with a clear error naming the file instead of measuring.

---

### User Story 2 - Compare a step with the baseline and its predecessor in a report (Priority: P1)

The developer runs a second command on two or more result files (baseline, predecessor, new step)
and gets a comparison report in Markdown and as an HTML page. For each KPI the report shows the
values, the difference and a verdict: better, worse, unchanged (within the noise threshold), not
comparable (different test-set version) or not measured. Budget violations are marked as such.

**Why this priority**: The roadmap's rule 3 and rule 5 are only kept if the comparison is
automatic and honest. A number without its noise threshold invites wrong conclusions.

**Independent Test**: Generate the report from the committed baseline result and from a fresh
result of the repo model; check verdicts, noise thresholds and budget marks by hand for three
KPIs.

**Acceptance Scenarios**:

1. **Given** a baseline result and a step result, **When** the report is generated, **Then** every
   KPI row shows baseline value, step value, difference, direction (↑ or ↓ is better), noise
   threshold and verdict.
2. **Given** a difference smaller than or equal to the KPI's noise threshold, **When** the report
   is generated, **Then** the verdict is "unchanged", even if the raw number moved.
3. **Given** results from three seeds for the same step, **When** the report is generated,
   **Then** it shows mean and spread per KPI, and a change only counts as better or worse if it
   exceeds both the fixed noise threshold and twice the seed spread.
4. **Given** a step whose RAM arena, reserve or flash use breaks a budget from the constitution or
   the roadmap (arena ≤ 35 KB, ≥ 10 % reserve), **When** the report is generated, **Then** the
   budget section marks it as failed and the report's summary says "budget broken".
5. **Given** two results measured with different versions of a test set, **When** the report is
   generated, **Then** the affected KPIs are marked "not comparable" instead of showing a
   difference.
6. **Given** the same result files, **When** the report is generated twice, **Then** both reports
   are identical (apart from the generation time).

---

### User Story 3 - Commit the baseline once so comparisons work without the Spark (Priority: P1)

The developer measures `chemie-nodemcu` once (on the Spark or wherever the model file is, and on
the board) and commits the result files. From then on every report compares against this baseline
without needing the model file. The repo model `nodemcu` gets its own committed result.

**Why this priority**: The baseline model lives only on the Spark; without committed results no
comparison in later specs is possible. This is the demo of this step.

**Independent Test**: In a fresh checkout without access to the Spark, generate the baseline
report for `chemie-nodemcu` and `nodemcu` from the committed files.

**Acceptance Scenarios**:

1. **Given** a fresh checkout, **When** the developer generates the baseline report, **Then** it
   shows all PC KPIs of `chemie-nodemcu` (chemistry suite) and of `nodemcu` (general-knowledge
   suite) and the board KPIs that were measured, without any model file being present.
2. **Given** the committed baseline result, **When** the developer reads it, **Then** it records
   which model (content hash), which test sets (hashes), which firmware and which board it was
   measured with, and how many seeds (one, for the baseline).

---

### User Story 4 - Measure speed and resources on the board (Priority: P2)

With a NodeMCU connected over USB, the developer runs the board command. It flashes nothing on
its own; it uses the firmware and model already on the board, sends a fixed set of questions and
measures T1 (first character, typed and pasted), T2 (characters per second), T3 (characters per
second near full context), R1 (arena peak and free heap after boot) and a fixed sample of the F1
and F5 questions. It checks that the board's answers are identical to the PC reference and writes
a board result file.

**Why this priority**: Speed and RAM are the hard limits of every step (constitution I), but the
PC measurement already covers fact and language quality, so the board part comes second.

**Independent Test**: Run the board command against `chemie-nodemcu` (or `nodemcu`) on one board
and compare T1/T2/R1 with the values in `specs/005-nodemcu-port/measurements.md`.

**Acceptance Scenarios**:

1. **Given** a connected board, **When** the board benchmark runs, **Then** the result contains
   T1 (typed and pasted, median and worst value), T2, T3, R1, the board sample of F1 and F5, and
   the identity of firmware, model and knowledge image reported by the board.
2. **Given** a board answer that differs from the PC reference for the same question, **When** the
   benchmark finishes, **Then** the result lists the mismatch and the report marks the run as
   "parity broken".
3. **Given** a board that resets, hangs or stops answering during the run, **When** the benchmark
   detects it, **Then** it records the event and the affected question, continues with the next
   one when the board is back, and the result is marked incomplete.

---

### User Story 5 - Run the demo script on two models side by side (Priority: P2)

For the demo of each roadmap step, the developer runs a fixed demo script (10–15 questions per
step) against two boards or two firmware images and gets both answers side by side, with timing
for each answer.

**Why this priority**: Rule 2 of the roadmap asks for a visible demo per step; it builds on the
board mode of US4.

**Independent Test**: Run the demo script with `chemie-nodemcu` and `nodemcu` (two boards, or the
same board flashed one after the other) and check the side-by-side output.

**Acceptance Scenarios**:

1. **Given** two connected boards, **When** the demo runner runs a demo script, **Then** it asks
   each question on both boards and writes a table: question, answer A, answer B, first-character
   time A and B.
2. **Given** only one board, **When** the developer runs the demo script once per image and then
   merges the two runs, **Then** the same side-by-side table is produced.
3. **Given** a demo script, **Then** it is a versioned file of 10–15 questions, separate from the
   benchmark test sets, and the output names both models.

---

### User Story 6 - CI computes the PC KPIs of the repo model (Priority: P3)

On every pull request the CI computes the PC KPIs of the model committed in the repository and
checks them against its committed result, so a change to runtime, reference or test sets that
silently changes answers is caught.

**Why this priority**: It protects the benchmark from drifting, but the benchmark has to exist
first.

**Independent Test**: Change one answer-relevant detail locally (e.g. one test question without
re-pinning), run the CI step and see it fail with a clear message.

**Acceptance Scenarios**:

1. **Given** an unchanged repository, **When** CI runs, **Then** the PC benchmark of the repo model
   passes and its quality KPIs equal the committed result.
2. **Given** a change that alters the repo model's answers, **When** CI runs, **Then** it fails and
   names the KPIs and questions that changed; the fix is a re-run and commit of the result in the
   same pull request.

### Edge Cases

- A question contains a character the model's alphabet does not know: the reference handles it as
  the board does; S1 counts such characters separately and reports text coverage.
- A model has a context shorter than question plus expected answer: the question is still asked;
  a truncated answer is scored as it is (usually "no usable answer").
- The answer contains the right value and also a wrong value of the same kind: scored as wrong
  fact, because a student cannot tell which one is right.
- A model with knowledge image but missing or corrupt image: the run stops before measuring;
  measuring the model without its image is a separate, explicitly requested run.
- A test question also appears (after normalisation) in the model's recorded training data: the
  result reports the overlap per test set, and the report flags affected KPIs.
- Hand ratings for S3 belong to a different answer text (answers changed): the old ratings are
  not reused; S3 shows "not rated".
- A step result without board measurement: board KPIs show "not measured", never zero.
- The baseline has one seed, the step three: the report uses the fixed noise threshold for the
  verdict and states that the baseline has no seed spread.
- The topic has no relations with numbers (e.g. capitals only): KPIs that do not apply are
  "not applicable" in the suite definition, not zero.

## Requirements *(mandatory)*

### Functional Requirements

**Benchmark suites and test sets**

- **FR-001**: The benchmark MUST be organised in suites, one per topic. A suite consists only of
  data and configuration: test sets, question types with their value classes, the reference facts,
  the demo scripts and the noise thresholds. Nothing topic-specific may be in the benchmark logic
  (roadmap rule 6).
- **FR-002**: The project MUST include two suites: **chemistry** (the curriculum of specs 003–006)
  and **general knowledge** (the topic of the repo model `nodemcu`: capitals, element symbols,
  self-description). The second suite MUST run without any change to the benchmark logic and serves
  as the topic-independence test of this spec.
- **FR-003**: The chemistry suite MUST contain these frozen test sets:
  (a) **unseen phrasings** for F1: at least 200 fact questions covering every question type of the
  topic, written independently of every training template, with the expected value per question;
  (b) **unknown objects** for F3: at least 40 questions in the topic's question forms about objects
  that are not in the reference facts (e.g. invented or out-of-curriculum substances);
  (c) **off-topic questions** for F3: at least 40 questions outside the topic, none of them taken
  from the refusal training data (`abweisen.tsv`);
  (d) the **short-test set** `kurzarbeit.tsv` of spec 006 for F5;
  (e) the **S1 test text**: at least 20,000 characters of German text not used in training, half
  topic text and half general German, with recorded source and license;
  (f) the **S2 recall test**: at least 100 probes in which a word named early in a text is asked
  for later, at distances in steps from 16 characters up to at least four times the largest
  context used by any model in the roadmap;
  (g) the **S3 sample**: 20 fixed prompts that need a free-text answer (greeting, explanation,
  refusal).
  The general-knowledge suite MUST contain at least (a), (b), (c), (e) and (f), sized for its
  smaller topic (at least 60 questions in (a)).
- **FR-004**: Every test set MUST be pinned by its SHA-256 hash in the suite. The benchmark MUST
  refuse to run when a file does not match its pin. Changing a test set MUST create a new test-set
  version; results with different versions of a set MUST NOT be compared on the KPIs that use it.
- **FR-005**: The test sets MUST be excluded from all future training data: the data generators of
  later specs MUST drop every training prompt that equals a test question after normalisation (as
  spec 006 already does for `kurzarbeit.tsv`). The benchmark MUST report, for every test set, how
  many of its questions occur in the model's recorded training data when that data is available.
- **FR-006**: New test questions MAY be proposed by a large language model but MUST be reviewed
  and accepted by a person before they are pinned; the review is recorded with the set.

**Scoring**

- **FR-007**: All F-KPIs MUST be scored on the final answer text that the user would see on the
  board (after the knowledge image filled in its values, if any), so that free-text models and
  knowledge-image models are measured the same way.
- **FR-008**: Each answer to a fact question MUST be assigned exactly one class: **correct** (the
  expected value appears and no other value of the same value class), **wrong fact** (a value of
  the question's value class appears that is not an accepted expected value), **refused** (the
  answer is one of the suite's refusal texts or "don't know" forms), or **no usable answer**
  (anything else). Value matching MUST respect upper and lower case for symbols and formulas and
  MUST accept number formats defined per value class in the suite (e.g. decimal comma or point,
  rounding to the stated precision, optional unit).
- **FR-009**: The KPIs MUST be defined as follows (all rates in percent with the count behind
  them):
  - **F1** correct / all questions of the unseen-phrasings set, also broken down per question type;
  - **F2** wrong fact / all fact questions of the unseen-phrasings and short-test sets (target
    ≤ 1 %);
  - **F3** refused / all questions of the unknown-objects and off-topic sets, also per set;
  - **F4** refused / all questions of the unseen-phrasings set;
  - **F5** short-test score as defined in spec 006 (fact and multi questions correct, explain
    questions contain all required keywords, refuse and unknown questions refused);
  - **F6** number of reference facts (object × property) that the system answers correctly when
    asked with the suite's canonical question for that property;
  - **T1** time from sending the end of the question to the first visible answer character, for a
    typed question (characters at human speed) and for a pasted question (all at once), median and
    worst value;
  - **T2** answer characters per second after the first character, median over the board sample;
  - **T3** answer characters per second for prompts whose question and answer fill at least 90 %
    of the model's context;
  - **R1** peak arena use and free heap after boot, as reported by the board;
  - **R2** flash size of the model, **R3** flash size of the knowledge image (0 if none);
  - **R4** (R2 + R3) / F6, bytes per answerable fact;
  - **S1** bits per character of the model on the S1 test text, for the topic half, the general
    half and both, with the share of characters the model's alphabet covers;
  - **S2** the largest distance at which the recall probes are answered correctly at least 80 % of
    the time, plus the full accuracy-by-distance curve;
  - **S3** share of the 20 S3 answers rated "grammar ok" by a person.
- **FR-010**: Quality KPIs (F, S) MUST be measured through the PC reference that is bit-exact with
  the board (constitution III); the board sample MUST confirm this with identical answers.

**Measurement runs**

- **FR-011**: One command MUST measure a model on the PC (with an optional knowledge image) for a
  given suite and write one machine-readable result file. A second command MUST do the board
  measurement and write a board result file. Both result files MUST record: model and knowledge
  image content hashes, suite and test-set versions, firmware identity (board), git commit, seed(s)
  of the training run if known, date and machine or board.
- **FR-012**: Result files MUST be stored under `bench/results/` with a name that identifies model,
  suite and date; committed results MUST be readable without the model file.
- **FR-013**: The board measurement MUST use the firmware and model already on the board, MUST NOT
  flash or erase anything on its own, MUST compare every board answer with the PC reference and
  MUST record resets, hangs and timeouts per question instead of aborting the whole run.
- **FR-014**: The board sample MUST be fixed in the suite: at least 30 questions from the F1 set,
  the full short-test set, and the prompts for T3; one board run MUST finish within 30 minutes.
- **FR-015**: S3 ratings MUST be stored next to the result as a separate file that is tied to each
  rated answer's text; the benchmark MUST produce an empty rating sheet for unrated answers.

**Report**

- **FR-016**: A third command MUST build a comparison report from two or more result files
  (baseline, predecessor, step; optionally several seeds per model) as Markdown and as a
  self-contained HTML page.
- **FR-017**: The report MUST show per KPI: value(s), difference, better direction, noise threshold
  and a verdict (better, worse, unchanged, not comparable, not measured, not applicable).
- **FR-018**: Each KPI MUST have a noise threshold that is fixed in the suite before the first
  comparison is made. A change MUST count as better or worse only when it is larger than the noise
  threshold and, when several seeds are present, larger than twice the seed spread (research 1 §8,
  roadmap rule 5). Changing a threshold later MUST be a versioned change of the suite.
- **FR-019**: The report MUST contain a budget section that checks R1–R3 and the firmware size
  against the constitution's budgets and the roadmap's gate (arena ≤ 35 KB, ≥ 10 % reserve) and
  marks every breach; the report summary MUST state "budget broken" if any budget is broken, and
  "parity broken" if any board answer differed from the PC.
- **FR-020**: The report MUST list, per question, answers that changed class between the compared
  results (e.g. correct → wrong fact), so that regressions are visible behind the rates.
- **FR-021**: The report MUST be reproducible: the same result files give the same report apart
  from its generation time.

**Demo runner and baseline**

- **FR-022**: A demo runner MUST ask the questions of a demo script on two boards (or merge two
  single-board runs) and write a side-by-side table of answers and first-character times. Demo
  scripts are versioned files with 10–15 questions, kept apart from the benchmark test sets.
- **FR-023**: The baseline `chemie-nodemcu` MUST be measured once on the PC (chemistry suite) and
  on the board, and the repo model `nodemcu` on the PC (general-knowledge suite) and on the board;
  all four result files and the resulting baseline report MUST be committed.
- **FR-024**: The CI MUST run the PC benchmark of the repo model with its suite on every pull
  request and fail when its quality KPIs or per-question classes differ from the committed result
  or when a test-set pin does not match. The CI step MUST finish within 10 minutes on the CI
  machine.

### Key Entities

- **Benchmark suite**: everything needed to measure one topic: test sets, question types with
  value classes and canonical questions, reference facts, refusal forms, board sample, demo
  scripts, noise thresholds; has a version.
- **Test set**: a frozen list of questions (or a text, for S1/S2) with expected values or classes;
  identified by its SHA-256 pin and a version.
- **Measurement run**: one measurement of one model (plus optional knowledge image) with one suite
  on the PC or the board; produces a result file.
- **Result file**: KPI values, per-question answers and classes, overlap counts, identities
  (model, knowledge image, firmware, suite, test sets, commit, seed, machine or board, date).
- **Rating sheet (S3)**: per answer text a yes/no grammar rating by a person.
- **Comparison report**: the report built from several result files, with verdicts, budget
  section, parity status and the list of changed answers.
- **Demo script**: 10–15 fixed questions for one roadmap step, with the side-by-side output of two
  models.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A developer in a fresh checkout produces the baseline report for `chemie-nodemcu`
  and `nodemcu` from committed files with one command, without access to the Spark or a board.
- **SC-002**: Measuring a model on the PC takes one command and, for a NodeMCU-sized model, at
  most 15 minutes on a 4-core CPU; two runs on the same inputs give identical quality KPIs and
  per-question classes (100 %).
- **SC-003**: The board measurement takes one command and at most 30 minutes; its T1 and T2 for
  `chemie-nodemcu` agree with the hand measurement of spec 005 (158 ms typed, 5.1 chars/s) within
  10 %, or the difference is explained in the measurements file.
- **SC-004**: Every one of the 15 KPIs of the roadmap (F1–F6, T1–T3, R1–R4, S1–S3) has a written
  definition, a test set or measuring procedure and a noise threshold before the baseline is
  committed; in the baseline report each KPI shows a value, "not applicable" or a stated reason why
  it was not measured.
- **SC-005**: The general-knowledge suite is measured with the same benchmark logic as the
  chemistry suite, without any code change (topic-independence check).
- **SC-006**: All test sets are pinned; changing one byte of any test set makes the benchmark and
  the CI fail with a message that names the file.
- **SC-007**: On a deliberately changed answer of the repo model, the CI fails and the report lists
  the changed question within its per-question change list.
- **SC-008**: For a sample of 50 scored answers, a person's own classification (correct, wrong
  fact, refused, no usable answer) agrees with the benchmark's classification in at least 49 cases.

## Assumptions

- Spec 007 is written and built before spec 006 is finished (roadmap order); spec 006's step 2
  then measures `chemie-hybrid` with this benchmark. The short-test set `kurzarbeit.tsv` is taken
  over in its state at the time of pinning; if spec 006's review still changes it, that is a new
  test-set version (FR-004).
- The baseline is measured with one seed, because `chemie-nodemcu` exists only once; later steps
  measure three seeds where training cost allows (roadmap rule 5). For KPIs without seed spread the
  fixed noise threshold decides alone.
- Default noise thresholds, to be confirmed in the plan and fixed in the suite before the first
  comparison: rates F1, F3, F4, F5 ± 3 percentage points (about one binomial standard error at
  200 questions), F2 ± 0.5 points, F6 ± 1 % of its value, T1–T3 ± 5 %, R1–R4 exact (any change
  counts), S1 ± 0.02 bits per character, S2 one distance step, S3 ± 2 answers.
- The board mode reuses the serial protocol and console commands that `devlib.py`,
  `device_smoke.py` and `device_parity.py` already use (`/info`, `/stats`, timing lines); if R1 or
  the knowledge-image identity is not yet reported by the firmware, adding that to the console
  output is part of this spec, within the budgets of spec 006.
- One NodeMCU is enough; a second board is optional (FR-022 merges two single-board runs). Access
  to `chemie-nodemcu` on a board (roadmap "Offene Punkte") is arranged by the user once for the
  baseline measurement.
- The S1 text and the new question sets are written for this project or come from sources with a
  compatible license, recorded in `DATA_LICENSES.md` (constitution IV).
- The canonical question per property (F6) and the value classes come from the suite; for the
  chemistry suite they follow the question types of spec 006.
- S3 is rated by the developer; no second rater is required.
- Out of scope: training new models, changing model or answer quality, performance work, and
  automated flashing of boards.
