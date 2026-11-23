# Measurements: 007-benchmark-kpi-bericht

Host values from the development container (4 CPU cores, Linux x86-64), 2026-11-23. Board values
(🔌) and the Spark runs (🖥️) are filled in by T038, T039, T040 and T045.

## Code and tests

| Check | Result |
|-------|--------|
| `pytest -q` (training) | 123 passed, incl. 33 benchmark tests (`test_bench_*.py`, datagen exclusion) |
| Scoring vs. hand labels (SC-008) | 50/50 agree (`tests/fixtures/bench_scoring_sample.tsv`) |
| Pin check (SC-006) | one changed byte → exit 2 with file name and both hashes (`test_bench_suite.py`) |
| `--check` (SC-007) | a changed item class or KPI fails and names the item (`test_bench_pc.py`) |
| Board mode against `utiny-host --console` | 5-question parity sample: 0 mismatches, 2.6 s (CI step in `runtime-host`) |
| Characters outside the alphabet | the console ignores them; the PC adapter now drops them too (found by the host test) |

## Suites

| Suite | Reference facts | Properties | Sets present | Status |
|-------|-----------------|------------|--------------|--------|
| chemie | 2,379 (exported from the spec 006 fact set) | 26 | `kurzarbeit` (130, pinned `cd2a36bf…`) | unseen/unknown/offtopic/s3 and S1/S2 wait for the Spark proposals (T018) |
| allgemein | 288 (capitals and element symbols, both directions) | 4 | – | all sets wait for the Spark proposals (T018) |

## First runs (partial suites)

| Run | Questions | Time | Notes |
|-----|-----------|------|-------|
| `nodemcu.utny`, chemie, `--only kurzarbeit` | 130 | 18.4 s (1 job) | F5 8.5 %, F2 2.9 % (n = 102); the repo model knows only symbols and capitals |
| hybrid smoke model (2 × 64) with `facts.utft`, chemie, `--only kurzarbeit,facts` | 2,509 | 22.1 s (4 jobs) | answers are rendered through the fact table (no `<fn>` in any answer) |
| `nodemcu.utny`, mini fixture suite (all KPIs) | 21 + S1/S2 | 7.7 s | see below |

Estimate for a full chemie run with a NodeMCU-sized model (R13): ~190,000 reference steps at
2.1 ms ≈ 7 min with one job; with `--jobs 4` the question part shrinks accordingly (SC-002 ≤ 15 min).

## Observation: S1 and S2 on a question-answer model

On the mini fixture text, `nodemcu.utny` needs 12.0 bits per character (uniform over 87 symbols
would be 6.4). The reference itself is correct: on a trained question the answer part costs
0.000002 bits per character. The model has only ever seen `<bos> question <sep> answer`, never
running prose, and is confidently wrong on it. S2 is 0 on the mini probes: it does not copy an
invented word in prose. Both values are honest for this model kind; they become informative for the
language-model cores of specs 011-013. Whether to also report S1 on answer-style text is left for the
first real comparison.
