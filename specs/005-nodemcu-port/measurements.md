# Measurements: 005-nodemcu-port

Host values were measured in the development container (4 CPU cores, Linux x86-64, gcc) on
2026-11-21. Hardware values (🔌) need a real NodeMCU and are filled in by the tasks named in the
table.

## Runtime change: word-access safe image reads (T004, T010)

| Check | Before (T004) | After (T010) |
|-------|---------------|--------------|
| CTest | 3/3 passed (runtime, console_logic, parity_tiny) | 7/7 passed, incl. `runtime_checked`, `parity_tiny_checked`, `parity_starter_checked` (alignment-trapping build) and `image_access_lint` |
| `utiny-host --model models/starter.utny --golden models/starter_golden.json` | 24 cases, 886 steps, 0 failed | 24 cases, 886 steps, 0 failed (bit-identical logits) |
| Golden files / fixtures changed | – | none |

Legacy ESP32 firmware (T011): the CI `firmware` job (ESP-IDF v5.4.1) builds it with the changed
runtime and passes its budget report (`--board esp32`); `ut_model` grows by 256 B (meta copy),
well inside its static DRAM (112,516 / 180,736 B before the change).

## NodeMCU model (T015, T016)

`uv run ut pipeline --config configs/nodemcu.toml --out runs/nodemcu --device cpu`, seed 1234,
3000 steps, 4 CPU threads, 725 s.

| Item | Value | Target |
|------|-------|--------|
| Parameters | 583,296 (4 × 128, MQA, d_ff 384, ctx 104) | |
| Train examples | 8,137 | |
| Demo accuracy (quantized reference) | **100 %** (33/33) | ≥ 80 % (SC-002) |
| Held-out phrasings (quantized reference) | **70.0 %** (450 prompts) | ≥ 60 % (SC-002) |
| Model file | 601,404 B | model area 688,128 B (87.4 %) |
| Arena | 35,504 B | 40,960 B (86.7 %); firmware buffer 36,864 B |
| Host parity (`utiny-host --golden models/nodemcu_golden.json`) | 24 cases, 888 steps, all bit-identical (normal and alignment-checked build) | |

Held-out is lower than the starter model's 80.8 % (ctx 256), but above the spec threshold. The
cause was not investigated; the training data also changed (NodeMCU self-description facts, 0.6 %
of the pairs no longer fit the context).

### Reproducibility (T032)

Second CPU run with the same config and seed (`runs/nodemcu-repro`): alphabet and all tensors
are **byte-identical**, eval identical (demo 100 %, held-out 70.0 %). The two files differ only in
the meta JSON field `git` (run 1 at `9fa7193`, run 2 at `16ee1f9`), which records the commit by
design (constitution IV); at the same commit the whole file is identical (covered by
`training/tests/test_determinism.py`).

## NodeMCU firmware build (T026)

PlatformIO `espressif8266@4.2.1` (Arduino core 3.1.2, GCC 10.3), `-O2`, 160 MHz,
`UT_MAX_ANSWER=104`.

| Item | Value | Budget |
|------|-------|--------|
| `firmware.bin` | 293,232 B | firmware area 360,448 B (81.4 %) |
| Static DRAM (`.data` + `.rodata` + `.bss`) | 74,944 B | 81,920 B DRAM in total |
| of which arena / console / `ut_model` | 36,864 / 4,176 / 2,008 B | |
| Heap left at boot (estimate: DRAM − static) | ~7 KB | measured by T028 via `/stats` |

The SDK and core take ~28 KB of static DRAM even for an empty sketch (measured: 28,008 B),
so ~7 KB of heap remain for the UART buffers and the SDK. Whether that is enough is checked on the
board (T028); fallback: research R5 (IRAM heap) or a smaller console trace buffer.

## On the board (🔌, T028/T029/T036–T039)

| Item | Target | Measured |
|------|--------|----------|
| First answer character after Enter (typed demo prompt) | ≤ 2000 ms | |
| Generation speed | ≥ 5 chars/s | |
| Free heap / free loop stack after boot | > 0, stable | |
| Board vs. reference (`tools/device_parity.py`) | 24/24 | |
| FR-002 console checks (umlauts, abort, empty input, emoji, determinism) | all OK | |
| Erased / corrupted / oversized model → HALT_ERROR, single boot | all OK | |
| Endurance (`tools/soak.py --count 100`, ≥ 1 h) | no reset, stable heap | |
| Fresh checkout → running PoC | < 30 min | |
