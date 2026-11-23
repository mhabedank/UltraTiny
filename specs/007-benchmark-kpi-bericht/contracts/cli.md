# Contract: Benchmark Commands

All commands run from `training/` (`uv run python ../tools/<script>.py …`), like the other tools.
Exit codes: `0` ok, `1` measured but a check failed (`--check`, parity, budget in `--strict`),
`2` usage or input error (missing file, pin mismatch, unknown suite).

## `tools/bench.py pc` – PC measurement (US1, FR-011)

```text
bench.py pc --suite DIR --model FILE.utny [--facts FILE.utft] --label NAME
            [--out FILE.json] [--train-data FILE] [--jobs N] [--only SET[,SET]]
            [--check FILE.json]
```

| Option | Meaning |
|--------|---------|
| `--suite` | Suite directory, e.g. `../bench/suites/chemie` |
| `--model` / `--facts` | Model and optional knowledge image; a corrupt or missing `--facts` stops the run (exit 2) |
| `--label` | Step name for grouping seeds; default: model meta `name` |
| `--out` | Default `../bench/results/<label>_<suite>_pc_<YYYYMMDD>.json` |
| `--train-data` | Training data (`train.txt`) for the overlap report (FR-005) |
| `--jobs` | Worker processes; results are identical for any N |
| `--only` | Measure a subset (development only; the result is marked partial) |
| `--check` | Compare quality KPIs and per-question classes with this committed result; exit 1 and list differences when anything differs (FR-024) |

Also writes `<out>.s3.tsv` (rating sheet; keeps ratings whose `answer_sha256` still matches).

Console summary: one line per KPI, then `OK` or the list of differences.

## `tools/bench.py board` – board measurement (US4, FR-013/014)

```text
bench.py board --suite DIR --model FILE.utny [--facts FILE.utft] --label NAME
               (--port /dev/ttyUSB0 | --exec "utiny-host --model … --console")
               [--out FILE.json] [--firmware FILE.bin] [--sample all|parity]
```

- Never flashes or erases. With `--port` it first resets the board through RTS (as `device_smoke.py`),
  so R1 is read right after boot. Then it reads `/info` and stops (exit 2) if parameters, file size, git/date or
  the fact table `sha4` do not match `--model`/`--facts`.
- Switches `/trace json` on for the whole run (per-step times for T2/T3), then runs the board sample:
  pasted pass (all), typed pass (first 15), T3 prompts, `/stats` at start and end.
- Compares every answer with the PC adapter; mismatches go to `items[].parity = false` and the
  summary (exit 1).
- `--firmware` adds the firmware size for the budget section.
- `--sample parity` asks only 5 questions (used by CI with `--exec`).

## `tools/bench_report.py` – comparison report (US2, FR-016–021)

```text
bench_report.py RESULT.json [RESULT.json …] [--baseline LABEL] [--predecessor LABEL]
                [--ratings DIR] [--md OUT.md] [--html OUT.html] [--strict]
```

- Results with the same `label` and `kind` are seeds of one step.
- Default baseline: the first label given; columns: baseline, predecessor (if given), each other label.
- PC and board results of the same label are merged into one column (board KPIs from the board run).
- `--strict`: exit 1 when a budget or parity is broken (for later CI use).

## `tools/bench_demo.py` – demo runner (US5, FR-022)

```text
bench_demo.py --script ../bench/demo/STEP.tsv --a PORT|--a-exec CMD --b PORT|--b-exec CMD
              [--out FILE.md]
bench_demo.py --script … --single PORT --label NAME --out RUN.json     # one board, one image
bench_demo.py --merge RUN_A.json RUN_B.json --out FILE.md              # merge two single runs
```

Output table: `#`, question, answer A, answer B, first character A (ms), first character B (ms).

## `tools/bench_s2.py` – S2 probe generator (R7)

```text
bench_s2.py --filler ../bench/suites/allgemein/text/s1.txt --seed 7 --out text/s2.tsv
```

Deterministic; the output is pinned like any other test set.

## `tools/bench_export_facts.py` – reference facts export (R4)

```text
bench_export_facts.py --config configs/chemie-hybrid.toml --out ../bench/suites/chemie/facts.tsv
```

Run once per suite version; the output is reviewed and pinned.
