# Data Model: Benchmark and KPI Report

Entities from [spec.md](spec.md) "Key Entities". File formats are fixed in
[contracts/suite-format.md](contracts/suite-format.md) and
[contracts/result-format.md](contracts/result-format.md).

## Suite

| Field | Type | Rules |
|-------|------|-------|
| `name` | string | Directory name under `bench/suites/` (`chemie`, `allgemein`) |
| `version` | integer | Bumped on any change of a pinned file, a threshold or a value class |
| `files` | map path → SHA-256 | Every file listed here is pinned; a mismatch stops every command (FR-004) |
| `value_classes` | list of Value class | |
| `properties` | map name → Property | |
| `refusal_forms` | list of string | Prefixes or full texts that count as "refused" |
| `thresholds` | map KPI → Threshold | Fixed before the first comparison (FR-018) |
| `board_sample` | Board sample | |
| `kpis_not_applicable` | list of KPI id | E.g. nothing for chemie; listed KPIs show "not applicable" |

## Value class

| Field | Type | Rules |
|-------|------|-------|
| `name` | string | E.g. `symbol`, `element_name`, `number`, `formula`, `city`, `equation` |
| `kind` | `vocab` \| `number` | `vocab`: known values come from `facts.tsv`; `number`: numeric pattern |
| `case_sensitive` | bool | True for symbols and formulas (FR-008, spec 006 FR-012) |
| `decimals` | int | `number` only: compare after rounding to this precision; `,` and `.` both accepted |
| `units` | list of string | Optional unit after a number (`u`, `g/mol`) |

## Property

| Field | Type | Rules |
|-------|------|-------|
| `name` | string | Same names as the readable answers (`element_symbol`, `hauptstadt_von`) |
| `value_class` | Value class name | |
| `canonical` | string | Canonical question for F6 with `{name}` / `{key}` |
| `reverse` | bool | Value is a name (e.g. `symbol_element`); the question names the key |

## Reference fact (`facts.tsv` row)

| Field | Rules |
|-------|-------|
| `object` | Key, unique per suite (`Na`, `H2O`, `Frankreich`) |
| `object_name` | Display name used in canonical questions |
| `property` | A Property name |
| `value` | Exact value as it may appear in an answer |

Identity: (`object`, `property`) is unique. F6 counts these pairs (minus properties listed as not
asked).

## Test item (row of a question set)

| Field | Rules |
|-------|-------|
| `id` | Unique within the set (`un/001`, `ka/001`) |
| `kind` | `fact`, `multi`, `explain`, `refuse`, `unknown` |
| `question` | ≤ the console's question limit for the smallest model in the roadmap (70 characters) |
| `expected` | `fact`/`multi`: `property: object` entries separated by ` \| `; `explain`: keywords separated by `; `; else empty |
| `type` | Derived: the property of the first expected entry (for "per question type" breakdowns) |

## Test set

A pinned file of test items (or a text for S1, probes for S2). Version = (suite version, file
SHA-256). Sets: `unseen` (F1/F2/F4), `unknown` and `offtopic` (F3), `kurzarbeit` (F5, F2), `s3`
(S3), `s1` text, `s2` probes.

## S2 probe

| Field | Rules |
|-------|-------|
| `id` | `s2/NNN` |
| `distance` | One of the configured distances |
| `text` | Probe text |
| `control` | Control text, same length, first mention replaced |
| `target_start`, `target_len` | Character span of the second occurrence |

## Measurement run → Result file

| Field | Rules |
|-------|-------|
| `kind` | `pc` \| `board` |
| `label` | Step name used to group seeds (`chemie-nodemcu`, `chemie-hybrid`) |
| `suite` | name, version, file pins |
| `model` | SHA-256, size, parameters, ctx, git and date from meta, training seed if recorded |
| `knowledge` | SHA-256 and size of the knowledge image, or null |
| `board` | Board only: firmware identity from `/info`, board name, port |
| `env` | git commit of the benchmark, date, host or board, tool version |
| `kpis` | KPI id → KPI value |
| `items` | Per-question records (see below) |
| `overlap` | Set → count of questions found in the training data, or `unknown` |
| `events` | Board only: resets, hangs, timeouts with item id |
| `complete` | False when a board run lost items |

**Per-question record**: `set`, `id`, `question`, `answer`, `class` (`correct`, `wrong_fact`,
`refused`, `no_answer`), `too_long`, plus board timing (`first_ms`, `cps`) and `parity` (bool) for
board runs.

**KPI value**: `value` (number or null), `n` (count behind a rate), `detail` (per type, per set, S2
curve), `status` (`measured`, `not_measured`, `not_applicable`).

## Rating sheet (S3)

TSV next to the result: `id`, `answer_sha256`, `answer`, `grammar_ok` (`ja`/`nein`/empty). A
rating is used only if `answer_sha256` matches the result's answer; otherwise S3 is "not rated".

## Comparison report

Inputs: ≥ 2 result files, one marked baseline (first), optional predecessor. Content: summary
(budget broken, parity broken), per-KPI rows (values or mean ± spread, Δ, direction, threshold,
verdict), budget section, changed answers per question, S2 curve, F1 per type. Verdict ∈ {better,
worse, unchanged, not comparable, not measured, not applicable}.

State: a KPI is "not comparable" when the two results used different versions of any test set the KPI
reads.

## Demo script

`bench/demo/<step>.tsv`: `id`, `question` (10–15 rows), plus the side-by-side output
`bench/demo/<step>-<labelA>-vs-<labelB>.md` with question, answer A/B, first-character time A/B.
