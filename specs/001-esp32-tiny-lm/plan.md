# Implementation Plan: Tiny Language Model Demo on a Classic ESP32

**Branch**: `claude/modest-sagan-xrovbt` | **Date**: 2026-11-20 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `/specs/001-esp32-tiny-lm/spec.md`

## Summary

A German, character-level question-answering transformer (~0.6 M parameters, int8 weights) is
trained on a fixed knowledge base on the developer's M3 Mac (MPS GPU, CPU fallback), exported to
a self-describing UTNY v1 file, flashed into a dedicated 2 MB flash partition, and run fully
offline on a classic ESP32. A portable C runtime reads weights in place from memory-mapped flash,
uses a ≈ 78 KB static arena (MQA + int8 KV cache), prefills while the user types, and streams the
answer over the serial console. A NumPy reference reproduces the device math bit-exactly and
gates every change via golden vectors. See [research.md](research.md).

## Technical Context

**Language/Version**: C11 (runtime + firmware); Python 3.12 (training, reference, tools)

**Primary Dependencies**: ESP-IDF v5.x (firmware); PyTorch ≥ 2.5 with MPS backend, NumPy (training);
`uv` (Python env); CMake + CTest (host runtime)

**Storage**: Model file in a raw flash data partition (`model`, 2 MB), memory-mapped; training
data as TSV/TOML files in the repo

**Testing**: pytest (training/reference), CTest host tests + golden-vector parity
(`utiny-host --golden`), `idf.py build` + budget report in CI, manual on-device checks per
[quickstart.md](quickstart.md)

**Target Platform**: classic ESP32 (Xtensa LX6, 240 MHz, 520 KB SRAM, no PSRAM, 4 MB flash);
training on macOS Apple Silicon (M3) with Linux/CPU fallback

**Project Type**: embedded firmware + portable C library + Python training toolkit

**Performance Goals**: ≥ 10 chars/s generation (expected ≥ 25), first answer char ≤ 1 s after
Enter (expected ≈ 70 ms via typing-time prefill), training ≤ 2 h on M3 GPU

**Constraints**: model ≤ 2 MB flash, inference RAM ≤ 128 KB (planned ≈ 78 KB), no heap use at
inference, radios off, bit-exact host/device/reference parity, CC0/own data only

**Scale/Scope**: ~3,000 German facts, ~10 topics, ≥ 8 question templates per relation;
one board type; single-turn Q&A

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Gate | Pre-design | Post-design |
|-----------|------|-----------|-------------|
| I. Hard On-Device Budget | Budgets stated; verified by report; ≥ 10% headroom | ✔ spec FR-010 | ✔ model ≈ 0.61 MB / 2 MB; arena ≈ 78 KB / 128 KB; `make budget` fails on < 10% headroom (R3, R12) |
| II. Quantized, Allocation-Free | ≤ 8-bit weights, static arena, in-place flash reads, int preferred | ✔ | ✔ int8 per-row weights, int8 KV, int8×int8 matmuls; float only for norm/softmax (justified below); `esp_partition_mmap` (R4, R7) |
| III. Reference Parity | Python reference, host-buildable C, golden vectors | ✔ FR-014 | ✔ `reference.py`, `utiny-host --golden`, CI job `runtime-host` (R5, R13) |
| IV. Reproducible Training & Export | scripted, seeded, versioned format, data licenses | ✔ FR-011/012/015 | ✔ `ut pipeline`, `run.json`, UTNY magic + version + CRC, Wikidata CC0 + own data in `DATA_LICENSES.md` (R10, R11) |
| V. Simplicity & Portability | plain C, thin platform layer, measured complexity | ✔ | ✔ `runtime/` has no SDK deps; only `firmware/main` touches ESP-IDF; optional dual-core split only if measurements require it (R6, R9) |

**Result**: PASS (pre- and post-design). One justified use of float math recorded below.

## Project Structure

### Documentation (this feature)

```text
specs/001-esp32-tiny-lm/
├── plan.md              # This file
├── research.md          # Phase 0
├── data-model.md        # Phase 1
├── quickstart.md        # Phase 1
├── contracts/
│   ├── model-format.md  # UTNY v1 binary layout
│   ├── runtime-api.md   # C API + host CLI
│   ├── serial-console.md# device console protocol
│   └── training-cli.md  # ut datagen/train/export/eval/golden/pipeline
└── tasks.md             # Phase 2 (/speckit-tasks)
```

### Source Code (repository root)

```text
training/                      # Python (uv project)
├── pyproject.toml
├── configs/{v1.toml,tiny-test.toml}
├── data/
│   ├── facts/*.tsv            # knowledge base (Wikidata CC0 snapshot + own facts)
│   ├── templates/*.toml       # German question/answer templates (train/heldout split)
│   └── demo_prompts.tsv       # demo list with expected answers (SC-003)
├── tools/fetch_wikidata.py    # one-off snapshot refresh (not part of the pipeline)
├── src/ultratiny/
│   ├── alphabet.py            # symbols, encode/decode
│   ├── datagen.py             # facts × templates → examples
│   ├── model.py               # PyTorch model (R1) + fake-quant for QAT
│   ├── train.py               # MPS/CPU training loop, seeding, run.json
│   ├── quant.py               # shared quantization rules
│   ├── export.py              # UTNY v1 writer
│   ├── reference.py           # NumPy bit-exact device math (R4/R5)
│   ├── evaluate.py            # SC-003/004 scoring via reference
│   ├── golden.py              # parity vectors
│   └── cli.py                 # `ut` entry point
└── tests/

runtime/                       # portable C11, no SDK dependencies
├── CMakeLists.txt             # IDF component if ESP_PLATFORM, else lib + host CLI + tests
├── include/utiny.h
├── src/{model.c,forward.c,mathx.c,alphabet.c,crc32.c}
├── host/utiny_host.c          # CLI + golden checker
└── tests/                     # CTest unit tests + tiny test model fixture

firmware/                      # ESP-IDF project (platform layer only)
├── CMakeLists.txt             # EXTRA_COMPONENT_DIRS = ../runtime
├── partitions.csv             # R7 layout
├── sdkconfig.defaults         # radios off, console UART0 115200, -ffp-contract=off
└── main/{main.c,console.c,model_partition.c}

tools/
├── budget_report.py           # Constitution I gate
└── soak.py                    # SC-005 endurance over serial

Makefile                       # flash-model, budget, test shortcuts
DATA_LICENSES.md
.github/workflows/ci.yml       # python, runtime-host, firmware jobs
```

**Structure Decision**: Three top-level parts mirroring the constitution: `training/` (Python,
reproducible pipeline + reference), `runtime/` (portable, host-testable C), `firmware/` (thin
ESP-IDF platform layer). The runtime is shared by firmware and host via one CMake file.

## Complexity Tracking

| Violation | Why Needed | Simpler Alternative Rejected Because |
|-----------|------------|-------------------------------------|
| Float32 for RMSNorm, softmax and attention-weighted V sum (Principle II prefers integer) | Classic ESP32 has a hardware single-precision FPU, so these ops are cheap; all are IEEE-exact ops plus a project-owned `exp`, so parity stays bit-exact | Fully fixed-point requantization needs many extra scale/shift parameters and code with no speed gain on this core |
| Int8 quantized KV cache (extra scales, more parity surface) | Keeps the arena at ≈ 78 KB inside the 128 KB budget | float16/float32 KV needs 128 KB / 256 KB even with MQA |
