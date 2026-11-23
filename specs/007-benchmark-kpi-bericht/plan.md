# Implementation Plan: Benchmark and KPI Report

**Branch**: `claude/benchmark-kpi-bericht-rhojdq` | **Date**: 2026-11-23 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/007-benchmark-kpi-bericht/spec.md`

## Summary

One benchmark measures every roadmap step the same way:

- `tools/bench.py pc` asks frozen test sets through the bit-exact Python reference. It scores the
  **visible answer text** against pinned reference facts and writes one JSON result. The scoring
  classes are correct, wrong fact, refused and no usable answer.
- `tools/bench.py board` repeats a fixed sample on the NodeMCU over the existing serial console. It
  measures speed and RAM and checks that the board's answers match the PC's.
- `tools/bench_report.py` compares results. It applies fixed noise thresholds and seed spread, checks
  budgets and lists changed answers, as Markdown and as self-contained HTML.
- `tools/bench_demo.py` puts two models' answers side by side.

The benchmark data lives in topic **suites** (`bench/suites/chemie`, `bench/suites/allgemein`).
Each suite is data only and every file in it is pinned by SHA-256. The suite `allgemein` is the
topic-independence test and the CI check for `models/nodemcu.utny`.

The baseline `chemie-nodemcu` is measured once, on the Spark and on the board, and committed.
There are no firmware, runtime or model-format changes. Details: [research.md](research.md).

## Technical Context

**Language/Version**: Python 3.11+ (training package and tools), as in specs 005/006

**Primary Dependencies**:
- Existing only: NumPy (reference), pyserial (board, dev dependency), stdlib `tomllib`, `json`, `html`
- Reused modules: `ultratiny.reference`, `ultratiny.alphabet`, `ultratiny.facttable`, `tools/devlib.py`,
  `tools/budget_report.py` (budget limits)
- No new packages

**Storage**: Files only:
- `bench/suites/<topic>/` (TOML + TSV + text, pinned)
- `bench/results/*.json` (results), `*.s3.tsv` (ratings), `baseline.md`/`.html`
- `bench/demo/*.tsv`, `*.md`

**Testing**:
- **pytest** (`training/tests/test_bench_*.py`):
  - scoring on a hand-labelled sample (SC-008)
  - pin check, verdict rules, report determinism
  - S1/S2 on a tiny model
  - board mode against a fake link
- **CI**:
  - `python` job: `bench.py pc --check` on the repo model
  - `runtime-host` job: board mode against `utiny-host --console` (parity sample)

**Target Platform**:
- PC: Linux container, DGX Spark (CPU path), CI runner
- Board: NodeMCU v2 (ESP8266) with the firmware of spec 005/006, read-only access over serial

**Project Type**: Tooling for an embedded ML project: measurement CLI, report generator and data sets.

**Performance Goals**:
- PC run, chemistry suite: ≤ 15 min on 4 cores (estimate 6.7 min single-process, R13)
- CI check, allgemein: ≤ 10 min (estimate ~4 min)
- Board run: ≤ 30 min (estimate ~20 min, R8)

**Constraints**:
- Quality KPIs bit-reproducible across machines (NumPy pinned by `uv.lock`)
- The board is never flashed by the tools
- Nothing in `bench/` may reach training data (FR-005)
- Topic-free code (roadmap rule 6)

**Scale/Scope**:
- 2 suites; chemie ≈ 200 + 40 + 40 + 130 + 20 questions, 1,597 reference facts, 20,000-character S1
  text, 104 S2 probes
- 4 committed baseline results

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Check | Status |
|-----------|-------|--------|
| I. Hard on-device budget | No firmware, model or runtime change; static RAM and flash unchanged. The report adds a budget section (limits from `tools/budget_report.py`, plus the roadmap arena gate 35 KB) that marks breaches (FR-019) | ✅ |
| II. Quantized, allocation-free inference | Inference path untouched; the board mode only reads console output | ✅ |
| III. Reference parity | Quality is measured through the bit-exact Python reference; every board answer is compared with it (FR-010, FR-013); CI also runs the board mode against the C host console | ✅ strengthens |
| IV. Reproducible training & export | Test sets and reference facts pinned by SHA-256; results record model hash, test-set versions, commit and seed; new data sources recorded in `DATA_LICENSES.md` (`public-domain` for the S1 general half, `own` for the rest); datagen drops benchmark questions from training | ✅ |
| V. Simplicity & portability | Python only, no new dependencies; one adapter interface for future cores instead of per-model code paths | ✅ |
| Quality gate "fixed evaluation set and metric" | This spec is that gate for all later specs | ✅ |

Post-design re-check (after Phase 1): unchanged, all ✅. No entries in Complexity Tracking.

## Project Structure

### Documentation (this feature)

```text
specs/007-benchmark-kpi-bericht/
├── plan.md              # This file
├── research.md          # Phase 0: R1–R13
├── data-model.md        # Phase 1: suite, test set, result, report entities
├── quickstart.md        # Phase 1: validation scenarios
├── contracts/
│   ├── cli.md           # commands, options, exit codes
│   ├── suite-format.md  # suite.toml, facts.tsv, sets, S1/S2 files
│   └── result-format.md # result JSON, KPI definitions, report sections
├── checklists/requirements.md
└── tasks.md             # Phase 2 (/speckit-tasks)
```

### Source Code (repository root)

```text
bench/                                  # NEW – benchmark data, never used for training
├── README.md                           # what is here, how to run, how to re-pin
├── suites/
│   ├── chemie/
│   │   ├── suite.toml                  # pins, value classes, properties, thresholds, board sample
│   │   ├── facts.tsv                   # exported from spec 006 fact set (R4)
│   │   ├── sets/{unseen,unknown,offtopic,s3}.tsv
│   │   └── text/{s1.txt,s2.tsv}
│   └── allgemein/                      # same layout; facts from starter.tsv
├── results/                            # committed result JSON, rating sheets, baseline report
└── demo/                               # demo scripts per roadmap step and side-by-side output

training/src/ultratiny/bench/           # NEW package
├── __init__.py
├── suite.py        # load + pin check, all_questions() for datagen exclusion
├── scoring.py      # value matching and the four classes (R5), KPI aggregation
├── subject.py      # adapter interface + transformer/Reference adapter (R2)
├── lm.py           # S1 sliding-window bits, S2 recall (R6, R7)
├── pc.py           # PC run, overlap, --check comparison
├── board.py        # board run over devlib.Device (R8)
├── report.py       # report model, verdicts (R9), Markdown and HTML rendering (R10)
└── demo.py         # demo runner and merge

training/src/ultratiny/datagen.py       # CHANGED – drop benchmark questions (FR-005)
training/src/ultratiny/hybrid.py        # CHANGED – same, beside the kurzarbeit drop

tools/
├── bench.py                            # NEW – `pc` and `board` subcommands
├── bench_report.py                     # NEW
├── bench_demo.py                       # NEW
├── bench_s2.py                         # NEW – S2 probe generator
└── bench_export_facts.py               # NEW – reference facts export

training/tests/
├── test_bench_suite.py                 # pins, loading, minimum sizes
├── test_bench_scoring.py               # hand-labelled sample (SC-008), edge cases
├── test_bench_lm.py                    # S1/S2 on tiny_v2 fixture
├── test_bench_report.py                # verdicts, not comparable, determinism, budget marks
└── test_bench_board.py                 # board mode with a fake link (reset, timeout, parity)

.github/workflows/ci.yml                # CHANGED – bench --check (python), board mode vs host (runtime-host)
DATA_LICENSES.md                        # CHANGED – public-domain row, bench/ note
```

**Structure Decision**:
- **Logic**: the training package, so it is tested by pytest and reuses the reference.
- **Entry points**: `tools/`, as the roadmap names them.
- **Data**: a new top-level `bench/`, kept apart from training data.

`kurzarbeit.tsv` stays where spec 006 pinned it. The chemie suite refers to it by path and pins the
same hash.

## Implementation Phases (for /speckit-tasks)

1. **Suite skeleton and scoring (P1, US1)**:
   - `suite.py` and `scoring.py`
   - the `allgemein` suite: facts from `starter.tsv`, unseen ≥ 60, unknown, offtopic, s3
   - the hand-labelled scoring sample
2. **Language KPIs**: `lm.py`, `bench_s2.py`, the S1 texts (own chemistry text, public-domain general
   text), overlap check against training files.
3. **PC run and check**: `subject.py`, `pc.py`, `tools/bench.py pc`, `--check`, the CI step.
   Commit the `nodemcu` result.
4. **Report (US2)**: `report.py`, `tools/bench_report.py`, budget section, HTML.
5. **Chemistry suite**: `bench_export_facts.py`, then the sets:
   - `facts.tsv`
   - unseen ≥ 200 over all properties
   - unknown 40, offtopic 40
   - s3 20 prompts
   - T3 prompts

   Test questions are proposed by an LLM and reviewed by the user (👤, FR-006).
6. **Board mode (US4)**: `board.py`, `tools/bench.py board`, the host-console CI step, a board run
   with `nodemcu` (🔌).
7. **Baseline (US3)**: run `chemie-nodemcu` on the Spark (🖥️) and on the board (🔌), commit
   `baseline.md`/`.html`.
8. **Demo runner (US5)** and the demo script for step 007.
9. **Training exclusion (FR-005)** in `datagen.py`/`hybrid.py`, `DATA_LICENSES.md`, `bench/README.md`,
   measurements file.

## Risks

| Risk | Mitigation |
|------|------------|
| Value matching misclassifies free-text answers (e.g. a wrong element named in a sentence) | Subject-name rule (R5), hand-labelled sample with ≥ 49/50 agreement in pytest (SC-008); every class is visible per question in the report |
| PC run too slow for CI | allgemein suite small; `--jobs`; measured in phase 3 before the CI step is enabled |
| NumPy update changes floats | `uv.lock` pins NumPy; `--check` fails loudly, which is the desired signal |
| Board answers differ in whitespace/line endings | Compare after one fixed normalisation (CRLF → LF, trailing spaces removed), defined in `board.py` and tested |
| `chemie-nodemcu` not reachable for the board run | Board KPIs stay "not measured" in the baseline with the reason; PC baseline is enough for later PC comparisons |

## Complexity Tracking

No constitution violations.
