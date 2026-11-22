# Data Model: Hybrid Chemistry Teacher

Entities from [spec.md](spec.md) "Key Entities", with fields, validation rules and states.
Binary layouts are in [contracts/fact-table-format.md](contracts/fact-table-format.md). The model
output grammar is in [contracts/function-output.md](contracts/function-output.md).

## Object

A thing that facts are about.

| Field | Type | Rules |
|-------|------|-------|
| `key` | string ≤ 12 B | Unique and case-sensitive. Element = symbol, compound/acid/base = formula (digits as plain characters, e.g. `Al2O3`), reaction or test reaction = lowercase slug `[a-z0-9]+`. Only characters of the model alphabet. |
| `name` | string ≤ 40 B | German name in nominative case (`Kupfer`, `Aluminiumoxid`, `Knallgasreaktion`). Unique per kind. |
| `kind` | enum | `element`, `compound`, `acidbase`, `reaction`, `test`. |
| `aliases` | list of strings | Training only (e.g. `Kochsalz` → NaCl, `Natron`): extra names that map to the same key. Not stored on the board. |
| `source` | string | `wikidata:Q…`, `computed`, `own`, `rlp-bb`. It must have an allowed prefix (`DATA_LICENSES.md`). |

## Question type

| Field | Type | Rules |
|-------|------|-------|
| `code` | 1 ASCII letter | Unique, see the table in research R4. |
| `name` | string | Internal name, e.g. `element_ordnungszahl`. |
| `kinds` | set of kinds | The object kinds the type applies to. |
| `needs_value` | bool | `false` for `S`, `s`, `R`, `f`, because their answer uses only name and key. |
| `reverse_of` | code or none | `o` → `O`: the key is a value of type `O`, resolved by scan. |
| `template` | string ≤ 100 B rendered | Slots `{name}`, `{key}`, `{v}` and `{X}` (value of type X). The prefix is the text before the first slot and is printed as soon as the type is known. Every template MUST start with a non-empty fixed prefix (SC-007). |
| `not_applicable` | string or none | E.g. `{name} bildet kein typisches Ion.` It may use only `{name}` and `{key}`. |
| `forms` | list of question forms | ≥ 12 per type (FR-007), see below. |

## Fact record

| Field | Type | Rules |
|-------|------|-------|
| `object` | Object key | Must exist. |
| `type` | Question type code | `type.needs_value` must be true and `object.kind` must be in `type.kinds`. |
| `value` | string ≤ 60 B (≤ 50 B for types `q` and `t`, whose templates are longer) | Finished display string (`29`, `63,5`, `2, 8, 18, 1`, `Na+ (einfach positiv geladen)`). It is never formatted at runtime. |
| `source` | string | `computed` (rule in `factgen.py`) or the curated source. |

**Validation by the builder** (any failure stops the build, FR-005):
- Each (object, type) pair is unique.
- Every rendered answer (template + value + name + key) is ≤ 100 B, and every value is ≤ 60 B.
- Reaction equations are balanced: atoms are counted on both sides, and coefficients and states are parsed.
- Computed ionic formulas are charge-neutral, and each computed molar mass equals the sum of its formula's atom masses.
- Elements: protons = electrons = Z; outer electrons = main group; shells = period (main groups only);
  the electron arrangement sums to Z.
- Reverse types are unambiguous: the values of the base type are unique. For example, every atomic number belongs to one element.
- Keys, names and every text the model is trained to read or write use only the model alphabet. Values, templates and fixed texts are only printed by the board and may use any UTF-8 (e.g. `→` in equations, `°`); slot control bytes appear only in templates.

## Function output

What the model produces after `<sep>`:

```text
answer   := text <eos> | <fn> type key <eos>
type     := one ASCII letter
key      := 1..12 alphabet characters
```

Interpretation and lookup states are in [contracts/function-output.md](contracts/function-output.md).

## Question form and family

| Field | Type | Rules |
|-------|------|-------|
| `text` | string | Contains `{name}` (forward) or `{key}` (reverse/symbol forms), e.g. `Nenne die Ordnungszahl von {name}.` |
| `family` | id | `w`, `imp`, `kurz`, `satz`, `alltag`, `rev`, …, with ≥ 2 forms per family. |
| `type` | code | The question type it asks. |

Each type has ≥ 12 forms in ≥ 4 families. One family per type is held back (see held-back sets).

## Training pair

`question \t target`. The target is plain text or `\x01` + type + key. `\x01` stands for `<fn>` in text
files, and `Alphabet.encode` maps it to token 5. Surface noise (lower case, no punctuation, one typo) is
applied to the question and never to the key part.

## Held-back sets

| Set | Content | Rule |
|-----|---------|------|
| `combo` | 10 % of (type, object) pairs, from a stable hash with the seed | Every object keeps ≥ 3 trained types, and every type keeps ≥ 80 % of its objects. |
| `family` | One family per type | None of its forms appears in training for that type. |
| `kurzarbeit` | `data/eval/kurzarbeit.tsv` | Frozen with a SHA-256 pin in the config. A normalised training prompt equal to a short-test question is dropped. |
| `explain` | 10 % of the short explanations (by entry id) | Same rule as the existing held-out phrasings. |
| `refusal` | Existing refusal held-out plus unknown-object negatives | As in 003/005. |

All sets are written to `runs/<name>/data/` and their hash is recorded in the run meta (FR-015).

## Short-test item

| Field | Type | Rules |
|-------|------|-------|
| `id` | `ka/NNN` | Unique. |
| `question` | string ≤ 80 chars | Written independently of `hybrid.toml`. |
| `kind` | `fact`, `explain`, `refuse`, `unknown`, `multi` | |
| `expected` | string | `fact`: one or more accepted `type key` pairs, separated by `|`. `explain`: required keywords, separated by `;`. `refuse`/`unknown`: empty. |
| `grade` | 7–10 | For reporting only. |

## Short explanation

| Field | Type | Rules |
|-------|------|-------|
| `id` | reference to a `chemie_rlp_*` or `chemie_reaktionen` id | |
| `questions` | phrasings (from the long entry, plus paraphrases) | |
| `answer` | ≤ 60 chars | Automatic check (research R8), then `reviewed = yes` by the user before it is used in training. |

## Board state (console)

```text
READY ──type──▶ TYPING ──Enter──▶ GENERATING ──text token──▶ (print) ──<eos>/max/ctx──▶ READY
                                     │
                                     └─<fn>──▶ FN_TYPE ──letter──▶ FN_KEY (print prefix)
                                                                   │  collect ≤ 12 chars
                                                                   └─<eos> or 12 chars──▶ RESOLVE
                                                                       (print rest) ──▶ READY
```

Fact table status at boot: `OK (vN, R records)`, `fehlt` or `defekt (CRC/Version)`. Model-written
answers work in every status (FR-013).
