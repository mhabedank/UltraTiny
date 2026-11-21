# Measurements: 001-esp32-tiny-lm

## Starter model (`models/starter.utny`)

Trained with `uv run ut pipeline --config configs/starter.toml --out runs/starter --device cpu`
in the development container (4 CPU cores, no GPU) on 2026-11-20.

| Item | Value |
|------|-------|
| Facts / train examples / held-out prompts | 164 / 8,212 / 452 |
| Parameters | 602,752 (4 × 128, MQA, d_ff 384, ctx 256) |
| Training time (CPU, 3000 steps, batch 64) | 582 s |
| Demo accuracy (SC-003, quantized reference) | **100 %** (32/32) |
| Held-out phrasings (SC-004, quantized reference) | **80.8 %** (452 prompts) |
| Model file | 621,468 bytes (29.6 % of 2 MB) |
| Inference arena | 79,888 bytes (60.9 % of 128 KB) |
| Firmware app image | 211,504 bytes (20.2 % of the 1 MB factory partition) |
| Static DRAM (firmware incl. 96 KB arena) | 112,516 / 180,736 bytes |

History: the first run reached only 58.6 % / 50.2 % held-out (the model memorized phrasings).
More reverse-question templates, dropout 0.1 and word-level noise (filler words, dropped words)
raised it to 80.8 %. A leak (noisy variants reproducing held-out prompts) was found and fixed
before this measurement.

## Parity (SC-006)

| Check | Result |
|-------|--------|
| Host C runtime vs. NumPy reference, `utiny-host --golden models/starter_golden.json` | 24 cases, 886 steps, **all logits bit-identical** |
| Firmware in QEMU (esp32, Xtensa LX6 emulation) vs. golden text | **24/24 identical** |
| Real board, `tools/device_parity.py` | _pending (T046)_ |

## Robustness (User Story 3, emulated)

| Case | Result in QEMU |
|------|----------------|
| Payload byte flipped | `FEHLER: Modell ungültig (4: Daten-Pruefsumme falsch …)`, `/info` works, single boot |
| Empty (erased) model partition | `FEHLER: Modell ungültig (1: keine UTNY-Datei …)`, `/info` works, single boot |

## On real hardware (to be filled in by T046 / T068)

| Item | Target | Measured |
|------|--------|----------|
| First answer character after Enter (typed prompt) | ≤ 1000 ms | |
| Generation speed | ≥ 10 chars/s | |
| Board vs. reference (`tools/device_parity.py`) | 24/24 | |
| Endurance (`tools/soak.py`, 100 prompts ≥ 1 h) | no reset, stable heap | |
| Fresh checkout → running demo | < 30 min | |
| v1 training time on M3 (MPS) | ≤ 2 h | |
| v1 demo / held-out accuracy | ≥ 80 % / ≥ 60 % | |
| v1 MPS run twice, same seed | eval within ±1 pp | |
