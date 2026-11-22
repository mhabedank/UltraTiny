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
| `expected` | `fact`/`multi`: accepted function outputs `type+key`, separated by `\|` (first = canonical); `explain`: required keywords, separated by `;`; `refuse`/`unknown`: empty |

After the user's review the file's SHA-256 is pinned as `kurzarbeit_sha256` in
`configs/chemie-hybrid.toml` and `configs/hybrid-smoke.toml`; datagen refuses to run if the file
changes without a new pin.
