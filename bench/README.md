# Benchmark (specs/007-benchmark-kpi-bericht)

Everything in this directory is **evaluation data**. It is never used for training: the data
generators (`training/src/ultratiny/datagen.py`, `hybrid.py`) drop every training prompt that equals
a benchmark question after normalisation and report the count as `dropped_bench_match` (FR-005).

| Path | Content |
|------|---------|
| `suites/<topic>/suite.toml` | Pins (SHA-256 of every file), value classes, properties with canonical questions, refusal forms, noise thresholds, board sample, S2 distances, `[propose]` wording for the proposal generator |
| `suites/<topic>/facts.tsv` | Reference facts (`object`, `object_name`, `property`, `value`), exported once with `tools/bench_export_facts.py` |
| `suites/<topic>/sets/*.tsv` | Question sets: `unseen` (F1/F2/F4), `unknown` + `offtopic` (F3), `s3` (S3); chemie also uses `training/data/eval/kurzarbeit.tsv` (F5) |
| `suites/<topic>/text/` | `s1.txt` (S1 test text, `# topic` / `# general` halves) and `s2.tsv` (S2 probes from `tools/bench_s2.py`) |
| `suites/<topic>/proposals/` | LLM proposals for questions and topic text (`training/tools/bench_propose_llm.py`, run on the Spark); input for the sets, never read by the benchmark |
| `results/` | Result files `<label>_<suite>_<pc\|board>_<YYYYMMDD>.json`, S3 rating sheets `<result>.s3.tsv`, the baseline report. Exception: the CI reference `nodemcu_allgemein_pc.json` has no date |
| `demo/` | Demo scripts per roadmap step (`<step>.tsv`, 10-15 questions) and their side-by-side output |

Formats: `specs/007-benchmark-kpi-bericht/contracts/`. Commands run from `training/`.

## Measure

```bash
uv run python ../tools/bench.py pc --suite ../bench/suites/chemie --model <model.utny> [--facts <facts.utft>] --label <step> [--jobs 4]
uv run python ../tools/bench.py board --suite ../bench/suites/chemie --model <model.utny> [--facts …] --label <step> --port /dev/ttyUSB0 [--firmware …/firmware.bin]
uv run python ../tools/bench_report.py ../bench/results/<baseline>*.json ../bench/results/<step>*.json --md report.md --html report.html
uv run python ../tools/bench_demo.py --script ../bench/demo/007.tsv --a /dev/ttyUSB0 --b /dev/ttyUSB1 --out demo.md
```

The board command never flashes; it measures whatever runs on the board and stops if the board's
model or fact table differs from the given files. With `--exec "../build/utiny-host --model … --console"`
it runs against the host console instead (CI does this).

## Change a test set (re-pin)

1. Edit the file. Every command now stops with a pin error naming it.
2. `uv run python ../tools/bench.py pin --suite ../bench/suites/<topic>` rewrites the hashes.
3. If results with this suite were already compared, bump `version` in `suite.toml`: the report then
   marks the affected KPIs "nicht vergleichbar" against older results.
4. Re-measure and commit `results/nodemcu_allgemein_pc.json` when the allgemein suite changed (CI
   `--check` compares it on every pull request).

## S3 ratings

`bench.py pc` writes `<result>.s3.tsv` next to each result with the 20 S3 answers. Fill the
`grammar_ok` column with `ja` or `nein`. A rating only counts while its `answer_sha256` matches the
answer; when the answer changes, the next run empties that row. The report reads the sheet.

## Test-set provenance and reviews

- `training/data/eval/kurzarbeit.tsv`: written for spec 006, reviewed by the user (spot checks) and
  pinned on 2026-11-23 (`cd2a36bf…`).
- `suites/*/facts.tsv`: exported from the project's own fact data (`own`, `wikidata`, `computed`).
- `suites/*/sets/*.tsv` and the topic halves of `text/s1.txt`: proposed by an allowed local LLM on
  the Spark (`source = llm:<model>` in `proposals/`), selected deterministically and spot-checked by
  the user before pinning (FR-006). Expected answers come from `facts.tsv`, never from the LLM.
  Reviews are recorded here with date and scope.
