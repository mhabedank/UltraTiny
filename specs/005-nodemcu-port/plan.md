# Implementation Plan: UltraTiny PoC on NodeMCU (ESP8266)

**Branch**: `claude/keen-feynman-z2sszl` | **Date**: 2026-11-21 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/005-nodemcu-port/spec.md`

## Summary

Run the starter model offline on a NodeMCU (ESP8266) with the same serial console as the ESP32.
Approach (details in [research.md](research.md)):

- Retrain the starter architecture with `ctx_len = 104` (arena 35.5 KB, 86.7 % of the 40 KB
  budget) as `configs/nodemcu.toml`; update the self-description facts.
- Make the portable C runtime **word-access safe** (aligned 32-bit loads only from the model image),
  because the ESP8266 faults on byte loads from mapped flash. No format change, bit-identical
  results.
- New firmware `firmware-nodemcu/` on the Arduino core via PlatformIO: a thin platform layer
  feeding the existing `ut_console`, Wi-Fi off, static arena, model in a fixed flash area inside the
  1 MB mapped window (`0x58000`, flashable without rebuilding).
- Budget report gets board profiles (`--board nodemcu` default), CI gets a `firmware-nodemcu`
  build job. Parity and speed are proven on a real board.

## Technical Context

**Language/Version**: C11 (runtime, unchanged standard), C++17 only for the ~150-line Arduino
platform layer; Python 3.11+ (training, tools)

**Primary Dependencies**: Arduino core for ESP8266 3.1.x via PlatformIO `espressif8266`
(versions pinned in `platformio.ini`); existing PyTorch/NumPy training stack; esptool

**Storage**: model file in a raw flash area (`0x58000`–`0xFFFFF`, 672 KB), memory-mapped

**Testing**: CTest (host runtime, golden parity, new `UT_IMAGE_ACCESS_CHECK` build), pytest
(training), `pio run` in CI, serial tools on a real board (`device_parity.py`, `device_smoke.py`,
`soak.py`)

**Target Platform**: NodeMCU v2/v3 (ESP8266EX, Xtensa LX106 at 160 MHz, no FPU, ~80 KB DRAM,
4 MB flash, first 1 MB mapped)

**Project Type**: embedded firmware + portable C library + Python training pipeline (existing
repository layout)

**Performance Goals**: first answer character ≤ 2 s, ≥ 5 chars/s (constitution v2.0.0 defaults);
estimate ~8–11 chars/s, first character at risk for long prompts (research R7, gate G-Speed)

**Constraints**: model ≤ 672 KB model area (≤ 700 KB constitution), firmware + model ≤ 1 MB mapped
window, arena ≤ 40 KB, all with ≥ 10 % headroom; no heap at inference; 4 KB loop stack; watchdog
~3 s

**Scale/Scope**: one model (~589k params, 2,578 Q&A pairs), one board type, ~150 lines platform
code, ~100 lines runtime change, one new training config, budget-report and CI extensions

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Check (before research) | After design |
|-----------|-------------------------|--------------|
| I. Hard on-device budget | Spec states board and budgets (constitution v2.0.0 defaults). | ✅ Concrete numbers: model ~600 KB / 672 KB area, arena 35,520 / 40,960 B, firmware area 352 KB, window 1 MB; budget report enforces them per board ([contract](contracts/budget-report.md)). Speed is an estimate → gate G-Speed requires a hardware measurement before release. |
| II. Quantized, allocation-free | int8 weights, static arena kept. | ✅ No format change; static arena `UT_ARENA_MAX = 36 KB`; weights read in place via aligned 32-bit loads ([contract](contracts/runtime-image-access.md)). Float use unchanged; justified by parity and to be re-checked against the soft-float share measured in G-Speed. |
| III. Reference parity | Golden tests exist. | ✅ Runtime change must stay bit-identical (existing golden tests + new access-check build); new `nodemcu_golden.json`; device parity on a real board before release (no emulator). |
| IV. Reproducible training | Pipeline exists. | ✅ New config only; same seeds and run metadata; no new data sources (self-description facts are own data, already licensed as `own`). |
| V. Simplicity & portability | C runtime + thin platform layer. | ✅ Runtime stays plain C; Arduino code limited to `main.cpp` (UART, clock, flash address, Wi-Fi off). One code path for image access on all platforms. |

Gates:

- **G-Budget** (CI): budget report `--board nodemcu` passes for `models/nodemcu.utny` and the
  built firmware.
- **G-Parity** (CI + hardware): host golden parity in CI; 100 % device parity before release.
- **G-Speed** (hardware, early): measure per-token time and first-character latency on a real board
  right after the first firmware boots. If the first character exceeds 2 s for demo prompts,
  apply the mitigations in research R7 in order; if still over budget, stop and propose a budget
  amendment instead of merging.

No violations; Complexity Tracking stays empty.

## Project Structure

### Documentation (this feature)

```text
specs/005-nodemcu-port/
├── spec.md
├── plan.md              # this file
├── research.md          # Phase 0
├── data-model.md        # Phase 1
├── quickstart.md        # Phase 1
├── contracts/
│   ├── flash-layout.md
│   ├── runtime-image-access.md
│   └── budget-report.md
├── checklists/requirements.md
├── measurements.md      # filled during implementation (hardware values)
└── tasks.md             # Phase 2 (/speckit-tasks)
```

### Source Code (repository root)

```text
runtime/                       # portable C runtime (changed: word-access safe image reads)
├── include/utiny.h            # ut_model gains meta_buf[256]
├── src/mathx.[ch]             # ut_ld32, word-based ut_dot_i8 / ut_matvec
├── src/model.c                # header/meta copy, dims % 4 check
├── src/crc32.c                # word loop
├── src/forward.c              # embedding lookup via ut_ld32
└── tests/                     # + access-check build, golden for nodemcu model

firmware-nodemcu/              # NEW: Arduino core / PlatformIO firmware
├── platformio.ini             # board nodemcuv2, 160 MHz, pinned platform, -ffp-contract=off
├── ld/eagle.flash.4m.ultratiny.ld # firmware area 352 KB, model area from 0x58000
├── include/layout.h           # UT_MODEL_FLASH_OFFSET, UT_ARENA_MAX
└── src/main.cpp               # Wi-Fi off, UART io callbacks, static arena, loop + yield

firmware/                      # legacy ESP32 firmware (unchanged, still built in CI)

training/
├── configs/nodemcu.toml       # NEW: starter dims, ctx 104, max answer 72
└── data/facts/starter.tsv     # self-description facts → NodeMCU/ESP8266 (+ demo_prompts.tsv)

models/
├── nodemcu.utny               # NEW: trained PoC model
└── nodemcu_golden.json        # NEW: golden cases

tools/
├── budget_report.py           # board profiles, --pio-build
└── device_*.py, soak.py       # unchanged protocol; docs/flash hints for NodeMCU

Makefile                       # nodemcu-build / -flash / -flash-model / -monitor
.github/workflows/ci.yml       # + firmware-nodemcu job, budget report --board nodemcu
```

**Structure Decision**: keep the existing layout; add `firmware-nodemcu/` next to the legacy
`firmware/` so both build from the same `runtime/`. The model, config and golden files follow the
naming of the starter model.

## Complexity Tracking

No constitution violations to justify.
