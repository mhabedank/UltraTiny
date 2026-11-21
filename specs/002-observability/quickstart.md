# Quickstart & Validation: Observability for Device and Model

Formats and commands: [contracts/observability.md](contracts/observability.md). Entities:
[data-model.md](data-model.md).

## Prerequisites

- Same as [001 quickstart](../001-esp32-tiny-lm/quickstart.md): CMake ≥ 3.20, C compiler, `uv`.
- For QEMU: ESP-IDF v5.4.1 and qemu-xtensa. `UT_YES=1 make qemu` installs both to `~/esp`. On
  Linux, QEMU also needs `libslirp0` and `libsdl2-2.0-0`.
- For a board: classic ESP32 with firmware + model flashed (001 Scenario A).

## Scenario A — Host: runtime, console logic, parity (FR-005, FR-006, SC-002)

```bash
cmake -S runtime -B build && cmake --build build && ctest --test-dir build
./build/utiny-host --model models/starter.utny --golden models/starter_golden.json
```

Expected:

- ctest passes 3/3. `console_logic` checks `/stats`, `/trace an|json|aus`, Ctrl-C, HALT_ERROR,
  byte identity with trace off, and logit identity with profiling on.
- The golden check reports `24 cases, 886 steps, 0 failed`.

## Scenario B — Host viewer without an emulator (US2, US3)

```bash
make observe-host                     # = observe.py --host --demo 5
```

Expected:

- Each answer is shown with characters coloured by probability, plus a timing line, a certainty
  line and profile bars.
- It ends with `Demo: 5/5 Antworten wie erwartet` and the full `/stats` text.

## Scenario C — QEMU: `/stats` and `/trace an` by hand (US1, US2, SC-001)

```bash
make qemu
```

At the prompt:

1. `/stats` shows heap values > 0, stack free, `Arena 79888 / 98304 B`, `KV-Cache: Position 1 /
   256`, CPU load per core, uptime and `Takt 240 MHz`, plus "Letzte Antwort: noch keine".
2. `/trace an`, then `Wie heißt die Hauptstadt von Italien?` prints the answer, then a
   `--- Trace: 35 Zeichen, Ende: eos ---` table and a summary line.
3. `/stats` now also shows the timings of that answer and the profile (attn and ffn dominate).
4. Ctrl-C during an answer with the trace on prints a trace with `Ende: abort` covering only the
   characters produced.
5. `/trace aus`, then the same question prints only the answer, as in 001.

Quit with Ctrl-A, then X.

## Scenario D — QEMU: viewer and parity over TCP (US3, SC-002)

```bash
make observe                                           # start QEMU, 5 demo prompts, stop QEMU
UT_QEMU_TCP=5555 UT_YES=1 tools/qemu_run.sh &          # or keep QEMU running …
cd training && uv run python ../tools/device_parity.py --tcp localhost:5555 \
    --golden ../models/starter_golden.json
```

Expected:

- `make observe` ends with `Demo: 5/5 …` and QEMU is gone afterwards (`pgrep qemu-system-xtensa`
  is empty).
- The parity check reports `device parity: 24 cases, 0 mismatches`.
- `make observe` prints `Log: logs/observe-<date>-<time>.jsonl`. The file contains one
  `session` event (`"source": "qemu"`), and per answer the `token` events, one `answer`, one
  `result` and one `sys` event, plus a final `sys` event (format: contracts/observability.md).

## Scenario E — Python checks and budget (constitution I/III)

```bash
cd training && uv sync && uv run ruff check . && uv run ruff format --check . && uv run pytest -q
uv run python ../tools/budget_report.py --model ../models/starter.utny --idf-build ../firmware/build-qemu
```

Expected:

- All tests pass. `test_observe.py` runs end-to-end when `build/utiny-host` exists.
- The budget report prints `OK`, with static DRAM ≈ 117 KB / 180 KB.

## Scenario F — Real board (SC-003, deferred until a board is available)

```bash
cd training && uv run python ../tools/observe.py --port /dev/ttyUSB0 --demo --log board.jsonl
```

Expected:

- Core 1 is near 100 % while an answer is generated.
- Compare the `ms_avg` of `/trace aus` with `/trace an` over the same prompts (several runs): the
  difference must be ≤ 5 % (SC-003).
- Record the result in [measurements.md](measurements.md).
