# Data Model: Knowledge Compiler

Entities from [spec.md](spec.md) "Key Entities", with fields, validation rules and states. File
syntax is in [contracts/topic-format.md](contracts/topic-format.md), the binary layout in
[contracts/image-format.md](contracts/image-format.md), lookup and rendering in
[contracts/query.md](contracts/query.md). Design decisions are in [research.md](research.md).

## Topic

| Field | Type | Rules |
|-------|------|-------|
| `id` | string 1–15 B, `[a-z][a-z0-9_]*` | Unique in the repository; equals the directory name under `topics/`. Written into the image header and, through the training config, into the model meta (`topic`). |
| `schema_version` | integer 1–65535 | Bumped by the author when classes, relations or views change meaning. In the image header. |
| `title` | string | For reports only. |
| `object_files`, `fact_files` | list of paths | Relative to the topic directory; read in the given order. |
| `alphabet` | path to a training config | The model alphabet that keys and names are checked against (the chemistry topic uses `training/configs/chemie-hybrid.toml`). |
| `budget_bytes` | integer | Default 58,982 (fact area − 10 %). The build stops above it. |
| `compat` | optional paths | Oracle and change list (R10). |

## Concept class

| Field | Type | Rules |
|-------|------|-------|
| `name` | `[a-z][a-z0-9_]*`, ≤ 20 B | Unique per topic. |
| `order_by` | relation name or empty | Integer relation that orders the objects of the class (e.g. `ordnungszahl`). Empty = order of appearance in the object files. Ties are a build error. |

At most 8 classes per topic (one bit each in a view's class mask). Each class holds ≤ 65,535 objects.

## Object

| Field | Type | Rules |
|-------|------|-------|
| `key` | string ≤ 12 B | Unique across the topic, case-sensitive (`Co` ≠ `CO`). Only model-alphabet characters. |
| `name` | string ≤ 40 B | Unique per class. Only model-alphabet characters. |
| `class` | class name | Must exist. |
| `source` | string | Allowed prefix (`DATA_LICENSES.md`); `llm:` is not allowed. |

## Relation

| Field | Type | Rules |
|-------|------|-------|
| `name` | `[a-z][a-z0-9_]*`, ≤ 20 B | Unique per topic. Used in fact files, rules, view templates and the console. |
| `subject` | class name | The one class whose objects may have this relation (one class keeps columns simple, R5). |
| `type` | `text`, `int`, `dec`, `enum`, `ref` | See value types. |
| `values` | list of strings | `enum` only: the allowed values. |
| `decimals` | 0–6 | `dec` only: exact number of decimals, German comma (`63,55`). |
| `target` | class name | `ref` only: the class of the referenced objects. |
| `card` | `one` or `many` | Forward cardinality. |
| `reverse` | `none`, `one` or `many` | Whether the value side can be asked, and how many subjects one value may have. `one` is checked at build time (FR-005). |

Value types: `text` (any UTF-8 ≤ 60 B; may contain characters outside the model alphabet, e.g. `→`,
because only the board prints it), `int` (decimal digits, optional leading `-`), `dec`, `enum`, and
`ref` (the value is an object key of `target`; it renders as that object's name).

A relation has at most 65,534 distinct values; with ≤ 254 values its forward column uses 1 byte per
subject, otherwise 2 bytes.

## Fact (triple)

| Field | Type | Rules |
|-------|------|-------|
| `subject` | object key | Must exist; its class must be in `relation.subject`. |
| `relation` | relation name | Must exist. |
| `value` | string | Must parse as the relation's type; `ref` values must be keys of `target`. |
| `source` | string | Allowed prefix, not `llm:` (R14). |
| `origin` | file:line, or rule id + input facts | Set by the compiler. Kept in `build.json`, not in the image. |

**Validation** (FR-004; the build stops and names file, line and rule): unknown class, relation or
subject; value of the wrong type; a second value for a `card = one` relation; a duplicate fact;
missing or disallowed source; key or name outside the model alphabet; key > 12 B, name > 40 B,
value > 60 B; every rendered answer > 100 B (lists: first item plus continuation, R7).

## Rule

| Field | Type | Rules |
|-------|------|-------|
| `id` | string | Unique; appears in provenance and error messages. |
| `kind` | `class`, `chain`, `table` | research R8. |
| `if_relation`, `equals` / `between` | relation, value or `[lo, hi]` | `class`: the condition. `between` only for `int`/`dec`. |
| `except` | list of object keys | `class`: subjects the rule skips. |
| `first`, `then` | relation names | `chain`: `(s, first, o)` with `o` an object, and `(o, then, v)`. |
| `from`, `map` | relation, table value → value | `table`. |
| `add_relation`, `add_value` | relation, value | What the rule adds (`chain` and `table` take the value from the input). |

**States of a derived fact**: `new` (added), `same` (equal to an existing fact, dropped),
`conflict` (different value for a `one` relation → build stops, naming both origins).
The compiler runs all rules in order and repeats until a round adds nothing (≤ 32 rounds,
≤ 65,535 facts in total).

## View

| Field | Type | Rules |
|-------|------|-------|
| `name` | `[a-z][a-z0-9_<]*`, ≤ 20 B | Unique per topic. Default for forward views: the relation name; for reverse views: relation name + `<`. Used by `/wissen`. |
| `kind` | `forward`, `reverse`, `self`, `profile` | research R4. |
| `relation` | relation name | `forward`, `reverse`. For `reverse`, the relation's `reverse` must not be `none`. |
| `classes` | list of class names | Objects outside these classes get the "not applicable" text. For `reverse`, the classes of the answered subjects. |
| `template` | string | Must start with fixed text (the prefix is printed as soon as the view is known, 006 SC-007). Slots: `{name}`, `{key}`, `{v}` (the value or the list), `{r:<relation>}` (single value of another relation of the same object; `profile`). |
| `not_applicable` | string or empty | Continues the prefix; may use `{name}` and `{key}`. Empty = the topic's generic text. |
| `more` | string or empty | Continuation of a shortened list; `{n}` = number of items left out. Required when the view can return more than one item. |
| `letter` | one ASCII letter or empty | Legacy function-output type letter (FR-015). Unique per topic. |

What `{key}`, `{name}` and `{v}` mean per kind:

| Kind | Lookup key | `{key}` | `{name}` | `{v}` |
|------|-----------|---------|----------|-------|
| `forward` | subject key | subject key | subject name | value(s) of the subject |
| `reverse` | a value of the relation | the queried value | name of the first subject | subject name(s), as a list |
| `self` | object key | object key | object name | — |
| `profile` | object key | object key | object name | — (uses `{r:…}`) |

## Topic texts

| Field | Example (chemistry) | Rules |
|-------|---------------------|-------|
| `unknown` | `Das weiß ich leider nicht.` | Printed for unknown keys and unmapped letters. |
| `not_applicable` | `: dazu habe ich keine Angabe.` | Generic continuation after `{name}`. |
| `fallback_sep` | `– ` | Printed between an already printed prefix and `unknown`. |
| `list_sep`, `list_last` | `, ` and ` und ` | List words (R7). |

The firmware keeps one built-in text only: the topic-neutral "knowledge missing" message
(`Die Faktentabelle fehlt, Faktenfragen gehen gerade nicht.`, unchanged from 006).

## Competency question

| Field | Type | Rules |
|-------|------|-------|
| `view` | view name | Every view has ≥ 1 (FR-002). |
| `question` | string | German example question; for reports and, later, spec 009. |
| `key` | string | The query key. |
| `expect` | string | Expected rendered answer (exact bytes) or `unknown`/`na`. |

The build checks every competency question against the compiled image; they also become golden
cases (FR-014).

## Knowledge image

Compiled file, one per topic: header (magic `UTKI`, version 1, topic id, schema version, sizes,
CRCs), string area, classes, objects, key index, relations with value tables, columns and posting
lists, views, topic texts. Layout and validation: [contracts/image-format.md](contracts/image-format.md).

**Status at boot**: `OK`, `MISSING` (no magic), `CORRUPT` (version, CRC, sizes or offsets),
`WRONG_TOPIC` (model meta `topic` differs, R11). Only `OK` answers fact queries.

## Query

| Field | Rules |
|-------|-------|
| `view` | By legacy letter (function output, `/wissen O Cu`) or by view name (`/wissen ordnungszahl< 29`). |
| `key` | Bytes, ≤ 60 (reverse keys are values); function-output keys ≤ 12 as in 006. |
| outcome | `fact`, `na`, `unknown` (as in 006), or `missing` (status ≠ OK). |

## Build report (`build.json`)

Counts per class, relation and view; explicit and derived facts per rule; answerable facts (F7);
image size split into header, strings, objects and key index, columns, value tables, posting lists,
views; bytes per answerable fact (R5); the source data hash; and the provenance of every derived
fact. Deterministic (sorted keys, no timestamps other than the git commit).

## Compat oracle and change list (chemistry)

| File | Columns |
|------|---------|
| `topics/chemie/compat/utft1_answers.tsv` | `letter, key, outcome, answer` (exact bytes the 006 console printed) |
| `topics/chemie/compat/changes.tsv` | `letter, key, old, new, reason, reviewed` (`yes` required) |

## Fact proposal

| Field | Rules |
|-------|-------|
| `subject`, `relation`, `value` | As a fact. |
| `source` | Proposed by the model; must be replaced by a real allowed source on acceptance. |
| `reason` | The model's short justification. |
| `accepted` | `yes` / `no` / empty. Only `yes` rows with a non-`llm:` source are copied. |

## Legacy mapping for chemistry

The 26 types of 006 (`training/data/templates/hybrid.toml`) as views of the chemistry topic.
Templates are copied unchanged; `{K}` and `{O}` in `E` become `{r:kategorie}` and `{r:ordnungszahl}`.

| Letter | 006 type | View kind | Relation | Class |
|--------|----------|-----------|----------|-------|
| `S` | element_symbol | self | — | element |
| `s` | symbol_element | self | — | element |
| `O` | element_ordnungszahl | forward | ordnungszahl | element |
| `o` | ordnungszahl_element | reverse | ordnungszahl (`reverse = one`) | element |
| `M` | element_atommasse | forward | atommasse | element |
| `P` | element_periode | forward | periode | element |
| `G` | element_gruppe | forward | gruppe (display text as in 006) | element |
| `F` | element_familie | forward | familie | element |
| `K` | element_kategorie | forward | kategorie | element |
| `Z` | element_zustand | forward | zustand | element |
| `p`, `e`, `n` | protons, electrons, neutrons | forward | protonen, elektronen, neutronen | element |
| `a`, `h` | outer electrons, shells | forward | aussenelektronen, schalen | element |
| `v`, `i`, `w` | arrangement, ion, valence | forward | elektronenverteilung, ion, wertigkeit | element |
| `E` | element_profil | profile | (kategorie, ordnungszahl) | element |
| `R` | verbindung_formel | self | — | verbindung |
| `f` | formel_verbindung | self | — | verbindung |
| `m`, `b`, `c` | molar mass, bond, acid/base | forward | molare_masse, bindung, saeure_base | verbindung |
| `q` | reaktion_gleichung | forward | gleichung | reaktion |
| `t` | nachweis | forward | nachweis | nachweisreaktion |

New in 008 (no letter): `gruppe_nr` (int, generated by `prepare.py`), `hauptgruppe` (table rule
from `gruppe_nr`), class rules filling `familie`, and the reverse views of research R9.

## Second topic: chess pieces (outline)

| Item | Content |
|------|---------|
| Classes | `figur` (König, Dame, Turm, Läufer, Springer, Bauer; keys `K`, `D`, `T`, `L`, `S`, `B`), `farbe` (Weiß, Schwarz) |
| Relations | `wert` (int, reverse many), `anzahl` (int, number per side, reverse many), `zug` (text), `startfelder` (text, card many, reverse one; white pieces), `grundreihe` (int, `farbe`), `art` (enum, derived) |
| Rules | class rule `wert = 3 → art = Leichtfigur`; class rule `wert between [5, 9] → art = Schwerfigur` |
| Size | about 30–36 explicit facts, source `own` |
| Views | forward views for every relation, reverse views for `wert`, `anzahl`, `startfelder`; every view with ≥ 1 competency question |
