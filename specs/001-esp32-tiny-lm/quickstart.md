# Quickstart & Validation: Tiny Language Model Demo on a Classic ESP32

> **Legacy.** Since constitution v2.0.0 the target board is the NodeMCU (ESP8266): see
> [`specs/005-nodemcu-port/quickstart.md`](../005-nodemcu-port/quickstart.md) and
> [`firmware-nodemcu/`](../../firmware-nodemcu/). This ESP32 guide stays valid for the legacy firmware.

## Prerequisites

- Classic ESP32 dev board (4 MB flash, no PSRAM) + USB cable
- macOS (Apple Silicon) or Linux
- ESP-IDF v5.x installed and exported (`. $IDF_PATH/export.sh`)
- `uv` (Python project manager), CMake ≥ 3.20, a C compiler

## Scenario A — Run the demo with the pre-built model (User Story 1, SC-001/002/003/008)

```bash
cd firmware
idf.py set-target esp32
idf.py -p <PORT> flash                      # firmware + partition table
make -C .. flash-model PORT=<PORT> MODEL=<downloaded release model.utny>
idf.py -p <PORT> monitor
```

Expected:

1. Banner per [contracts/serial-console.md](contracts/serial-console.md) shows model name,
   format v1, parameter count, flash/RAM use, "Funk: aus".
2. Type `Was ist die Hauptstadt von Frankreich?` + Enter → answer such as
   `Die Hauptstadt von Frankreich ist Paris.` streams char by char.
3. `/info` shows first-char latency ≤ 1000 ms and ≥ 10 chars/s.
4. Work through `training/data/demo_prompts.tsv`: ≥ 80% correct.
5. Ctrl-C during an answer prints `[abgebrochen]`; next prompt works without reset.

## Scenario B — Train and export on the M3 Mac (User Story 2, SC reproducibility)

```bash
cd training
uv sync
uv run ut pipeline --config configs/v1.toml --out runs/v1        # uses MPS (GPU) automatically
cat runs/v1/eval.json                                            # demo ≥ 0.80, heldout ≥ 0.60
uv run ut pipeline --config configs/v1.toml --out runs/v1-cpu --device cpu
```

Expected: completes ≤ 2 h on the M3 (GPU); `runs/v1/model.utny`, `eval.json`, `budget.json`
exist. Two CPU runs with the same seed produce byte-identical `model.utny` (`shasum`).

## Scenario C — Host parity without hardware (SC-006)

```bash
cmake -S runtime -B build && cmake --build build && ctest --test-dir build
uv --directory training run ut golden --model runs/v1/model.utny \
    --prompts data/gen/heldout.jsonl --out ../build/golden.json
./build/utiny-host --model training/runs/v1/model.utny --golden build/golden.json   # exit 0
```

## Scenario D — Swap model without rebuilding firmware (User Story 3)

```bash
make flash-model PORT=<PORT> MODEL=training/runs/v1/model.utny   # new model
idf.py -p <PORT> monitor                                         # banner shows new model
make flash-model PORT=<PORT> MODEL=corrupt.utny                  # e.g. truncated file
```

Expected: valid model → new banner; corrupt model → `FEHLER: Modell ungültig (…)`, no reboot loop.

## Scenario E — Budgets (SC-007)

```bash
make budget            # runs idf.py size + tools/budget_report.py
```

Expected: model ≤ 1.8 MB, arena ≤ 115 KB, app ≤ 90% of the factory partition → exit 0.

## Scenario F — Endurance (SC-005)

Run `tools/soak.py --port <PORT> --prompts training/data/demo_prompts.tsv --count 100`
(≥ 1 h with pauses). Expected: 100 answers, no reset banner in between, `/info` heap value stable.
