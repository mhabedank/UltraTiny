# Measurements: 002-observability

Development container, 2026-11-21. QEMU timings are emulated (virtual clock) and not
representative of real hardware; they only show that the values are wired up.

| Item | Value |
|------|-------|
| Golden parity, host (`utiny-host --golden models/starter_golden.json`) | 24 cases, 886 steps, 0 failed (bit-identical) |
| Golden parity, firmware in QEMU (`device_parity.py --tcp`) | 24/24 identical |
| Static DRAM (firmware, QEMU build) | 117,124 / 180,736 B (001: 112,516 B; +4,608 B) |
| App image | 220,544 B (21.0 % of 1 MB; 001: 211,504 B) |
| Arena | 79,888 B (unchanged) |
| Trace buffer | 201 steps × 20 B = 4,020 B + 384 B probabilities |
| Stack high-water mark, inference task (QEMU) | 5,848–5,880 B free of 8,192 B |
| Heap (QEMU) | ≈ 190 KB free, minimum ≈ 182 KB, largest block 108 KB |
| Trace overhead, host (`utiny-host --console`, 45 answers each) | median 0.30 ms/char with and without trace (below the 0.01 ms resolution) |
| Trace overhead, QEMU | not measurable (noise ±30 % between identical runs) |
| `make observe` in QEMU (5 demo prompts) | 5/5 as expected, QEMU stopped afterwards |
| Ctrl-C with `/trace an` in QEMU | trace over the 6 produced characters, `Ende: abort` |
| SC-003 on real hardware | **open** (release gate, needs a board) |

Stage profile in QEMU (answer "Die Hauptstadt von Italien ist Rom.", context 39→74):
embed 0.4 % | norm 1.3 % | qkv 11.1 % | attn 38.3 % | wo 10.6 % | ffn 36.8 % | head 1.6 %.
On the host the same answer spends ≈ 50 % in ffn and ≈ 25 % in attn, so the ratio on the real
Xtensa core should be checked with a board.
