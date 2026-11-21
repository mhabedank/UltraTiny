# Implementation Plan: ESP32-Chemielehrer

**Branch**: `claude/modest-sagan-xrovbt` | **Date**: 2026-11-21 | **Spec**: [spec.md](spec.md)

## Summary

Same runtime, format and firmware as 001; only data, config and training change. A larger
model (6 × 192, MQA, d_ff 512, ctx 192, ≈ 1.75 M params) is trained on a chemistry-only
knowledge base: curriculum concept Q&A for Themenfelder 3.1–3.12 (own text), element profiles for
all 118 elements (Wikidata CC0 + computed periodic-table position), compounds and reactions (own
text), persona answers and refusal examples. Free-form answers are oversampled (FR-006); eval
gains refusal metrics (FR-008).

## Technical Context

**Language/Version**: unchanged (C11 runtime/firmware, Python 3.12 training)
**Primary Dependencies**: unchanged
**Storage**: model file ≈ 1.78 MB in the 2 MB `model` partition
**Testing**: pytest (datagen, eval metrics), golden parity host + QEMU, pipeline thresholds
**Target Platform**: classic ESP32 (unchanged); training on M3 (MPS) or CPU
**Performance Goals**: ≥ 10 chars/s on the board (estimate 11–20: 1.78 MB streamed per token)
**Constraints**: model ≤ 1.8 MB (constitution: 2 MB − 10 %), arena ≤ 96 KB firmware buffer
**Scale/Scope**: ~12 Themenfelder × ~30 concepts, 118 elements × ~8 facts, ~80 compounds

### Size check (computed)

| Item | Value |
|------|-------|
| Parameters | 1,752,768 (6 × 283,008 + tok 17,664 + pos 36,864 + norm 192) |
| Model file | ≈ 1.78 MB (int8 + per-row scales) — budget 1.887 MB ✔ |
| KV cache | 2 × 6 × 192 × 32 B = 73,728 B + scales 9,216 B |
| Arena total | ≈ 91 KB — firmware buffer 96 KB ✔, budget 115 KB ✔ |

## Constitution Check

| Principle | Status |
|-----------|--------|
| I. Budget | ✔ within 2 MB/128 KB with ≥ 10 % headroom; budget report gate unchanged |
| II. Quantized, allocation-free | ✔ unchanged runtime |
| III. Parity | ✔ golden vectors regenerated; host + QEMU checks |
| IV. Reproducible, licensed data | ✔ own text (MIT) + Wikidata (CC0), per-row `source`; pipeline scripted |
| V. Simplicity | ✔ no code changes to runtime/firmware; only config/data/eval |

## Design

- **Data files** (`training/data/`): `facts/chemie_rlp_*.tsv` (concept Q&A, relation `frei`,
  ≥ 4 phrasings, last held out), `facts/chemie_verbindungen.tsv`, `facts/chemie_reaktionen.tsv`,
  `facts/chemie_persona.tsv`, `facts/abweisen.tsv` (refusals, relation `abweisen`, free),
  `facts/wikidata_elemente_chemie.tsv` (element profiles), `templates/chemie.toml`.
- **Element profiles**: `tools/fetch_wikidata.py --chemie` adds atomic mass (rounded to 0.01 u or
  integer for very heavy elements) and melting/boiling points (normalized SI → °C, rounded);
  group, period, category and state at 20 °C are computed from the atomic number in
  `tools/periodic.py` (own, deterministic).
- **Oversampling**: `DataConfig.free_repeat` repeats free-relation train lines N times.
- **Eval**: `refusal.jsonl` (held-out off-topic) → refusal rate; false refusals counted over demo +
  held-out chemistry prompts. Pipeline thresholds from `[eval]` in `configs/chemie.toml`.
- **Config** `configs/chemie.toml`: d 192, 6 layers, 6 heads, d_ff 512, ctx 192, dropout 0.1,
  long training (steps tuned so CPU ≤ ~3 h, MPS faster).

## Complexity Tracking

None.
