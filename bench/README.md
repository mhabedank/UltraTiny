# Benchmark (specs/007-benchmark-kpi-bericht)

Everything in this directory is **evaluation data**. It is never used for training: the data
generators drop every training prompt that equals a benchmark question (spec FR-005).

| Path | Content |
|------|---------|
| `suites/<topic>/` | One benchmark suite per topic: `suite.toml` (pins, value classes, thresholds), `facts.tsv`, `sets/*.tsv`, `text/s1.txt`, `text/s2.tsv` |
| `results/` | Committed result files (`<label>_<suite>_<pc\|board>_<date>.json`), S3 rating sheets, baseline report |
| `demo/` | Demo scripts per roadmap step and their side-by-side output |

Commands (run from `training/`):

```bash
uv run python ../tools/bench.py pc --suite ../bench/suites/allgemein --model ../models/nodemcu.utny
uv run python ../tools/bench_report.py ../bench/results/*.json --md report.md --html report.html
```

Formats and options: `specs/007-benchmark-kpi-bericht/contracts/`.
