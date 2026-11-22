# Implementation Plan: Hybrid Chemistry Teacher on the NodeMCU

**Branch**: `claude/keen-feynman-z2sszl` | **Date**: 2026-11-22 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/006-hybrid-chemielehrer/spec.md`

## Summary

For factual questions the NodeMCU model stops writing facts. Instead it emits a **function output**:
`<fn>` + one type character + an object key, e.g. `<fn>OCu` for "Welche Ordnungszahl hat Kupfer?".
The firmware looks the key up in a verified **fact table** (UTFT blob in flash at 0x100000, outside the
mapped megabyte) and prints a short German template answer.

For reverse questions, the model only copies the value from the question and the firmware resolves it.
Examples: "Was ist N?" → `<fn>sN`, and "Welches Element hat die Ordnungszahl 29?" → `<fn>o29`.

Greetings, refusals, "I don't know" and ≤ 60-character curriculum explanations are still written by the model.

Training data is rebuilt around:
- computed, verified facts (26 question types, both directions)
- ≥ 12 question forms per type, grouped into families
- held-back combinations and families, plus a frozen short-test set of ≥ 120 questions

The model size, arena and board stay as in feature 005. Details: [research.md](research.md).

## Technical Context

**Language/Version**:
- Runtime: C11 (plain, no deps)
- Firmware: Arduino core 3.1.2 (C++ glue only)
- Training: Python 3.11+

**Primary Dependencies**:
- PyTorch and NumPy (training)
- PlatformIO `espressif8266@4.2.1` (firmware)
- esptool (flashing)
- the existing Spark LLM pipeline (`training/tools/augment_llm.py`), for phrasings and shortening only

**Storage**:
- model `.utny` (v2) in the mapped flash area 0x58000
- fact table `.utft` (v1) in flash 0x100000–0x10FFFF, read through the SDK flash-read call
- training data as TSV/TOML in `training/data/`

**Testing**:
- pytest (`training/tests`)
- CTest (`runtime/tests`, including the alignment-checked build)
- golden parity (host)
- `tools/device_parity.py` and the smoke and soak tools (board)

**Target Platform**:
- NodeMCU v2 (ESP8266, 160 MHz, no FPU, 4 MB flash)
- host Linux/macOS for tests
- DGX Spark (CUDA) or CPU for training

**Project Type**: Embedded ML. It has three parts: the training pipeline, the portable C runtime and the board firmware.

**Performance Goals**:
- first visible character ≤ 2 s; every template starts with a fixed prefix, so fact answers show their first character after the type character (~0.4 s, estimate; measured per type in T046) and text answers after ~0.16 s as today
- ≥ 5 chars/s for model-written text
- a fact answer takes 4–9 forward passes instead of 30–60

**Constraints**:
- model ≤ 619 KB (688 KB area − 10 %)
- arena ≤ 36 KB buffer (40 KB budget)
- fact table ≤ 58 KB (64 KB area − 10 %)
- static DRAM growth ≤ 1 KB (free heap 4,960 B at boot)
- no heap allocation at runtime and no float in the lookup
- bit-exact parity between Python and C, including the rendered answer

**Scale/Scope**:
- 118 elements, ~180 compounds, ~30 reaction equations, ~20 test reactions, ~15 acids/bases
- ~2,500 fact records
- ~460 short explanations
- ~40–60 k training lines
- ≥ 120 short-test questions

No open NEEDS CLARIFICATION: all unknowns are resolved in research.md (R1–R13).

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Check | Status |
|-----------|-------|--------|
| **I. Hard on-device budget** | Board and budgets come from constitution v2.0.0 and 005: flash, RAM, time per token, headroom. New budget line: fact table ≤ 64 KB area with ≥ 10 % headroom, outside the 1 MB mapped window, so the firmware + model ≤ 1 MB rule is unchanged. The budget report (`tools/budget_report.py`) gets a `facts` entry. Board measurement before release (T-tasks: speed, heap, parity). | ✅ |
| **II. Quantized, allocation-free inference** | The inference path is unchanged: int8 weights, static arena, in-place reads. The lookup uses static buffers (≈ 150 B), and its integer and string code has no float. Weights stay memory-mapped. The table is not weights, so reading it with flash-read is consistent with "weights read in place". | ✅ |
| **III. Reference parity** | Python `facttable.py` and C `facts.c` render the same bytes. The golden file holds the rendered text and the table hash. Host tests run in the normal and the alignment-checked build. `tools/device_parity.py` compares rendered text on the board before release. | ✅ |
| **IV. Reproducible training & export** | `ut pipeline` builds table, data, model, eval, golden and budget in one command (CPU or Spark). Seeds, data hash, table hash and held-back sets are recorded. The UTNY version goes to 2 (the alphabet gains `<fn>`); UTFT v1 starts with magic, version and CRC. New curated files get `source` columns, and `DATA_LICENSES.md` is updated. LLM output (paraphrases, shortened explanations) is committed and reviewed, never generated at training time. | ✅ |
| **V. Simplicity & portability** | One new C module (`facts.c`, ~250 lines, C stdlib only) and one platform read callback. No file system, no new tokenizer, and the same architecture. The added complexity (a second blob format, a special token) is the user's hybrid decision; see Complexity Tracking. | ✅ (justified) |

**Post-design re-check (after Phase 1)**: the data model and contracts keep every rule above:
- UTFT is aligned for word reads
- lookup buffers are static
- templates are stored as finished strings
- the budget report covers the new area

No new violations.

## Project Structure

### Documentation (this feature)

```text
specs/006-hybrid-chemielehrer/
├── spec.md
├── plan.md              # this file
├── research.md          # Phase 0: R1–R13
├── data-model.md        # Phase 1: entities, validation, states
├── quickstart.md        # Phase 1: validation guide
├── contracts/
│   ├── function-output.md   # model output grammar, UTNY v2, console behaviour
│   ├── fact-table-format.md # UTFT v1 binary layout, lookup rules, flash placement
│   └── eval-sets.md         # held-back sets, short-test file, evaluation report
├── checklists/requirements.md
└── tasks.md             # Phase 2 (/speckit-tasks)
```

### Source Code (repository root)

```text
runtime/
├── include/utiny.h            # UT_FORMAT_VERSION 2, UT_TOK_FN 5
├── include/utiny_facts.h      # NEW: fact-table API (open, lookup, render, read callback)
├── include/utiny_console.h    # fn sub-state, facts handle in ut_console_io
├── src/model.c                # accept v1 and v2 alphabets
├── src/facts.c                # NEW: UTFT validation, binary search, reverse scan, rendering
├── src/console.c              # fn mode: prefix on type char, render on <eos>, /info line
├── host/utiny_host.c          # --facts FILE, golden check incl. rendered text
└── tests/test_facts.c         # NEW: format, lookup, missing/n.a., parity fixtures

firmware-nodemcu/
├── include/layout.h           # UT_FACTS_FLASH_OFFSET 0x100000, UT_FACTS_AREA_SIZE 0x10000
└── src/main.cpp               # flash-read callback, facts open at boot, status line

training/
├── src/ultratiny/alphabet.py  # <fn> special (id 5), FN marker in text files
├── src/ultratiny/export.py    # UTNY v2
├── src/ultratiny/reference.py # generate() returns function output
├── src/ultratiny/factgen.py   # NEW: compute element/compound facts, checks (balance, charge)
├── src/ultratiny/facttable.py # NEW: build/write/read UTFT, lookup, render (parity twin of facts.c)
├── src/ultratiny/datagen.py   # hybrid relations, families, held-back combos, short-test guard
├── src/ultratiny/evaluate.py  # per-set report, function-output scoring, wrong-fact rate
├── src/ultratiny/golden.py    # rendered text + facts_sha256
├── src/ultratiny/cli.py       # new `ut facts`; pipeline: factgen → datagen → train → export → eval → golden → budget
├── configs/chemie-hybrid.toml        # Spark/CPU full run
├── configs/hybrid-smoke.toml         # tiny CPU run for CI/tests
├── data/templates/hybrid.toml        # NEW: 26 types × ≥ 12 forms in families
├── data/facts/chemie_gleichungen.tsv # NEW curated (balanced equations)
├── data/facts/chemie_saeuren_basen.tsv
├── data/facts/chemie_nachweise.tsv
├── data/facts/chemie_kurz.tsv        # NEW: ≤ 60-char explanations (LLM proposal + check + review)
├── data/eval/kurzarbeit.tsv          # NEW: frozen short-test set
├── tools/periodic.py                 # extended rules (shells, ions, valence)
├── tools/shorten_llm.py              # NEW (Spark): propose shortened explanations
└── tests/test_factgen.py, test_facttable.py, test_hybrid_datagen.py, test_evaluate_hybrid.py

tools/
├── budget_report.py           # facts area check
└── device_parity.py           # compare rendered answers

Makefile                       # nodemcu-flash-facts, FACTS ?= models/chemie-hybrid.utft
models/                        # chemie-hybrid.utny / .utft / _golden.json / _eval.json
```

**Structure Decision**: Keep the existing three-part layout (`training/`, `runtime/`, `firmware-nodemcu/`)
and add one module in each part. The fact table code exists twice, in Python and in C, because parity
requires it (Principle III). Both are tested against the same golden file.

## Phase overview (for /speckit-tasks)

1. **Facts first (US1 foundation)**:
   - `factgen.py`, the curated files, and `facttable.py` with the UTFT writer
   - `facts.c`, with host tests that compare against the Python fixtures
2. **Model output (US1)**:
   - alphabet `<fn>`, UTNY v2, reference function mode
   - console fn mode, `utiny-host --facts`, golden with rendered text
3. **Data (US1/US2)**:
   - `hybrid.toml` with families
   - generation of held-back combinations and families
   - unknown-object negatives, data mix
   - short explanations: LLM proposal, automatic check, user review
4. **Evaluation (US3)**:
   - short-test set draft, user review and pin
   - per-set report and wrong-fact rate
   - pipeline thresholds from SC-001–SC-005
5. **Board (all)**:
   - layout constants, flash-read callback, `make nodemcu-flash-facts`
   - budget report, measurements (speed, heap), device parity, Spark run

## Complexity Tracking

| Addition | Why Needed | Simpler Alternative Rejected Because |
|----------|------------|-------------------------------------|
| Second binary format (UTFT) and flash area at 0x100000 | FR-001/FR-013: verified facts outside the network, versioned and validated like the model | The model area has only ~18 KB of headroom (R3). `PROGMEM` couples every data fix to a firmware build. LittleFS adds a file system for one read-only blob. |
| New special token `<fn>` (UTNY v2) | R1: an unambiguous, untypable switch into function mode, and the shortest output | A printable marker can be typed by users. Per-type tokens don't fit the 96-token vocabulary. |
| Fact-table code twice (Python and C) | Principle III: the reference must reproduce the device output byte for byte | A single implementation can't run both on the board and in the Python reference. |
