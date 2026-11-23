# Evaluation sets (specs/006-hybrid-chemielehrer)

`kurzarbeit.tsv` is the frozen short-test set (FR-010, contracts/eval-sets.md). It is written
independently of `data/templates/hybrid.toml` and is **never** used for training: `datagen` drops
every training prompt whose normalised form equals one of its questions.

| Column | Content |
|--------|---------|
| `id` | `ka/NNN` |
| `grade` | 7–10 (reporting only) |
| `kind` | `fact`, `multi`, `explain`, `refuse`, `unknown` |
| `question` | at most 70 characters (the console's question limit at context 104) |
| `expected` | `fact`/`multi`: accepted answers as `question type name: key` (type names from `data/templates/hybrid.toml`, e.g. `element_symbol: Na`), separated by ` \| ` (first = canonical); `explain`: required keywords, separated by `; `; `refuse`/`unknown`: empty |

Datagen translates `element_symbol: Na` into the function output `SNa` (type code + key) and fails on an unknown type name.

After the user's review the file's SHA-256 is pinned as `kurzarbeit_sha256` in
`configs/chemie-hybrid.toml` and `configs/hybrid-smoke.toml`; datagen refuses to run if the file
changes without a new pin.

## Review

2026-11-23: reviewed by the user (spot checks) as part of specs/007-benchmark-kpi-bericht and pinned
(`kurzarbeit_sha256 = cd2a36bf…`). The `explain` keywords were kept as they are; whether they are
strict enough is judged after the first measured results (a change is a new pinned version).
