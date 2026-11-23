# Research: Benchmark and KPI Report

Decisions for [plan.md](plan.md). Each entry: decision, rationale, alternatives. Measured values are
from the development container (4 cores, x86-64), 2026-11-23.

## R1 – Where the code lives and how it is called

**Decision**: The logic is a package `training/src/ultratiny/bench/` (suite loading, scoring, PC run,
board run, report, demo). Four thin entry points in `tools/`, run from `training/` like the other
tools (`uv run python ../tools/<x>.py`):

| Command | Spec |
|---------|------|
| `tools/bench.py pc` | US1, FR-011 |
| `tools/bench.py board` | US4, FR-013/014 |
| `tools/bench_report.py` | US2, FR-016–021 |
| `tools/bench_demo.py` | US5, FR-022 |

Suites, test sets and results live in a new top-level `bench/` directory (`bench/suites/<topic>/`,
`bench/results/`, `bench/demo/`).

**Rationale**: The roadmap names `tools/bench.py` and `tools/bench_report.py`. Keeping the logic in
the package lets pytest cover it, reuses `Reference`, `Alphabet`, `facttable` and `devlib` without
copies, and keeps the tools as argument parsers. `bench/` at the top level keeps benchmark data apart
from training data (`training/data/`), which helps FR-005 (nothing in `bench/` is ever trained).

**Alternatives**: A `ut bench` subcommand in `cli.py` (rejected: board tools already live in
`tools/`, and the roadmap names the scripts); test sets under `training/data/eval/` (rejected: mixes
training and benchmark data; only `kurzarbeit.tsv` stays there, see R3).

## R2 – One measuring interface for every model kind

**Decision**: The benchmark talks to a model only through a small adapter ("subject") with two
operations:

- `answer(question) -> visible text`: what the board would print, including fact-table rendering;
- `bits(text, positions) -> bits per scored character`: for S1 and S2.

The first adapter wraps today's `Reference` (transformer, UTNY v1/v2). For v2 models with a fact
table it renders the answer with `facttable.answer_bytes()`, the same code the evaluation of spec 006
uses, so the printed text equals the board's. Generation is greedy, `max_len = ctx_len − 3` as in
`hybrid.evaluate_sets`. A question that does not fit the context is recorded as `too_long` and scored
"no usable answer".

**Rationale**: FR-007 asks that free-text and knowledge-image models are scored the same way, and
specs 011–013 will add new cores. A new core then adds one adapter, not a new benchmark.

**Alternatives**: Scoring function outputs (`SNa`) directly as spec 006 does (rejected: only works for
hybrid models); calling `utiny-host` for every answer (rejected: slower and the Python reference is
already bit-exact by constitution III; the board run checks parity anyway).

## R3 – Suite format and the pinned files

**Decision**: A suite is a directory with a `suite.toml` and TSV files:

```text
bench/suites/chemie/
  suite.toml          # version, value classes, refusal forms, thresholds, board sample, pins
  facts.tsv           # reference facts: object, property, value, value class, canonical question
  sets/unseen.tsv     # F1 (and F2, F4)
  sets/unknown.tsv    # F3
  sets/offtopic.tsv   # F3
  sets/s3.tsv         # S3 prompts
  text/s1.txt         # S1 text, two marked halves
  text/s2.tsv         # S2 probes (generated, see R7)
```

`kurzarbeit.tsv` stays at `training/data/eval/kurzarbeit.tsv` (spec 006 and its datagen pin point
there); `suite.toml` refers to it by path and pins the same hash (`cd2a36bf…`). Every file is pinned by
SHA-256 in `suite.toml`; `bench.py` checks all pins before it loads a model. A file's pin together with
the suite version forms the test-set version written into results (FR-004).

The question sets use the readable answer format introduced for `kurzarbeit.tsv`
(`element_symbol: Na`), with property names from `facts.tsv`.

**Rationale**: Data only (FR-001); a second topic needs no code (FR-002, SC-005); TSV/TOML is what
the repository already uses. One manifest with pins makes SC-006 a single check.

**Alternatives**: JSON test sets (rejected: harder to review by hand); copying `kurzarbeit.tsv` into
the suite (rejected: two copies could drift although the pin would catch it).

## R4 – Reference facts per suite

**Decision**: `facts.tsv` holds every fact a suite asks about: `object`, `object_name`, `property`,
`value`, `value_class`. Canonical questions per property sit in `suite.toml`
(`[properties.<name>] canonical = "Welches Symbol hat {name}?"`).

- **chemie**: exported once from the spec 006 fact set (`factgen.build`, 1,597 records today) by a
  small export script, then committed and pinned. The benchmark never imports factgen at run time.
- **allgemein**: written from `training/data/facts/starter.tsv` (97 capitals, 47 element symbols;
  the 20 self-description rows become S3 prompts, not facts).

**Rationale**: The benchmark must keep working when factgen changes (later specs rewrite it: 008). A
pinned export freezes the meaning of "correct" for comparisons.

**Alternatives**: Reading the fact table `.utft` at run time (rejected: models without a fact table,
like `chemie-nodemcu`, still need expected values; also couples the benchmark to one binary format).

## R5 – Scoring a visible answer

**Decision**: Each value class in `suite.toml` has a matcher; the set of known values of a class is
taken from `facts.tsv` (all symbols, all element names, all formulas …) plus a number pattern for
numeric classes.

1. Normalise the answer (Unicode NFC, collapse spaces; keep case).
2. **refused** if the answer starts with or equals one of the suite's refusal forms
   (`Das weiß ich leider nicht.`, `Frag mich etwas zur Chemie!`, the not-applicable form
   `…: dazu habe ich keine Angabe.`), checked first.
3. Extract all known values of the classes the question's accepted answers use (whole-token match,
   case-sensitive for symbols and formulas; numbers with `,` or `.` and the class's rounding).
4. **correct** if at least one accepted value is present and no other value of those classes;
   **wrong fact** if any other value of those classes is present; otherwise **no usable answer**.

Names in the question itself are ignored when they appear in the answer as the subject (the answer
"Das Symbol von Natrium ist Na." contains the name "Natrium", which is the question's object, not a
wrong name). Multi questions accept any listed answer, as in spec 006.

Explain items (F5) keep spec 006's rule (all keywords, ≤ 60 characters, not refused). Unknown/
off-topic items are correct when refused; an answer that states a known value of any class is a
wrong fact.

**Rationale**: Data-driven matching keeps the logic topic-free and makes "wrong fact" concrete:
another known value of the same kind. SC-008 (49/50 agreement with a person) is tested on a hand-
labelled sample in pytest.

**Alternatives**: Edit distance to a template sentence (spec 003/005 `is_correct`; rejected: depends on
the answer template, so a hybrid model with different wording would be scored differently); an LLM
judge (rejected: not reproducible, not offline).

## R6 – S1 bits per character

**Decision**: Sliding windows over the S1 text with window = `ctx_len` and stride = `ctx_len / 2`; in
each window only the second half is scored (the first window scores everything). Bits =
−log2 p(next char) from the reference logits (float64 softmax over the int-exact logits). Characters
outside the model's alphabet are removed before scoring and counted; the result reports coverage.
S1 is reported for the topic half, the general half and both.

Cost at 2.1 ms per reference step (measured, `nodemcu.utny`): 20,000 characters × 2 steps ≈ 85 s.

**Rationale**: Every scored character has at least `ctx_len/2` characters of history, the standard
way to evaluate a fixed-window model; scoring every position with full history would cost ~70 min.

**Alternatives**: Non-overlapping windows (rejected: the first characters of each window have almost
no history and inflate bits); stride 1 (too slow).

**Text**: Each suite has its own topic half and shares the general half:
- **Topic half, chemie**: 10,000 characters of chemistry text for grades 7–10, written for this
  project and reviewed by the user. It covers curriculum topics but is not copied from
  `chemie_rlp_*.tsv`.
- **Topic half, allgemein**: 10,000 characters of geography and general-knowledge text (countries,
  capitals, currencies), written the same way.
- **General half, both suites**: 10,000 characters of public-domain German prose (Project Gutenberg,
  author dead > 70 years, e.g. Kafka, *Die Verwandlung*, 1915).

How the project-written text is sourced and recorded follows the rule for LLM output in `DATA_LICENSES.md`: proposed by an allowed local model on the Spark (T017, T018), reviewed by the user, recorded in T050 (decided 2026-11-23). A check verifies that no 40-character span of
the S1 text occurs in the training data files. `DATA_LICENSES.md` gets a `public-domain` row and a
note that `bench/` data is evaluation-only.

## R7 – S2 recall probes

**Decision**: A deterministic generator (`tools/bench_s2.py`, seed fixed) writes `text/s2.tsv`:
- **Target word**: an invented, pronounceable word of 6–8 letters from the model alphabet
  (e.g. `Brolmik`). Since it is invented, the model cannot know it, so a low cost on its second
  appearance can only come from copying.
- **Filler**: taken from the general half of the S1 text. A probe's text is: filler, then
  "… hieß {word} …", then filler of length d, then "… wieder {word}".
- **Control text**: the same text, except the first mention is replaced by a different invented
  word of the same length.
- **Size**: distances d ∈ {16, 32, 64, 96, 128, 192, 256, 416}, 13 probes each, 104 probes in total.
  These distances are fixed. A model that recalls at 416 gets S2 "≥ 416"; larger distances for later
  cores (spec 012) are a new suite version, so S2 then reads "not comparable" against older results.

Scoring: bits of the second occurrence, using the adapter's full-history rule (for the transformer:
the window ends at the target, at most `ctx_len − 1` characters of history). A probe is recalled when
these bits ≤ 0.5 × the bits at the same place in the control text. S2 = largest d with ≥ 80 % recalled
(clarified 2026-11-23).

Cost: 104 probes × 2 texts × ~110 steps ≈ 23,000 steps ≈ 50 s.

**Rationale**: Works for any language model without training it on recall questions. A transformer
with context 104 must show recall up to about 96 and none at 128 and above, which is a built-in sanity
check of the measurement.

**Alternatives**: Real rare words (rejected: the model may know them, so the control is not neutral).

## R8 – Board measurement over the existing console

**Decision**: No firmware change. The board mode uses `tools/devlib.Device` and the console
commands that already exist:

| Need | Source on the board |
|------|---------------------|
| identity | `/info`: parameters, file size, training git and date, fact table `data <sha4>` |
| T1 | `/info` "erstes Zeichen nach … ms" after each question; typed pass with 100 ms per character (as `device_smoke.py`), pasted pass all at once |
| T2 | `/trace json` (on for the whole run; printed after the answer, so it does not slow it): per-step `us`; T2 = (n − 1) / Σ step time of characters 2…n, median over the sample. `/info` chars/s (counted from Enter, so it includes the first-character wait) is kept as information only |
| T3 | same per-step data; T3 = characters / Σ step time over steps with `pos ≥ 0.9 × ctx_len`, on the T3 prompts |
| R1 | `/stats` JSON line `@ut {"type":"sys",…}`: `arena_need`, `arena_buf`, `heap_free`, `heap_min` |
| parity | answer text vs. the PC adapter's answer for the same question |

The arena is static (constitution II), so its peak equals `arena_need`. With `--port` the run starts
with an RTS reset (no flashing), so the first `/stats` gives the heap after boot; it is read again at
the end of the run (`heap_min` shows the low point). With `--exec` there is no reset.

- **Board sample** (`suite.toml`): 30 F1 questions, the whole short-test set (130), and 10 T3 prompts.
  T3 prompts are long questions with long answers.
- **Run time**: 170 questions at ~6 s each, plus 15 typed questions at ~5 s extra, gives about 20 min,
  inside the 30-minute limit (FR-014).
- **Faults**: a boot banner seen mid-run means a reset, and a timeout means a hang. The run records
  the event, waits for the prompt (resetting through RTS if needed) and goes on with the next question.

The same code runs against `utiny-host --console` (`devlib.ExecLink`). This lets CI test the board
mode without hardware.

**Rationale**: Spec assumption allowed console changes, but everything needed is already printed;
avoiding firmware changes keeps static RAM and the 006 budgets untouched.

**Alternatives**: New `/bench` console command (rejected: not needed; costs flash and RAM).

## R9 – Seeds, noise threshold and verdicts

**Decision**: Results are grouped by the `label` written at measurement time (e.g. `chemie-hybrid`).
Several results with the same label and suite version are seeds of one step. Per KPI:
- **Several seeds**: mean and sample standard deviation.
- **Verdict**: better or worse only if |Δ| > threshold (FR-018, values fixed in the clarification) and,
  when either side has ≥ 2 seeds, |Δ| > 2 × the larger spread. Otherwise the verdict is "unchanged".
- **Exact KPIs** (R1–R4, threshold "exact"): any difference counts.

Thresholds are stored in `suite.toml`, so a threshold change is a suite version change.

**Rationale**: Research 1 §8 and roadmap rule 5.

**Alternatives**: Bootstrap confidence intervals per question set (rejected for now: needs more
seeds than the Spark budget gives; the fixed threshold was set to about one binomial standard
error at 200 questions).

## R10 – Report output

**Decision**: One report model (Python dicts) rendered twice:
- **Markdown**: tables.
- **HTML**: a single self-contained file with inline CSS and inline SVG for two charts, the S2 recall
  curve and F1 per question type. No JavaScript and no external files.

The report holds:
- **Summary line**: also flags "budget broken" and "parity broken".
- **KPI table**: value, Δ, direction, threshold, verdict.
- **Budget section**: limits are imported from `tools/budget_report.py`, so there is one source of
  truth.
- **Changed answers**: every question whose class changed between the compared results.

Output is sorted and has no timestamps except one "generated" line, which is excluded when the
determinism test compares two reports.

**Rationale**: FR-016–FR-021; a single HTML file is easy to attach to a PR or publish.

**Alternatives**: A plotting library (rejected: new dependency for two small charts).

## R11 – CI

**Decision**: The `python` job gains one step after pytest:

```bash
uv run python ../tools/bench.py pc --suite ../bench/suites/allgemein \
  --model ../models/nodemcu.utny --check ../bench/results/nodemcu_allgemein_pc.json
```

`--check` measures and compares quality KPIs and per-question classes with the committed result.
Any difference, including an improvement, fails, and the output names the changed KPIs and questions
(clarified 2026-11-23).

Estimated time for the allgemein suite: ~150 facts for F6, ~200 questions, S1/S2. That is about
120,000 reference steps, ~4 min at 2.1 ms per step, inside 10 min (FR-024).

The `runtime-host` job gains a short board-mode check against `utiny-host --console` (5 questions,
parity only).

**Determinism**: The reference uses NumPy float32 with integer matmuls and is bit-exact with the C
runtime, which the parity tests show. NumPy is pinned by `uv.lock`, so results on the CI runner match
the container. If a NumPy update ever changes results, `--check` fails, which is the intended
behaviour.

## R12 – Baseline runs and keeping test sets out of training

**Decision**:
- **chemie-nodemcu, PC**: run on the DGX Spark, where the model is. Its `uv` environment can run
  `tools/bench.py pc` on CPU. The result JSON is committed.
- **chemie-nodemcu, board**: the user flashes `chemie-nodemcu` (005 flashing steps) and runs
  `tools/bench.py board` on their machine.
- **nodemcu**: both runs here and on the user's board.

All four results and `bench/results/baseline.md`/`.html` are committed.

**Keeping test sets out of training (FR-005)**:
- `ultratiny.bench.suite.all_questions()` lists every question of every suite.
- `datagen.py` (v1 pipeline) and `hybrid.py` (v2) drop matching training prompts after normalising
  them, as spec 006 already does for `kurzarbeit.tsv`, and report how many they dropped.
- For an existing model, `bench.py pc --train-data runs/<name>/data/train.txt` reports the overlap per
  set. Without that file it reports "unknown".

**Rationale**: The roadmap's open point "baseline access" is resolved by measuring where the model
is. Dropping test questions from future training is cheap and keeps later comparisons honest.

## R13 – Expected run time on the PC (SC-002)

| Part | Reference steps (chemie) |
|------|--------------------------|
| F1 (200 × ~80) | 16,000 |
| F3 (80 × ~70) | 5,600 |
| F5 (130 × ~80) | 10,400 |
| F6 (1,597 facts × ~60) | 96,000 |
| S1 | 40,000 |
| S2 | 23,000 |
| **Total** | **~191,000 ≈ 6.7 min** at 2.1 ms |

Within 15 min on one core. A `--jobs N` option spreads questions over processes when needed.
Results do not depend on the number of jobs, because each question starts from a fresh context.
