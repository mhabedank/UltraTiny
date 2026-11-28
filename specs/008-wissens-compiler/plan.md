# Implementation Plan: Knowledge Compiler (Topic-Independent)

**Branch**: `claude/adoring-cannon-2dpdv4` | **Date**: 2026-11-28 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/008-wissens-compiler/spec.md`

## Summary

A topic becomes data: `topics/<id>/` holds a schema (classes, relations, value types, rules,
views with answer templates, topic texts, competency questions), object and fact files (triples
with a source) and an optional preparation step. A new compiler (`ultratiny.knowledge`) validates
the topic, computes reverse directions and three kinds of simple rules at build time, and writes a
**knowledge image** (UTKI v1). UTKI replaces the 006 fact table (UTFT v1) in the same 64 KB flash
area.

The structure, not the strings, is where today's table spends its bytes: 1,597 records × 8 B and
323 objects × 12 B are 57 % of the 29,100 B; the strings are already stored once (research R1).
UTKI therefore uses 16-bit offsets, objects grouped by class, relation-local value IDs, one-byte
columns for single values and posting lists for lists and reverse questions (R5). Estimate: about
21.6 KB for about 3,070 answerable facts (≈ 7 B per fact; 006: 12.23 B), without string compression.

The model interface stays: the 006 function output (type letter + key) maps to views through legacy
letters, and a frozen oracle of every 006 answer proves byte-identical answers before the old code
is removed (R10). A `/wissen` console command queries any view without a model, which is how the
second topic (chess pieces) and the new reverse views are tested on the board (R12). No model is
trained in this step (FR-019).

## Technical Context

**Language/Version**:
- Runtime: C11, no dependencies (`runtime/`)
- Firmware: Arduino core 3.1.2 for the ESP8266, C++ glue only (`firmware-nodemcu/`)
- Compiler, reference and tools: Python 3.11+ (`training/`, `tools/`, `topics/*/prepare.py`)

**Primary Dependencies**:
- Python standard library only for the compiler (`tomllib`, `csv`, `struct`, `zlib`, `hashlib`)
- The existing Spark LLM client for the optional proposal step (`training/tools/shorten_llm.py`)
- PlatformIO `espressif8266@4.2.1`, esptool (unchanged)

**Storage**:
- Topic sources as TOML and TSV under `topics/<id>/`
- Images `models/<id>.utki` (committed, rebuilt and compared in CI) with `models/<id>.build.json`
- On the board: flash `0x100000`–`0x10FFFF`, read through `ESP.flashRead` (unchanged from 006)

**Testing**:
- pytest: topic loading and validation, rules, image writer and reader, compat check, determinism,
  proposals (`training/tests/test_knowledge_*.py`, fixture topics under `training/tests/fixtures/topics/`)
- CTest: `test_knowledge.c` (status, lookup, lists, alignment-checked build), console tests with
  `<fn>`, `--kb-cases` parity of C against Python for both topics
- Board: `tools/device_knowledge.py` (cases + timing), `tools/device_parity.py` (006 golden),
  007 board run

**Target Platform**: NodeMCU v2 (ESP8266, 160 MHz, no FPU, 4 MB flash); host Linux for tests.

**Project Type**: Embedded ML project with three parts (training/tools in Python, portable C runtime,
board firmware); this feature adds a build-time compiler and replaces the on-device fact reader.

**Performance Goals**:
- Lookup and rendering ≤ 50 ms per query on the board (estimate < 3 ms, R15)
- Build of the chemistry topic < 1 min on CPU (SC-008)
- First character ≤ 2 s and ≥ 5 chars/s unchanged (the prefix is still printed when the letter arrives)

**Constraints**:
- Image ≤ 58,982 B (64 KB area − 10 %); ≤ 8.56 B per answerable fact (SC-003)
- Knowledge engine ≤ 1 KB static RAM, no heap, no float; firmware ≤ 360,448 B
- Byte-identical answers C ↔ Python; byte-identical 006 answers except reviewed changes
- No topic name, class, relation or text in compiler, format, engine or firmware (FR-001, FR-013)

**Scale/Scope**:
- Chemistry: 4 classes, 323 objects, ≈ 25 relations, ≈ 45 views (26 with legacy letters),
  ≈ 2,400 explicit and generated facts, ≈ 3,070 answerable facts
- Chess: 2 classes, 8 objects, 6 relations, ≈ 30–36 facts
- About 1,200 lines of new Python, about 600 lines of C replacing `facts.c` (≈ 320 lines)

No open NEEDS CLARIFICATION: research R1–R15 decides every open point.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Check | Status |
|-----------|-------|--------|
| **I. Hard on-device budget** | Board NodeMCU. Image ≤ 58,982 B in the 006 fact area (build, `budget_report.py`, `make nodemcu-flash-facts`); engine ≤ 1 KB static RAM; firmware ≤ 360,448 B; model area and arena unchanged; time per query ≤ 50 ms, first character and chars/s unchanged. Board measurement in quickstart §7. | ✅ |
| **II. Quantized, allocation-free inference** | Model math unchanged. The engine allocates nothing, uses integers only and reads the image in place through the aligned flash callback (the image lies outside the mapped window, as decided in 006; it holds no weights). | ✅ |
| **III. Reference parity** | Python reader `knowledge/image.py` mirrors `knowledge.c`; golden cases per topic (`ut knowledge cases`) run on host (`--kb-cases`, alignment-checked build) and board (`device_knowledge.py`); 006 golden `printed` cases stay valid through the compat check. | ✅ |
| **IV. Reproducible training & export** | The build is scripted and deterministic (CI rebuilds and compares committed images); the image starts with magic, version, topic, schema version and CRCs; sources carry licence prefixes from `DATA_LICENSES.md`; `prepare.py --check` in CI; model meta gains `topic`. | ✅ |
| **V. Simplicity & portability** | Plain C, no new dependency; one code path (UTFT v1 is removed after the compat check); no string compression until a measurement needs it (R6); rules only at build time in Python (R8). | ✅ |

Quality gates: every PR still runs the host build, unit tests, parity, the budget report and the
NodeMCU firmware build; CI additionally builds both topics, checks compat, and runs the knowledge
parity cases.

**Post-design re-check (after Phase 1)**: the contracts keep all five principles. The format change
bumps the magic and version (new format UTKI v1) and updates exporter, loader, reference and
parity vectors in the same change (development workflow rule). No violations.

## Project Structure

### Documentation (this feature)

```text
specs/008-wissens-compiler/
├── spec.md              # feature specification
├── plan.md              # this file
├── research.md          # Phase 0: decisions R1–R15
├── data-model.md        # Phase 1: entities, legacy mapping, chess outline
├── quickstart.md        # Phase 1: validation scenarios
├── contracts/
│   ├── topic-format.md  # topic directory, schema.toml, TSV files, errors
│   ├── image-format.md  # UTKI v1 binary layout and validation
│   ├── query.md         # lookup, rendering, lists, console, /wissen, host, reference API
│   └── cli.md           # ut knowledge …, changed tools and make targets
├── checklists/requirements.md
└── tasks.md             # Phase 2 (/speckit-tasks, not created here)
```

### Source Code (repository root)

```text
topics/
├── chemie/
│   ├── topic.toml, schema.toml
│   ├── objects.tsv                     # written by prepare.py
│   ├── facts/generated/*.tsv           # written by prepare.py (from ultratiny.factgen)
│   ├── facts/*.tsv                     # hand-curated additions (gruppe_nr extras, accepted proposals)
│   ├── prepare.py
│   └── compat/utft1_answers.tsv, changes.tsv
└── schach/
    ├── topic.toml, schema.toml, objects.tsv
    └── facts/figuren.tsv

training/src/ultratiny/knowledge/       # new: the compiler and the reference reader
├── __init__.py
├── topic.py                            # load + validate topic, schema, objects, facts
├── rules.py                            # reverse directions, class/chain/table rules, fixpoint
├── compile.py                          # UTKI writer, build.json, size report
├── image.py                            # UTKI reader = Python reference (lookup, render, answer_bytes)
├── compat.py                           # oracle export (once, from UTFT v1) and compat check
└── propose.py                          # optional LLM proposals and accept
training/src/ultratiny/cli.py           # `ut knowledge …`; `ut facts` removed; pipeline uses topics
training/src/ultratiny/{hybrid,golden,export}.py, bench/{subject,pc}.py   # switch to knowledge.image
training/src/ultratiny/facttable.py     # removed after the compat oracle is frozen
training/tests/test_knowledge_{topic,rules,image,compat,propose}.py
training/tests/fixtures/topics/{mini,bad_*}/
training/tools/make_runtime_fixtures.py # builds runtime fixtures from topics

runtime/include/utiny_knowledge.h       # replaces utiny_facts.h
runtime/src/knowledge.c                 # replaces facts.c
runtime/src/console.c, include/utiny_console.h   # fn path on the new API, /wissen, /info line
runtime/host/utiny_host.c               # --facts (UTKI), --kb-cases, --query
runtime/tests/test_knowledge.c, test_console_logic.c, fixtures/kb_*.utki, *_cases.tsv
runtime/CMakeLists.txt                  # tests and parity for both topics, checked variants

firmware-nodemcu/src/main.cpp           # ut_kb_open, boot line, topic check

tools/budget_report.py, bench.py, bench_export_facts.py, bench_demo.py, devlib.py, device_knowledge.py (new)
bench/board.py, bench/demo/008.tsv
models/chemie.utki, models/schach.utki (+ .build.json, _cases.tsv)
Makefile                                # knowledge target, nodemcu-flash-facts on UTKI
.github/workflows/ci.yml                # build topics, compat, prepare --check, kb parity
DATA_LICENSES.md                        # note: llm: not allowed as a fact source
specs/ROADMAP.md                        # step 3 status, KPIs F7/R5, second topic decided
```

**Structure Decision**: the existing three-part layout stays. The compiler is a sub-package of the
training package because it shares the alphabet, the licence prefixes and the config loader; the
runtime gets one replacement module; topic data lives in a new top-level `topics/` so it is visibly
separate from code (FR-001) and from the 003–006 training data.

## Order of work

1. **Freeze the oracle** (R10): export `utft1_answers.tsv` and the 006 image-only bench result while
   UTFT v1 still exists.
2. **Compiler and reference** (`knowledge/topic.py`, `rules.py`, `compile.py`, `image.py`) with the
   fixture topics; chemistry topic (`prepare.py`, `schema.toml` with the 26 legacy views).
3. **Compat green**, then the new chemistry relations, rules and reverse views (R9); measure size,
   F7, R5.
4. **C engine and console** (`knowledge.c`, `/wissen`, `/info`), host parity, fixtures; remove UTFT v1
   (C and Python) and switch pipeline, golden, eval and bench to UTKI.
5. **Chess topic** in its own change set (SC-004).
6. **Benchmark, budget, CI**, then board runs 🔌 (cases + timing, 006 golden, wrong topic, erased
   area), demo next to `chemie-nodemcu`, `measurements.md`, roadmap update.
7. **Optional**: LLM proposals (US4).

## Complexity Tracking

No constitution violation. One roadmap exception is recorded:

| Exception | Why Needed | Simpler Alternative Rejected Because |
|-----------|------------|-------------------------------------|
| Chemistry calculations stay in `ultratiny.factgen` (training package) and are reached by `topics/chemie/prepare.py` | `factgen` is the data generator for training `chemie-hybrid` (006 T044) until spec 009 derives training data from the schema; the compiler itself contains no chemistry (FR-008) | Rewriting the chemistry rules inside the topic duplicates them (two sources of truth); deleting `factgen` breaks the 006 training pipeline |
