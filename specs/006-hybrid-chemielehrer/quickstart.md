# Quickstart: Validate the Hybrid Chemistry Teacher

These scenarios prove that feature 006 works end to end. Commands use the layout in [plan.md](plan.md).
Formats are in [contracts/](contracts/).

## Prerequisites

- The repository with `uv` (training env), CMake and gcc (runtime), PlatformIO and esptool (board).
- For the full run: the DGX Spark (`training/SPARK.md`). Any CPU works for the smoke run.
- The NodeMCU from feature 005 on USB (e.g. `/dev/cu.usbserial-0001`).

## 1. Fact table builds and checks itself (US1, FR-004/FR-005)

```bash
cd training && uv run ut facts --config configs/chemie-hybrid.toml --out runs/facts
```

Expected:
- A summary with ≥ 20 types, records per type and the size, ≤ 58,982 B.
- 0 failed checks: equations balanced, ionic formulas neutral, molar masses consistent, reverse types unique.
- Spot checks in `runs/facts/facts.json`: Cu → O = 29; S → a = 6; Al2O3 → R; H2O → m = `18,0`.

## 2. Python and C render the same answers (FR-014)

```bash
cd training && uv run pytest tests/test_facttable.py tests/test_factgen.py -q
cmake -S runtime -B build/runtime && cmake --build build/runtime && ctest --test-dir build/runtime
```

Expected: all pass, including `test_facts` and `test_facts_checked` (alignment-trapping build). The
fixture cases cover forward, reverse (`o29`), not applicable (`iNe`), an unknown key, and a missing or
corrupt table.

## 3. Data generator shows variety and honest held-back sets (US3, FR-006/FR-007/FR-009)

```bash
cd training && uv run ut datagen --config configs/chemie-hybrid.toml --out runs/hybrid/data
```

Expected report:
- ≥ 20 types, each with ≥ 10 forms in ≥ 4 families
- every two-way relation in both directions
- sizes of `heldout_combo`, `heldout_family` and `kurzarbeit`
- `kurzarbeit` pin OK, and the number of training prompts dropped for matching it
- `train.txt` contains `\x01`-targets and plain-text targets in the configured mix

## 4. Smoke pipeline on CPU (FR-015)

```bash
cd training && uv run ut pipeline --config configs/hybrid-smoke.toml --out runs/hybrid-smoke --device cpu
```

Expected: it finishes in minutes and writes `model.utny` (v2), `facts.utft`, `golden.json` (with `text`
and `facts_sha256`), `eval.json` (per-set report) and `budget.json`. Quality thresholds are not met at
smoke size, which is expected; the smoke config sets them to 0. Running it twice gives identical files
apart from the git field.

## 5. Full training on the Spark (US1–US3)

```bash
# on the Spark
cd ~/UltraTiny && git fetch && git checkout claude/keen-feynman-z2sszl && git pull
cd training && NAME=chemie-hybrid tools/spark/train.sh configs/chemie-hybrid.toml 1234
# on the Mac: live loss
make spark-loss SPARK_PATTERN='chemie-hybrid*.log'
```

Expected: `eval.json` meets SC-001–SC-005:
- held-back combinations ≥ 85 %
- held-back families ≥ 85 %
- short test ≥ 80 % with ≤ 3 % wrong facts
- refusals ≥ 90 %, false refusals ≤ 5 %

Copy `model.utny`, `facts.utft`, `golden.json` and `eval.json` to `models/chemie-hybrid*` by hand
(as in 005).

## 6. Host parity with the trained model (SC-008)

```bash
build/runtime/utiny-host --model models/chemie-hybrid.utny --facts models/chemie-hybrid.utft \
  --golden models/chemie-hybrid_golden.json
```

Expected: all cases are bit-identical in tokens **and** printed text.

## 7. On the board (SC-007, FR-013)

```bash
make nodemcu-flash-model NODEMCU_MODEL=models/chemie-hybrid.utny ESPTOOL=esptool
make nodemcu-flash-facts FACTS=models/chemie-hybrid.utft ESPTOOL=esptool
make nodemcu-monitor
```

Type, and check:

| Input | Expected |
|-------|----------|
| `/info` | Model v2, `Faktentabelle: OK v1, … Einträge` |
| `Welche Ordnungszahl hat Kupfer?` | `Die Ordnungszahl von Kupfer ist 29.` The prefix appears within ~0.5 s. |
| `Was ist N?` | `Das Symbol N steht für Stickstoff.` |
| `Wie viele Außenelektronen hat Schwefel?` | `… Schwefel ist 6.` |
| `Stelle die Formel von Aluminiumoxid auf` | `… Al2O3.` |
| `Was ist eine chemische Reaktion?` | Model-written text, ≤ 60 chars |
| `Hi` / `Wie wird das Wetter morgen?` | Greeting / refusal |
| `/stats` after a text answer | ≥ 5 chars/s, heap > 0 and stable |

Then:

```bash
python tools/device_parity.py --port /dev/cu.usbserial-0001 --golden models/chemie-hybrid_golden.json
```

Expected: every case is identical, including the printed text.

FR-013 check: erase the table area (`esptool erase_region 0x100000 0x10000`) and reboot. `/info` shows
`Faktentabelle: fehlt`, a factual question gives the "missing" text, and `Hi` still gets a greeting.

## 8. Budgets

```bash
make budget BOARD=nodemcu
```

Expected: model, arena, firmware and **facts** are each within budget with ≥ 10 % headroom, and firmware + model stay within 1 MB.
