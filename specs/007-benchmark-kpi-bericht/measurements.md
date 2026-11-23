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

## Baseline `chemie-nodemcu` (T039, PC)

Measured by the user on a Mac (`uv run`, `--jobs 8`): 2,891 questions + S1 + S2 in 126.4 s
(SC-002). Model `7de799937683` (601,412 B). Result: `bench/results/chemie-nodemcu_chemie_pc_20261123.json`.

| KPI | Value | Note |
|-----|-------|------|
| F1 | 38.5 % (n = 257) | spec 005 reported 80.9 % on generator-made held-out phrasings; here questions are phrased independently and cover all 26 question types, also the ones the model never learned |
| F2 | 17.8 % (n = 359) | wrong facts: what spec 006 targets (≤ 1 %) |
| F3 | 62.9 % (n = 105) | |
| F4 | 7.0 % | |
| F5 | 37.7 % (n = 130) | |
| F6 | 1,404 of 2,379 | |
| R4 | 428.4 B per fact | |
| S1 / S2 | 13.31 bits per character / 0 | as for the repo model |

Baseline report: `bench/results/baseline.md` / `.html` from the two committed PC results. Board KPIs
(T1-T3, R1) and S3 stay "nicht gemessen" until T038, T040 and T041.

## Board run `chemie-nodemcu` (T040, first attempt)

NodeMCU v2 (CP2102, `/dev/tty.usbserial-0001`), firmware 293,232 B, run by the user on 2026-11-23;
170 questions in 62 min. Result: `bench/results/chemie-nodemcu_chemie_board_20261123.json`.

| KPI | Value | Spec 005 (hand measurement) |
|-----|-------|------------------------------|
| T1 typed (median of 15) | 179 ms (max 188) | 158 ms, one typed prompt: +13 % |
| T1 pasted (median) | 184 ms (max 225) | not measured |
| T2 (characters 2…n) | 4.7 chars/s | 5.1 chars/s (counted from Enter): −8 % |
| T3 (steps at ≥ 94 of 104 positions) | 3.8 chars/s | not measured |
| R1 | arena 35,504 / 36,864 B, free heap 4,960 B at boot and at the end | 4,960 B |

SC-003 (± 10 %): T2 holds; T1 is 13 % above the single spec-005 sample. The benchmark uses the median
of 15 different questions (longer ones need more prefill after Enter), so the gap is a different
sample, not a slower board; it is kept as the new reference.

Serial problems in this run: 4 "hangs" (the answer stopped mid-way, no prompt within 60 s) and one
answer with trace JSON spliced into it (`… 10 hoch 23 Tei` + `s":256356,…`): bytes were lost on the
serial line while the board sent `/trace json` output (≈ 200 bytes per character). Board and PC agreed
on all 165 other answers. Fix (after this run): the JSON trace is switched on only for the 10 T3
prompts and for the R1 reading, T2 comes from the `/stats` text, and a question whose answer is lost or
differs is asked once more (event `retry_ok` when the second answer matches). A re-run with this
version replaces the result.
