# Quickstart: Benchmark and KPI Report

Validation scenarios for spec 007. Commands run from `training/` after `uv sync`. Formats:
[contracts/cli.md](contracts/cli.md), [contracts/suite-format.md](contracts/suite-format.md),
[contracts/result-format.md](contracts/result-format.md).

## 1. Pins hold (SC-006)

```bash
uv run python ../tools/bench.py pc --suite ../bench/suites/allgemein --model ../models/nodemcu.utny --only s1
```

Expected: runs. Then change one byte in `bench/suites/allgemein/sets/unseen.tsv` and run again:
exit 2, message names the file and both hashes. Revert the change.

## 2. Measure the repo model on the PC (US1, SC-002, SC-005)

```bash
uv run python ../tools/bench.py pc --suite ../bench/suites/allgemein --model ../models/nodemcu.utny --label nodemcu
```

Expected:
- Finishes in a few minutes.
- Writes `bench/results/nodemcu_allgemein_pc_<date>.json` with F1–F6, R2–R4, S1, S2, S3 answers and
  the identity block.
- Prints one line per KPI.
- S2 lies between 64 and 96 (context 104), with no recall at 128 and above.

Run the same command again and compare the two result files. They differ only in `env.date`.

## 3. Measure a chemistry model with and without a knowledge image (FR-007)

```bash
uv run ut pipeline --config configs/hybrid-smoke.toml --out runs/hybrid-smoke --device cpu
uv run python ../tools/bench.py pc --suite ../bench/suites/chemie --model runs/hybrid-smoke/model.utny --facts runs/hybrid-smoke/facts.utft --label smoke
```

Expected: the answers in `items[].answer` are the printed sentences (fact-table values filled in), not
function outputs. Running without `--facts` on a v2 model prints the "fact table missing" text and
scores those questions as `no_answer`.

## 4. Report and verdicts (US2)

```bash
uv run python ../tools/bench_report.py ../bench/results/nodemcu_allgemein_pc_*.json \
  ../bench/results/nodemcu_allgemein_board_*.json --md /tmp/r.md --html /tmp/r.html
```

Expected:
- Every KPI row has a value, "not measured" or "not applicable".
- Budget rows are filled.
- Building the report twice gives identical files, apart from the "generated" line.
- A copy of the result with F1 raised by 2 points shows "unchanged"; raised by 4 points, "better".

## 5. CI check (US6, SC-007)

```bash
uv run python ../tools/bench.py pc --suite ../bench/suites/allgemein --model ../models/nodemcu.utny --check ../bench/results/nodemcu_allgemein_pc.json
```

Expected: exit 0. After editing one expected answer in the committed result's `items` (simulating a
changed answer), exit 1 and the output lists that question.

## 6. Board mode without a board

```bash
cmake -S ../runtime -B ../build && cmake --build ../build -j
uv run python ../tools/bench.py board --suite ../bench/suites/allgemein --model ../models/nodemcu.utny --exec "../build/utiny-host --model ../models/nodemcu.utny --console" --sample parity --label nodemcu
```

Expected: 5 questions, all `parity: true`, exit 0; timing KPIs come from the host clock and are
marked `host` in `board.name`.

## 7. On the board (🔌 US4, SC-003)

Flash `nodemcu` as in specs/005 quickstart, then:

```bash
uv run python ../tools/bench.py board --suite ../bench/suites/allgemein --model ../models/nodemcu.utny --port /dev/ttyUSB0 --label nodemcu --firmware ../firmware-nodemcu/.pio/build/nodemcuv2/firmware.bin
```

Expected:
- Finishes within 30 min.
- T1 typed is close to 158 ms and T2 close to 5.1 chars/s (spec 005), each within 10 %.
- R1 shows an arena of 35,504 B and a free heap of about 4,960 B.
- No parity mismatch.

## 8. Baseline (🖥️ + 🔌, US3, SC-001)

On the Spark: `tools/bench.py pc --suite ../bench/suites/chemie --model <chemie-nodemcu.utny> --label chemie-nodemcu`;
on the board with `chemie-nodemcu` flashed: `tools/bench.py board …`. Commit both JSON files and
`bench/results/baseline.md`/`.html` from:

```bash
uv run python ../tools/bench_report.py ../bench/results/chemie-nodemcu_chemie_*.json ../bench/results/nodemcu_allgemein_*.json --md ../bench/results/baseline.md --html ../bench/results/baseline.html
```

Expected in a fresh checkout without models: the same command produces the same report.

## 9. Demo runner (US5)

```bash
uv run python ../tools/bench_demo.py --script ../bench/demo/007.tsv --a /dev/ttyUSB0 --b /dev/ttyUSB1 --out /tmp/demo.md
```

With one board, use `--single` once per image and then `--merge`. Expected: a table with 10–15 rows
and both answers side by side.
