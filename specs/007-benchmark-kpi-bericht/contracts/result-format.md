# Contract: Result File and Report

## Result file (`bench/results/<label>_<suite>_<pc|board>_<YYYYMMDD>.json`)

UTF-8 JSON, keys sorted, two-space indent, so diffs stay readable in pull requests.

```json
{
  "format": 1,
  "kind": "pc",
  "label": "chemie-nodemcu",
  "complete": true,
  "suite": {"name": "chemie", "version": 1, "files": {"sets/unseen.tsv": "…"}},
  "model": {"sha256": "…", "size": 601412, "params": 583296, "ctx_len": 104,
            "git": "…", "date": "2026-11-22", "seed": 1234},
  "knowledge": null,
  "board": null,
  "env": {"commit": "…", "date": "2026-11-24", "host": "spark", "tool": "bench 1"},
  "overlap": {"unseen": 0, "kurzarbeit": 0, "unknown": "unknown"},
  "kpis": {
    "F1": {"value": 41.5, "n": 200, "status": "measured",
           "detail": {"by_type": {"element_symbol": 88.0}}},
    "F2": {"value": 6.1, "n": 302, "status": "measured"},
    "S2": {"value": 96, "status": "measured", "detail": {"curve": {"16": 1.0, "128": 0.0}}},
    "T1": {"value": null, "status": "not_measured"}
  },
  "items": [
    {"set": "unseen", "id": "un/001", "question": "…", "answer": "…",
     "class": "correct", "too_long": false}
  ],
  "events": []
}
```

- Rates are in percent with one decimal; `n` is the denominator.
- `items` holds every scored question (F1–F6, S3 answers), in the order of the sets.
- Board results add `first_ms`, `cps`, `typed`, `parity` per item and `T1` detail
  `{"typed": {"median", "max"}, "pasted": {"median", "max"}}`.
- `--check` compares `kpis[*].value` of F1–F6, S1, S2, the S3 answers and every `items[].class`;
  `env`, timing and identity fields are not compared.

## KPI definitions (implementation of spec FR-009)

| KPI | Value | Source items |
|-----|-------|--------------|
| F1 | correct / all `unseen` (%), detail per property | unseen |
| F2 | wrong fact / all fact and multi items (%) | unseen + kurzarbeit |
| F3 | refused / all (%), detail per set | unknown + offtopic |
| F4 | refused / all (%) | unseen |
| F5 | correct / all (%), spec 006 rules per kind | kurzarbeit |
| F6 | count of facts answered correctly with the canonical question | facts.tsv |
| T1 | ms, median and max, typed and pasted | board sample |
| T2 | chars/s, median | board sample |
| T3 | chars/s over steps at pos ≥ 0.9 ctx | T3 prompts |
| R1 | `arena_need`, `arena_buf`, `heap_free` after boot, `heap_min` | board `/stats` |
| R2 / R3 | bytes of model / knowledge image | files |
| R4 | (R2 + R3) / F6 | — |
| S1 | bits per character: topic, general, all; coverage % | s1 |
| S2 | largest distance with ≥ 80 % recalled; curve | s2 |
| S3 | % of rated answers with `grammar_ok = ja` | s3 + rating sheet |

## Report (`bench_report.py`)

Markdown and HTML have the same sections:

1. **Header**: labels and their roles (baseline, predecessor, step), suites and versions, and seeds
   per label.
2. **Summary**: one line each for better, worse and unchanged counts, plus `budget broken` and
   `parity broken` when either applies.
3. **KPI table**, one row per KPI: group, KPI, direction (↑/↓), value per label (mean ± spread with
   seeds), Δ to the baseline, Δ to the predecessor, threshold and verdict.
4. **Budget**:
   - model area 688,128 B
   - arena ≤ 35 KB and ≥ 10 % reserve of the 40,960 B budget
   - firmware area 360,448 B
   - fact area 58,982 B

   Each row shows its value, limit and ok/broken. The limits are imported from
   `tools/budget_report.py`.
5. **Changed answers**: id, question, class in each result, answer text.
6. **Charts** (HTML only, inline SVG): S2 recall curve and F1 per property.
7. **Test-set overlap and incomplete runs**.

Verdict rules: [research.md R9](../research.md#r9--seeds-noise-threshold-and-verdicts).
