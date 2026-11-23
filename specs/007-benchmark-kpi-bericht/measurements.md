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

Assembled from the Spark proposals (T018, `qwen3.6:35b` with check prompt) with
`tools/bench_assemble.py` (seed 7); pinned, review by the user pending (T022, T027).

| Suite | Facts | unseen (T3) | unknown | offtopic | kurzarbeit | s3 | S1 topic + general | S2 |
|-------|-------|-------------|---------|----------|------------|----|--------------------|----|
| chemie | 2,379 / 26 properties | 257 (10), all 26 properties | 50 | 55 | 130 | 20 | 10,861 + 10,084 | 104 |
| allgemein | 288 / 4 properties | 79 (10) | 50 | 26 | – | 20 | 10,040 + 10,084 | 104 |

- S1 general half: Kafka, *Die Verwandlung* (public domain, Gutenberg #22367); 100 % of its characters
  are in the model alphabet.
- One chemistry paragraph was dropped because it shared a 40-character span with the curriculum data
  (`test_s1_texts_not_in_training_data`).
- S3 (allgemein): fact-like prompts ("Hauptstadt Frankreich?") were removed and the set filled from
  unused off-topic proposals.

## Repo model `nodemcu.utny` (T023, reference result for CI)

`bench.py pc --suite ../bench/suites/allgemein --model ../models/nodemcu.utny --label nodemcu`,
1 job, 185.7 s → `bench/results/nodemcu_allgemein_pc.json`.

| KPI | Value | Note |
|-----|-------|------|
| F1 | 88.6 % (n = 79) | per type: element_symbol 95, symbol_element 90, hauptstadt_land 90, hauptstadt_von 78.9 |
| F2 | 6.3 % (n = 79) | |
| F3 | 0.0 % (n = 76) | the starter data has no refusals; unknown countries get an invented capital |
| F4 | 0.0 % | |
| F6 | 287 of 288 | |
| R2 / R4 | 601,404 B / 2,095.5 B per fact | |
| S1 | 13.50 bits per character (topic 13.40, general 13.61), coverage 100 % | see the observation below |
| S2 | 0 (no recall at any distance) | |

Same model on the chemie suite (not a baseline, timing only): 2,891 questions + S1 + S2 in 262.8 s
with `--jobs 3` (SC-002: ≤ 15 min). F1 1.9 %, F2 5.3 %, F5 8.5 %, F6 51.

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
