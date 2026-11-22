# Measurements: 006-hybrid-chemielehrer

Host values from the development container (4 CPU cores, Linux x86-64, gcc), 2026-11-22. Board
values (🔌) and the Spark run (🖥️) are filled in by tasks T044–T047.

## Fact table (T011–T017)

`uv run ut facts --config configs/chemie-hybrid.toml --out runs/facts`

| Item | Value | Budget |
|------|-------|--------|
| Question types | 26 (13–14 forms each, 5–6 families) | ≥ 20 × ≥ 10 (SC-006) |
| Objects | 118 elements, 155 compounds (90 curated + 65 computed ionic), 31 reactions, 19 test reactions | |
| Fact records | 1,597 | |
| Builder checks | 0 failures (balance, charge, molar mass, atom identities, reverse uniqueness, lengths) | |
| `facts.utft` | 29,100 B | 58,982 B (90 % of the 64 KB area): 49 % |

## Parity Python ↔ C (T019, T025, T026)

| Check | Result |
|-------|--------|
| `test_facts` / `test_facts_checked` (alignment-trapping reads) | 33 cases byte-identical |
| `parity_tiny_v2` / `_checked` (tiny v2 model, console path incl. printed answers) | 15 cases, 109 steps, 15 printed, 0 failed |
| v1 models (starter, nodemcu, tiny) | unchanged, all bit-identical |

## Firmware (T027)

PlatformIO `espressif8266@4.2.1`, `-O2`, 160 MHz.

| Item | 005 | 006 | Budget |
|------|-----|-----|--------|
| `firmware.bin` | 293,232 B | 297,280 B | 360,448 B |
| Static DRAM | 74,944 B | 75,664 B (+720 B) | +1 KB (plan) |
| Free heap at boot (estimate) | 4,960 B measured | ~4,240 B expected | > 0, measured by T046 🔌 |

## Smoke pipeline (T041, quickstart §4)

`make hybrid-smoke` (2 × 64 model, 200 steps, CPU): runs end to end in ~1 min; data 34,973
training lines, held back 236 combinations, 937 family prompts, 130 short-test questions (24
training prompts dropped because they equal a short-test question). Two runs at the same commit
give identical `facts.utft`, `golden.json` and weights (the model file differs only in the meta
`git` field). Host parity of the smoke model with `--facts`: 8 cases, 8 printed, 0 failed.

## Spark model `chemie-hybrid` (🖥️ T044)

| Set | Target | Result |
|-----|--------|--------|
| held-back combinations | ≥ 85 % (SC-001) | |
| held-back families | ≥ 85 % (SC-002) | |
| short test | ≥ 80 %, ≤ 3 % wrong facts (SC-003) | |
| wrong facts, all sets | ≤ 3 % (SC-004) | |
| refusals / false refusals | ≥ 90 % / ≤ 5 % (SC-005) | |

## On the board (🔌 T046, T047)

| Item | Target | Measured |
|------|--------|----------|
| `/info` fact table line | `OK v1` | |
| First visible character, fact answer (prefix) | ≤ 2 s | |
| Generation speed, text answer | ≥ 5 chars/s | |
| Free heap after boot | > 0, stable | |
| `tools/device_parity.py` with printed answers | all identical | |
| Erased table area: `/info` → `fehlt`, fact question → missing text, `Hi` → greeting | all OK | |
