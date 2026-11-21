# Quickstart / Validation: 005-nodemcu-port

Runnable checks that prove the feature end to end. Details: [flash layout](contracts/flash-layout.md),
[budget report](contracts/budget-report.md), [runtime image access](contracts/runtime-image-access.md).

## Prerequisites

- A NodeMCU v2/v3 (ESP8266, 4 MB flash) and a USB data cable; USB-serial driver for CP2102 or CH340.
- Python 3.11+ with `uv`, PlatformIO (`pip install platformio`), `esptool.py`.
- A C compiler and CMake for the host checks.

## 1. Host checks (no hardware) – FR-007, FR-008 (host part)

```bash
cmake -S runtime -B build -DUT_IMAGE_ACCESS_CHECK=ON && cmake --build build -j
ctest --test-dir build --output-on-failure
./build/utiny-host --model models/nodemcu.utny --golden models/nodemcu_golden.json
```

Expected: all tests pass; golden parity "all logits bit-identical"; the existing starter and tiny
golden tests still pass (runtime change is bit-exact).

## 2. Train the NodeMCU model – User Story 2

```bash
cd training && uv run ut pipeline --config configs/nodemcu.toml --out runs/nodemcu --device cpu
```

Expected: model file, `eval.json` with demo ≥ 80 % and held-out ≥ 60 % (SC-002), golden file.
Running it twice on CPU with the same seed gives byte-identical model files.

## 3. Budget gate – FR-004, FR-005, SC-004

```bash
python tools/budget_report.py --model models/nodemcu.utny --board nodemcu --pio-build firmware-nodemcu/.pio/build/nodemcuv2
```

Expected: every line `OK` with ≥ 10 % headroom. Negative check: `--model models/starter.utny`
(ctx 256) fails on `arena`.

## 4. Build and flash – User Story 1, SC-006

```bash
esptool.py --port /dev/ttyUSB0 flash_id
make nodemcu-flash PORT=/dev/ttyUSB0
make nodemcu-flash-model PORT=/dev/ttyUSB0 MODEL=models/nodemcu.utny
make nodemcu-monitor PORT=/dev/ttyUSB0
```

Expected: `flash_id` reports ESP8266EX and 4 MB. The banner shows model `nodemcu`, format
version 1, parameter count, memory use and `NodeMCU (ESP8266)`, then `> `. Typing
`Auf welchem Chip läufst du?` answers with the NodeMCU/ESP8266. Time this from a fresh checkout
with a pre-built model: target under 30 minutes.

## 5. On-board checks – SC-001, SC-003, SC-005, FR-009, FR-012

```bash
cd training
uv run python ../tools/device_parity.py --port /dev/ttyUSB0 --golden ../models/nodemcu_golden.json
uv run python ../tools/device_smoke.py --port /dev/ttyUSB0
uv run python ../tools/soak.py --port /dev/ttyUSB0 --count 100
```

Expected: parity 100 % identical; `/info` after demo prompts shows first character ≤ 2000 ms and
≥ 5 chars/s; soak: no reset (`reset_reason` stays "Power on"/"External"), free heap stable.
Robustness: erase the model area (`esptool.py erase_region 0x58000 0xA8000`) → `FEHLER: Modell
ungültig (1: …)`, console stays responsive, single boot.

Record all measured values in `specs/005-nodemcu-port/measurements.md`.
