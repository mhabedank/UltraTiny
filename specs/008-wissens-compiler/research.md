# Research: Knowledge Compiler (Topic-Independent)

Phase 0 of [plan.md](plan.md). Every open point of the Technical Context is decided here. Sources:
[spec.md](spec.md), the research reports
[02](../../research/2026-11-architektur/02-domaenenmodell.md) and
[03](../../research/2026-11-architektur/03-baukasten-potenzial.md), the 006 contracts
([fact-table-format.md](../006-hybrid-chemielehrer/contracts/fact-table-format.md),
[function-output.md](../006-hybrid-chemielehrer/contracts/function-output.md)), and a measurement of
today's table (R1).

## R1 · Where the bytes of the 006 table go

Measured on `ut facts --config configs/chemie-hybrid.toml` (2026-11-28, `facts.utft` 29,100 B,
sha256 `398b433c…`):

| Part | Bytes | Share |
|------|-------|-------|
| Header | 64 | 0.2 % |
| Types (26 × 16 B) | 416 | 1.4 % |
| Objects (323 × 12 B) | 3,876 | 13.3 % |
| Records (1,597 × 8 B) | 12,776 | 43.9 % |
| Strings (1,201 distinct strings, NUL-terminated) | 11,968 | 41.1 % |

- The string area is **already deduplicated**: 1,203 references point to 1,201 distinct strings.
  About 5.6 KB are keys and names, about 6.1 KB are distinct values, and the rest are templates.
- Per type, values repeat a lot: family 7 distinct values for 59 facts, category 3 for 103, period
  7 for 118, bond type 2 for 155. The maximum is 139 distinct values (molar mass). **Every relation
  has fewer than 256 distinct values.**
- 2,379 answerable facts (`bench/suites/chemie/facts.tsv`) → **12.23 B per fact**.

**Decision**: the savings must come from the structure (17 KB, 57 %), not from the strings. The
per-relation local IDs of research 03 §5 fit exactly: one byte per fact instead of eight.

**Rationale**: research 02 §2 and 03 §4 say the dictionary dominates in large graphs. In this small
table the 8-byte records and the 12-byte objects dominate; the strings are already stored once. So
the first target is the structure, and string coding (R6) is a reserve.

## R2 · Topic layout on disk

**Decision**: one directory per topic under `topics/`:

```text
topics/<id>/
├── topic.toml        # configuration: id, schema version, file list, budget, model-alphabet config
├── schema.toml       # classes, relations, value types, rules, views (templates), texts, legacy letters
├── objects.tsv       # key, name, class, source  (one or more object files)
├── facts/*.tsv       # subject, relation, value, source  (one fact per line)
├── prepare.py        # optional: reproducible preparation step that writes facts/generated/*.tsv
├── compat/           # optional: frozen reference answers of a predecessor (chemistry: UTFT v1)
└── proposals/        # optional: LLM proposals waiting for review (US4)
```

The formats are in [contracts/topic-format.md](contracts/topic-format.md).

**Rationale**: FR-001 says a topic is data only. A top-level `topics/` keeps topics apart from the
training data of spec 003–006 (`training/data/`), which spec 009 will later derive from the schema.
TOML and TSV are what the project already uses (`hybrid.toml`, `facts/*.tsv`), so authors know
them and every error can name a file and a line (FR-004).

**Alternatives considered**: one big TOML per topic (too long for 2,000+ facts, bad line numbers);
RDF/Turtle or OWL (needs a parser and namespaces nobody needs here; research 03 §3 says OWL
reasoning is out of reach anyway); JSON (no comments).

## R3 · Chemistry: where the chemistry calculations go

**Decision**: `topics/chemie/prepare.py` runs the existing spec 006 fact generator
(`ultratiny.factgen.build`, unchanged) and writes its objects and values as plain triples to
`topics/chemie/objects.tsv` and `topics/chemie/facts/generated/*.tsv`. The output is committed.
CI reruns `prepare.py` and fails if the committed files differ. The compiler never imports `factgen`
or `periodic`.

Hand-curated chemistry additions that are new in 008 (normalised relations such as the group
number, rules, views for the new reverse questions) live in `schema.toml` and
`topics/chemie/facts/*.tsv`, not in the generated files.

**Rationale**:
- FR-008 allows a preparation step stored with the topic and forbids chemistry in the compiler.
- `factgen` is still the data generator for training `chemie-hybrid` (T044 in spec 006). It has to
  stay until spec 009 generates training data from the schema. Rewriting the chemistry rules a
  second time would create two sources of truth.
- Committed generated files make the topic reviewable as data and let the compiler run without
  the preparation step (SC-008: build < 1 min).

**Alternatives considered**:
- Express ions, ionic formulas and molar masses as compiler rules: needs arithmetic and formula
  parsing in the rule language, which is chemistry in disguise.
- Delete `factgen`: breaks the 006 training pipeline before spec 009 replaces it.

## R4 · Schema model: relations, directions and views

**Decision**: the schema separates **what is stored** from **how it is asked**.

- **Relation** (stored): name, subject class(es), value type, cardinality forward (`one`/`many`),
  and optionally `reverse = "one" | "many"`. A value is either a literal (text, integer, decimal,
  enum) or a reference to an object.
- **View** (asked): one way to ask the image, with its own template, "not applicable" text and
  list continuation text. A view has a direction:
  - `forward` of a relation: key = subject key, answer = the value(s);
  - `reverse` of a relation: key = a value, answer = the subject(s);
  - `self`: key = object key, answer uses only `{name}` and `{key}` (006 types `S`, `s`, `R`, `f`);
  - `profile`: like `self`, but the template uses values of other relations of the same object
    (006 type `E`).
- **Legacy letter**: `letter = "O"` on a view maps a 006 function-output type letter to that view
  (FR-015). Letters are optional; new views have none.

The 26 types of 006 map to views as follows (full list in
[data-model.md](data-model.md#legacy-mapping-for-chemistry)): 20 forward views, 1 reverse view
(`o` → reverse of `ordnungszahl`), 4 self views (`S`, `s`, `R`, `f`; for `s` and `f` the model
already sends the key, so they need no reverse lookup) and 1 profile view (`E`).

**Rationale**: the same stored relation can be asked several ways (006 `S` and `s` both look up an
element by its symbol and differ only in the sentence). Keeping templates on views means relations
stay topic-neutral data and every direction has its own sentence (FR-002). Research 02 §5 (template
plus slots) supports a fixed set of views as the unit the model, and later spec 009, chooses from.

**Alternatives considered**: templates on relations (cannot express `S` vs `s`, or two sentences for
one direction); one view per relation implicitly (no place for profile answers).

## R5 · Knowledge image layout (UTKI v1)

**Decision**: a new format "UTKI" (UltraTiny Knowledge Image) version 1 replaces UTFT v1. The
layout is in [contracts/image-format.md](contracts/image-format.md). Core ideas:

1. **16-bit offsets everywhere.** The image is ≤ 58,982 B, so every offset fits in a `u16`. That
   halves every pointer compared with UTFT v1.
2. **Objects grouped by class, in a declared order** (e.g. elements by atomic number). An object is
   4 B (key string, name string). The class is given by its position. A separate **key index**
   (2 B per object, sorted by key bytes) gives binary search by key.
3. **Relation-local value IDs** (research 03 §5): every relation has its own sorted value table
   (2 B per distinct value: a string offset, or an object number for references).
4. **Single-valued forward direction = column**: one byte per subject of the class (value ID, or
   `0xFF` = no value). With fewer than 255 distinct values per relation (R1), one byte suffices; the
   format allows 2-byte columns for relations with more values.
5. **Multi-valued directions (forward `many`, every reverse) = posting lists**: an offset table
   (`u16` per entry + 1) into a list of 1-byte IDs (subject positions within the class, or value
   IDs), in the declared order.
6. **Reverse lookup**: binary search of the key in the relation's sorted value table → value ID →
   its posting list. No scan over all facts (FR-012).
7. **Views** (12 B each) carry the direction, relation, class mask, template, "not applicable" and
   continuation strings, and the legacy letter.
8. **Topic texts in the image**: "unknown", generic "not applicable", the fallback separator `– `,
   and the list words (`, ` and ` und `).

Estimated size for chemistry (2,379 facts of 006 plus R9): strings ≈ 12.4 KB, objects and key index
≈ 2.0 KB, columns ≈ 3.0 KB, value tables ≈ 1.6 KB, posting lists ≈ 2.0 KB, views and header
≈ 0.6 KB → **≈ 21.6 KB** (UTFT v1: 29.1 KB).

**Rationale**: the measured structure (R1) shrinks from 17 KB to about 8.6 KB without any entropy
coding, the lookup stays a few binary searches with fixed-size records, and the C reader stays
simple (Constitution V). Research 03 §5 reports up to 2× from predicate-local IDs on large graphs;
here the gain is larger because UTFT v1 spent 8 B per record.

**Alternatives considered**: keep UTFT v1 and add a reverse index (still 8 B per fact, chemistry
kinds stay in the format); a generic succinct structure (k2-tree, HDT bitmaps), which research 03
§4–6 shows on million-triple graphs and which is complex to read on the ESP8266 for no gain at
2,000 facts; memory-mapping the image (the 1 MB mapped window is full with firmware and model;
006 placed the table outside it on purpose).

## R6 · String coding (Huffman, front coding)

**Decision**: not in UTKI v1. Strings stay plain NUL-terminated UTF-8, stored once. The build
report shows the string share so the decision can be revisited.

**Rationale**: with R5 the estimate is ≈ 7.0–7.5 B per answerable fact (R9), below the 8.56 B
target of SC-003, so the target does not need it. Huffman saves about 30–35 % of the strings
(research 02 §2), roughly 4 KB here, but needs a decoder, a code table in RAM or flash and
bit-level reads on every printed character. That is real complexity for a margin we do not need
yet (Constitution V).

**Fallback**: if the measured image misses SC-003, front coding of the sorted key and value tables
comes first (cheap to decode), then Huffman, each with a measurement in `measurements.md`.

## R7 · Rendering lists (multi-valued answers)

**Decision**: a multi-valued answer renders as `item1, item2 und item3` with the topic's list words.
If the whole answer would exceed 100 B, the renderer takes the longest prefix of items such that
`prefix + items + continuation` fits in 100 B, where the continuation is the view's `more` text with
the remaining count (e.g. `und 5 weitere`). At least one item is always printed (the build checks
that every list's first item plus continuation fits). The algorithm is fixed in
[contracts/query.md](contracts/query.md#lists) so C and Python agree byte for byte.

**Rationale**: spec US2 scenario 5; no value is cut off; the 100-byte limit is the 006 answer limit.
Counting first and printing second needs no RAM buffer: the posting list is read twice.

## R8 · Rules at build time

**Decision**: three rule kinds, run in Python at build time only (FR-006, research 03 §1–3):

| Kind | Meaning | Example |
|------|---------|---------|
| `class` | if relation `R` of a subject has value `v` (or a number in `[lo, hi]`), and the subject is not in `except`, then add `(subject, R2, value)` | `gruppe_nr = 1`, except `H` → `familie = Alkalimetalle` |
| `chain` | `(s, R1, o)` and `(o, R2, v)` with `o` an object → `(s, R3, v)` | chess: piece → kind → description |
| `table` | value of `R1` maps through a topic table to a value of `R2` | `gruppe_nr` 13 → `hauptgruppe` 3 |

The rules run in declaration order, repeated until no new fact appears (fixpoint). Limits: at most
65,535 facts in total and at most 32 rounds; beyond that the build stops (edge case "rules that feed
each other"). A derived fact equal to an explicit fact is dropped silently; a different value for a
single-valued relation stops the build and names both sources (FR-007). Every derived fact keeps
its provenance (rule id and input facts) in `build.json`, not on the board.

**Rationale**: these three kinds cover the roadmap example ("Gruppe 1 → Alkalimetall"), the chess
rule and the group-to-main-group mapping. Anything more (arithmetic, formula parsing) belongs in a
topic's preparation step (R3). A fixpoint over three kinds of simple rules is a few dozen lines of
Python and fully deterministic.

**Alternatives considered**: Datalog or OWL 2 RL as rule language (much more than needed; research
03 §3); rules on the board (research 03 §1: does not fit 35 KB).

## R9 · New answerable facts in chemistry (SC-002)

**Decision**: reverse views for relations where a school question exists, plus rule-derived facts:

| New view | Example question | New answers (estimate) |
|----------|------------------|------------------------|
| reverse `protonen` / `elektronen` | Welches Element hat 17 Protonen? | 118 + 118 |
| reverse `atommasse` | Welches Element hat die Atommasse 35,45 u? | 114 |
| reverse `molare_masse` | Welcher Stoff hat die molare Masse 18,0 g/mol? | 139 |
| reverse `neutronen` | Welches Element hat 20 Neutronen? | 80 |
| reverse `gruppe_nr`, `periode` | Welche Elemente gehören zur Gruppe 1? | 18 + 7 |
| reverse `familie`, `kategorie`, `zustand` | Welche Elemente sind Halogene? | 7 + 3 + 3 |
| reverse `aussenelektronen`, `schalen`, `wertigkeit` | Welche Elemente haben 6 Außenelektronen? | 8 + 7 + 4 |
| reverse `bindung`, `saeure_base` | Welche Stoffe haben eine Ionenbindung? | 2 + 7 |
| forward `hauptgruppe` (table rule) | In welcher Hauptgruppe steht Natrium? | 44 |
| forward `familie` (class rules, fills gaps) | Zu welcher Familie gehört Polonium? | ≈ 10 |

Total ≈ 2,379 + ≈ 690 ≈ **3,070 answerable facts** (target ≥ 2,855). With ≈ 21.6 KB that is
≈ 7.0 B per fact (target ≤ 8.56 B).

An answerable fact is counted as a distinct (view, key) whose lookup outcome is "fact"; this is the
definition of facts.tsv in spec 007 (one row per type × key) carried over to views.

**Rationale**: these questions appear in school short tests and need no new source data. The class
rules for families also check the Wikidata family values (a contradiction stops the build), which
is a free data check.

**Risk**: if the real image is larger than estimated, the reverse views with the least school use
(atomic mass, molar mass) go first; the count still meets 2,855 without them (≈ 2,817 + rules ≈
2,870). Measured in T-tasks and recorded in `measurements.md`.

## R10 · Compatibility with spec 006 (SC-001, FR-015)

**Decision**:

1. **Freeze the oracle before replacing the code.** A one-off export renders every (type letter,
   key) pair through UTFT v1: every applicable pair, every not-applicable pair, one unknown key per
   type, and the missing-table case. The result is committed as
   `topics/chemie/compat/utft1_answers.tsv` (type, key, outcome, answer bytes as UTF-8).
2. **Compat check.** `ut knowledge check --compat` renders the same queries through the new image
   via the legacy letters and compares byte for byte. Differences must be listed in
   `topics/chemie/compat/changes.tsv` (type, key, old, new, reason, `reviewed = yes`). Unlisted
   differences fail the check (CI).
3. **Remove UTFT v1.** After the check passes, `facts.c`, `utiny_facts.h` and `facttable.py` are
   replaced; there is one code path (FR-010, Constitution V).
4. **Same console behaviour.** The function-output state machine of 006 stays as it is
   (prefix printed when the letter arrives, key collected, rest printed at the end, the same
   fallbacks). Only the lookup behind it changes.

Expected intended changes: answers that were "not applicable" in 006 and now have a value through a
rule (e.g. families filled in by class rules). Each is reviewed.

**Rationale**: an oracle file makes the compat check independent of the old code, so the old code
can go. Spec 006 golden cases (`printed`) stay valid because the bytes stay the same.

## R11 · Topic identity and model mismatch (US3 scenario 3)

**Decision**: the image header holds the topic id (≤ 15 bytes, NUL-padded) and the schema version.
The exporter writes `"topic": "<id>"` into the model meta when the config names a topic
(`topic = "chemie"`). At boot, if the model has `<fn>` and its meta has a `topic`, the firmware
compares it with the image; on a mismatch it treats the image as missing and prints
`Wissen: falsches Thema (Bild schach, Modell chemie)`. Models without a `topic` meta field (all
models exported before 008) are not checked, and `/info` says `Thema nicht geprüft`.

**Rationale**: the meta JSON already exists and the console already reads fields from it
(`meta_str`); a new field needs no format change (UTNY stays v2). Spec FR-019 keeps the 006 model:
`chemie-hybrid` gets the field if it is exported after 008, and works unchecked if it is exported
before.

**Alternatives considered**: storing the image hash in the model (breaks every image rebuild);
comparing legacy letters (proves nothing about the topic).

## R12 · Direct query command (FR-016)

**Decision**: a console command `/wissen` (German, like `/hilfe`, `/info`, `/modus`):

| Input | Meaning |
|-------|---------|
| `/wissen` | topic id, schema version, number of facts and the list of views (name, direction, letter) |
| `/wissen O Cu` | legacy letter + key, exactly like the function output `<fn>OCu` |
| `/wissen ordnungszahl Cu` | view by name + key |
| `/wissen ordnungszahl< 29` | reverse view by relation name + `<` |

The key is the rest of the line after the first space following the view, so keys and reverse
values with spaces work. With `/trace an` the command also prints the lookup time in µs (for
SC-005). The grammar is in [contracts/query.md](contracts/query.md#direct-query-command).

**Rationale**: makes images testable without a model (second topic, new reverse views, the demo of
FR-021) and gives the board tools a way to time each lookup.

## R13 · Benchmark integration (FR-020)

**Decision**:

- Two new image-only KPIs, computed from the image alone (deterministic, threshold 0):
  **F7** answerable facts in the image (↑) and **R5** image bytes per answerable fact (↓). R3 keeps
  its meaning (image size); R4 keeps the 007 definition ((R2 + R3) / F6).
- `tools/bench.py image --facts <image>` writes an image-only result JSON. It runs once on the UTFT
  v1 table before the old code is removed (`bench/results/chemie-hybrid-utft1_chemie_image.json`),
  so the report can show 006 as predecessor.
- `tools/bench_export_facts.py --topic topics/chemie` exports `facts.tsv` from the compiled topic,
  using only views with a legacy letter (the only ones a model can be asked). Expected: identical to
  the pinned file except for the reviewed changes of R10. If it differs, the suite version is bumped
  and the reason is recorded.
- `bench.py pc/board --facts` takes `.utki` files; identity checks read the new header.

**Rationale**: F6 and R4 stay comparable with the baseline (FR-019 expects F6 at the 006 level);
the coverage gain shows in F7 and R5 without changing what F6 means.

## R14 · LLM fact proposals (US4, FR-022)

**Decision**: `ut knowledge propose --topic topics/chemie --model <llm>` uses the existing Spark LLM
client (as `training/tools/shorten_llm.py`) to list gaps (subjects of a relation's class without a
value) and ask for a value and a source. It writes `topics/<id>/proposals/<date>.tsv` with
columns `subject, relation, value, source, reason, accepted`. `ut knowledge accept <file>` copies
rows with `accepted = yes` into `facts/accepted.tsv`. The build rejects any fact whose source starts
with `llm:`; a person must enter the real source (e.g. `wikidata:Q…`) when accepting.

**Rationale**: no fact value comes from a language model without a person's check (006 FR-005,
spec FR-022). Proposals never touch fact files directly.

## R15 · Budgets and timing on the board

**Decision**:

- Image ≤ 58,982 B in the 006 fact area (0x100000, 64 KB); checked by the builder,
  `tools/budget_report.py` and `make nodemcu-flash-facts`.
- Static RAM of the knowledge engine ≤ 1 KB: handle with header fields (~64 B), the 128 B read
  buffer of 006 and the console's 48 B key buffer. No heap.
- Lookup time: binary search of the key index (≤ 9 steps for 323 objects, each one aligned 128 B
  read when not cached), one column or posting-list read, string reads while printing. Estimate
  < 3 ms per query on the ESP8266 (`ESP.flashRead` ≈ 10–30 µs per small read); target ≤ 50 ms
  (SC-005), measured with `/wissen` under `/trace an` for every golden query.
- Firmware growth: `knowledge.c` replaces `facts.c`; expected +2 KB at most (budget 360,448 B,
  today 297,280 B).

**Rationale**: the same flash access as 006 (read callback, aligned, outside the mapped window);
only the structure behind it changes.
