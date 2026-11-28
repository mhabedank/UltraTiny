# Feature Specification: Knowledge Compiler (Topic-Independent)

**Feature Branch**: `claude/adoring-cannon-2dpdv4`

**Created**: 2026-11-28

**Status**: Draft

**Input**: User description: "Schritt 3 aus specs/ROADMAP.md (Spec 008: Wissens-Compiler, themenunabhängig). Lies vorher specs/ROADMAP.md (Entscheidungen, Regeln, KPI-Entwurf), die dort unter „Grundlage“ verlinkten Befunde in research/2026-11-architektur/ und specs/006-hybrid-chemielehrer/ (vorhandene Testmengen und Messungen)." (The command was given as "Schritt 1 / Spec 007"; Spec 007 is already done, and the user chose step 3 instead.)

## Background

Spec 006 moved facts out of the network: the model outputs a question type and an object key,
and the board looks the value up in a verified fact table (UTFT v1) and prints it in an answer
template. That works, but the fact table is built for chemistry only:

- **Chemistry is built into code and format.** The object kinds (element, compound, acid/base,
  reaction, test reaction) are a fixed bit mask in the file format. The rules that compute facts
  (atomic structure, ions, ionic formulas, molar masses, bond type) live in the Python builder.
  The "I don't know" texts are fixed strings in the C runtime and the Python reference. Adding a
  second topic would mean changing the builder, the format and the runtime.
- **Facts are stored as finished strings per object and type.** 26 question types (one letter
  each, at most 52), 323 objects, 1,597 value records. The 29,100 B table answers 2,379 facts (the
  benchmark's `facts.tsv`), about 12.2 B per fact. Values that repeat across objects (group
  numbers, families, states, units) are stored again for every object.
- **One direction only, mostly.** Reverse questions exist for a few types (symbol, atomic number,
  formula) and run as a linear scan. Questions like "Welche Elemente gehören zur Gruppe 1?" or
  "Welches Element hat 6 Außenelektronen?" have no answer, although the facts are in the table.

The roadmap (step 3) turns this into a general kit: a topic goes in, a knowledge image comes out.
The research behind it:

- A symbolic store with pattern queries runs on the ESP8266 itself; the triple structure costs
  only a few bytes per fact, and the strings (names, values, texts) dominate the size; Huffman
  coding of the strings saved about 30–35 % ([02 §1–2](../../research/2026-11-architektur/02-domaenenmodell.md)).
- Rule engines and reasoners do not fit a 35 KB RAM budget; derived facts must be computed at
  build time and shipped as plain facts ([03 §1–3](../../research/2026-11-architektur/03-baukasten-potenzial.md)).
- The string dictionary is the main storage cost; IDs local to each relation and separate coding
  of the parts saved up to 2× over standard encodings ([03 §4–6](../../research/2026-11-architektur/03-baukasten-potenzial.md)).
- All these numbers come from graphs with millions of facts; for a knowledge base of a few
  thousand facts the real size has to be measured directly
  ([02 Vorbehalte](../../research/2026-11-architektur/02-domaenenmodell.md#vorbehalte),
  [03 Vorbehalte](../../research/2026-11-architektur/03-baukasten-potenzial.md#vorbehalte)).

Spec 007 provides the yardstick: F6 (answerable facts), R3 (flash for knowledge) and R4 (bytes
per fact), measured against the `chemie-nodemcu` baseline and the predecessor step.

## Clarifications

### Session 2026-11-28

- Q: Does spec 008 train a new chemistry model so that new facts are reachable by questions? → A: No.
  `chemie-hybrid` from spec 006 runs unchanged with the new image; new facts are tested through the
  direct query command; the question side is spec 009 (FR-019).
- Q: Which second mini-topic tests topic independence? → A: Chess pieces, facts written by the
  project (FR-017).

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Compile the chemistry topic into a knowledge image without losing an answer (Priority: P1)

The developer describes the chemistry topic as data: a schema (which kinds of things exist,
which relations connect them, which value types they have, how answers are phrased) and fact
files (one fact per line: subject, relation, value, source). One build command turns this into a
knowledge image. The board loads the image instead of the 006 fact table and answers every fact
question exactly as before, while the image is smaller per fact.

**Why this priority**: Everything later (specs 009, 010, the second topic) builds on this image.
It must not make the chemistry teacher worse.

**Independent Test**: Build the chemistry image, then ask every question the 006 table answers
(every type code with every key) on the PC reference and on the board; compare the answer texts
with the 006 table byte for byte.

**Acceptance Scenarios**:

1. **Given** the chemistry topic as schema and fact files, **When** the developer runs the build
   command, **Then** it produces one knowledge image and a build report (counts of objects,
   relations, explicit and derived facts, answerable facts, image size split into dictionary,
   structure and templates, bytes per fact).
2. **Given** the new image and the model output "atomic number of Cu" (type `O`, key `Cu`),
   **When** the board answers, **Then** it prints "Die Ordnungszahl von Kupfer ist 29." exactly as
   with the 006 table.
3. **Given** any (type code, key) pair that the 006 table answers, **When** it is asked with the new
   image, **Then** the answer text is identical, or the pair is on a reviewed list of intended
   changes.
4. **Given** a key that the image does not know, or a relation that does not apply to the object,
   **When** it is asked, **Then** the board prints the topic's "unknown" or "not applicable" text,
   never a value.
5. **Given** the same source files, **When** the build runs twice, **Then** both images are
   byte-identical.
6. **Given** a fact file with an error (unknown relation, value of the wrong type, a second value
   for a single-valued relation, missing source), **When** the build runs, **Then** it stops and
   names the file, the line and the rule that failed.

---

### User Story 2 - Facts in both directions and simple rules are computed when the image is built (Priority: P2)

The topic author declares in the schema which relations work in both directions (element →
symbol and symbol → element; element → group and group → elements) and writes simple rules
("group 1 and not hydrogen → alkali metal"). The build computes every derived fact and stores it
like an explicit fact. The board only looks facts up; it never reasons.

**Why this priority**: This is where new answerable facts come from without new source data, and
it removes the chemistry rules from the code (roadmap rule 6).

**Independent Test**: Build the image and count answerable facts per relation and direction;
check every derived fact against its rule and its source facts; ask reverse questions on the PC
and on the board.

**Acceptance Scenarios**:

1. **Given** a two-way relation "group", **When** the image is built, **Then** the reverse question
   "which elements are in group 1" is answerable and lists the elements in a fixed order.
2. **Given** a reverse relation declared single-valued (symbol → element), **When** two objects
   share the value, **Then** the build stops and names both objects.
3. **Given** the rule "group 1 and not H → family alkali metal", **When** the image is built,
   **Then** each matching element gets the fact, marked as derived with the rule and the facts it
   came from.
4. **Given** a derived fact that contradicts an explicit fact, **When** the image is built, **Then**
   the build stops and names both.
5. **Given** a multi-valued answer longer than the answer limit, **When** it is asked, **Then** the
   board prints the first values in the fixed order and a fixed continuation text from the
   template (e.g. "und 3 weitere"), never a cut-off value.

---

### User Story 3 - A second mini-topic compiles and answers without a code change (Priority: P2)

The developer adds a tiny second topic (about 30 facts) next to chemistry: its own schema, fact
files and answer templates. It compiles into its own image, and that image answers its questions
on the PC and on the board without changing the compiler, the image format, the query engine or
the firmware.

**Why this priority**: The roadmap demands topic independence and tests it in every spec with a
tiny second topic. Without this test, chemistry would creep back into code.

**Independent Test**: Add the topic in a change that touches only topic data and its test cases;
build its image; run its competency questions as direct queries on the PC and on the board.

**Acceptance Scenarios**:

1. **Given** the second topic, **When** it is built, **Then** the change set contains no edits to
   the compiler, the format description, the query engine or the firmware.
2. **Given** its image on the board, **When** each of its competency questions is sent as a direct
   query on the console, **Then** the board prints the expected answer, and the PC reference
   prints the same bytes.
3. **Given** the chemistry model on the board and the second topic's image, **When** the board
   starts, **Then** it reports that image and model belong to different topics, and fact
   questions get the "knowledge missing" text instead of answers from the wrong topic.

---

### User Story 4 - A large language model proposes missing facts, a person decides (Priority: P3)

The topic author lets a large language model on the PC or the DGX Spark look for gaps (an
element without a melting point, a compound without a bond type) and propose facts. The
proposals land in a review list. Only rows a person accepts, each with a source, enter the fact
files.

**Why this priority**: Optional in the roadmap. It speeds up filling a topic, but no fact may come
from a language model without a check (spec 006 FR-005).

**Independent Test**: Run the proposal step on the chemistry topic; check that the fact files do
not change until the review list is filled in, and that accepted rows carry a source.

**Acceptance Scenarios**:

1. **Given** the proposal step, **When** it runs, **Then** it writes a review list (subject,
   relation, proposed value, proposed source, reason) and changes no fact file.
2. **Given** a review list with accepted and rejected rows, **When** it is applied, **Then** only
   accepted rows with a source of an allowed kind enter the fact files.

---

### Edge Cases

- **Case-sensitive keys:** `Co` (cobalt), `CO` (carbon monoxide) and `N` vs `Na` remain different
  keys, as in spec 006 FR-012.
- **The same name in two classes:** a name may exist once per class; a key must be unique across the
  whole topic.
- **Rules that feed each other:** rules run until no new fact appears; a rule set that never stops
  growing (more facts than a fixed limit) stops the build.
- **Answer longer than the limit:** single values that make an answer exceed the answer limit stop
  the build (as in 006); multi-valued answers are shortened as in US2 scenario 5.
- **Image over budget:** the build stops when the image exceeds the fact area budget.
- **Image missing or corrupt:** the board reports it at start; model-written answers (greetings,
  explanations, refusals) keep working, and fact questions get a topic-neutral "knowledge missing"
  text from the firmware.
- **Image from another topic or schema version than the model expects:** treated like a missing
  image (US3 scenario 3), with a clear line at start.
- **A type code the model emits that the image does not map:** answered with the topic's "unknown"
  text.
- **Values with characters outside the model alphabet** (`→`, `°`, `²`): allowed in values and
  templates, which only the board prints; keys and names the model reads or writes must use the
  model alphabet.

## Requirements *(mandatory)*

### Functional Requirements

**Topic description**

- **FR-001**: A topic MUST consist only of data: a schema file, fact files and a configuration.
  Adding or changing a topic MUST NOT require a change to the compiler, the image format, the query
  engine or the firmware.
- **FR-002**: The schema MUST declare: the concept classes (kinds of objects); the relations, each
  with its subject class, its value type, whether it is single- or multi-valued and whether it can
  be asked in reverse (with the reverse's own cardinality); the value types (text, whole number,
  decimal number with fixed decimals and unit, value from a fixed list, reference to an object);
  for each relation and direction the answer template, the "not applicable" text and the
  continuation text for long lists; the topic's "unknown" text; and competency questions (example
  questions with expected answers) for every relation.
- **FR-003**: Facts MUST be stored as triples (subject, relation, value) with a source per fact. A
  source MUST have a prefix listed as allowed in `DATA_LICENSES.md`.
- **FR-004**: The build MUST validate every fact and stop on the first class of error, naming file,
  line and rule: unknown class or relation, value of the wrong type, a second value for a
  single-valued relation, duplicate facts, missing or disallowed source, characters outside the
  model alphabet in keys and names, and length limits (key ≤ 12, name ≤ 40, value ≤ 60, rendered
  answer ≤ 100 bytes, as in spec 006).

**Derived facts**

- **FR-005**: For every relation declared as two-way, the build MUST compute the reverse direction.
  A reverse declared single-valued MUST map each value to exactly one subject, or the build stops.
- **FR-006**: The build MUST support a small fixed set of rule kinds, declared in the topic data:
  (a) class rule: if a relation has a given value or a value in a given range (optionally with
  exceptions), then add a given fact; (b) chain: a relation followed by another gives a third;
  (c) value table: a value of one relation maps to a value of another via a table in the topic. The
  build MUST apply the rules until no new fact appears and mark each derived fact with its rule and
  the facts it came from.
- **FR-007**: A derived fact that contradicts an explicit fact, or two rules that derive different
  values for a single-valued relation, MUST stop the build.
- **FR-008**: Topic-specific calculations that the rule kinds cannot express (in chemistry: ionic
  formulas, molar masses, electron arrangement) MUST NOT live in the compiler. They MAY be a
  reproducible preparation step stored with the topic that writes ordinary fact files with source
  `computed`; the compiler treats them like any other fact file.
- **FR-009**: No reasoning MUST happen on the board: the image contains every answerable fact, and
  the board only looks facts up.

**Knowledge image and query engine**

- **FR-010**: The build MUST produce one knowledge image per topic. It replaces the 006 fact table
  (UTFT v1) on the board; there is one code path for knowledge images, and the chemistry table is
  rebuilt from the chemistry topic.
- **FR-011**: The image MUST start with a magic number, a format version, a topic identifier, a
  schema version and a checksum, and MUST be checked at start like the 006 table. Any layout change
  bumps the format version (Constitution IV).
- **FR-012**: The image MUST store every distinct string (key, name, value, template part) once and
  MUST contain an index for each relation and direction, so that forward and reverse questions are
  answered without reading every fact. The build report MUST show the size of the dictionary, the
  structure and the templates separately.
- **FR-013**: The image MUST contain all topic texts (templates, "unknown", "not applicable",
  continuation texts). The firmware and the Python reference MUST contain no topic-specific text;
  the only built-in text is a topic-neutral "knowledge missing" message.
- **FR-014**: The query engine on the board and the Python reference MUST render byte-identical
  answers for the same image and query (Constitution III). Each topic build MUST produce golden
  cases that cover every relation in each direction, unknown keys, not-applicable cases and
  shortened lists; host tests and the board check run them.
- **FR-015**: The model interface of spec 006 (function output = one type letter plus a key,
  [contracts/function-output.md](../006-hybrid-chemielehrer/contracts/function-output.md)) MUST
  keep working: the schema maps each type letter to a relation and direction. For the chemistry
  topic, every (type, key) pair that the 006 table answers MUST give the same answer text, except
  for pairs on a reviewed list of intended changes.
- **FR-016**: The board console MUST offer a direct query command (relation or type letter plus
  key) that answers from the image without the model, so that an image can be tested on the board
  without a model trained for its topic.

**Second topic**

- **FR-017**: The project MUST include a second mini-topic of about 30 explicit facts with at least
  2 concept classes, 3 relations, one two-way relation, one multi-valued relation and one rule.
  Topic: **chess pieces**: classes such as piece and square or colour; relations such as how a
  piece moves, its value, its count per side and its starting squares (multi-valued); a rule such
  as "value 3 → minor piece". The facts are written by the project (source `own`), so there is no
  licence question.
- **FR-018**: The second topic MUST compile, pass its golden cases on the PC and on the board, and
  answer all its competency questions as direct queries, in a change set that touches only topic
  data and topic test cases (SC-003).

**Model, measurement and demo**

- **FR-019**: This step trains no new model. The 006 model `chemie-hybrid` runs unchanged with the
  new chemistry image. Newly answerable facts (new reverse directions, rule results) are reachable
  on the board through the direct query command (FR-016); making them reachable by free questions,
  including question forms generated from the schema, is spec 009. The end-to-end F6 of spec 007
  is therefore expected to stay at the 006 level; the gain is measured as image coverage (SC-002).
- **FR-020**: The benchmark (spec 007) MUST measure the new image: the fact list `facts.tsv` of the
  chemistry suite is exported from the compiled topic; R3, R4 and the image's own bytes per
  answerable fact (R3 divided by answerable facts) are reported. The result goes as JSON to
  `bench/results/` and the report compares it with the baseline and with spec 006.
- **FR-021**: A fixed demo script of 10–15 chemistry items MUST run on the board next to
  `chemie-nodemcu`, with both answers side by side (roadmap rule 2): questions the 006 model
  understands, answered from the new image, plus at least 3 new reverse queries and 2 rule results
  sent as direct queries.
- **FR-022**: Optional fact proposals by a large language model (US4) MUST go to a review list;
  only rows a person accepts and that carry an allowed source MAY enter the fact files. No fact
  value MUST come from a language model without that review.

### Key Entities

- **Topic**: A named body of knowledge (chemistry, the second mini-topic) given as schema, fact
  files and configuration. It has an identifier and a schema version.
- **Schema**: The description of a topic: concept classes, relations, value types, rules, answer
  templates, topic texts, competency questions and the mapping from model type letters to
  relations.
- **Concept class**: A kind of object in a topic (in chemistry e.g. element, compound, reaction).
- **Relation**: A named property or link with subject class, value type, cardinality and optional
  reverse direction.
- **Fact (triple)**: subject, relation, value and source. Explicit (from a fact file) or derived
  (from a rule or a reverse direction, with its origin recorded).
- **Rule**: A declaration of one of the fixed rule kinds (class rule, chain, value table) that
  derives facts at build time.
- **Competency question**: An example question for a relation with its expected answer; used for
  tests, golden cases and the benchmark.
- **Answer template**: A short German sentence with slots, per relation and direction, plus its
  "not applicable" and continuation texts.
- **Knowledge image**: The compiled, versioned, checksummed file on the board's flash that holds
  the dictionary, the facts and an index per relation and direction.
- **Query**: relation or type letter plus key, from the model or from the console's direct query
  command; the answer is the rendered template.
- **Fact proposal**: A fact suggested by a large language model, with a proposed source, waiting
  for a person's decision.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: For the chemistry topic, 100 % of the (type, key) pairs answered by the 006 table give
  the same answer text with the new image, apart from a reviewed list of intended changes; PC and
  board answers are identical for 100 % of the golden cases.
- **SC-002**: The chemistry image answers at least **20 % more facts** than the 006 table (at least
  2,855 answerable facts against 2,379), counted as (object, relation, direction) with an answer.
- **SC-003**: The chemistry image needs at most **70 %** of the 006 table's bytes per answerable fact
  (at most 8.56 B against 29,100 B / 2,379 = 12.23 B), and the image stays within the fact area budget of 58,982 B.
- **SC-004**: The second topic compiles and answers 100 % of its competency questions correctly on
  the PC and on the board, in a change set with zero changed lines in the compiler, the image format
  description, the query engine and the firmware.
- **SC-005**: On the board, every query from the golden cases is answered within **50 ms** of lookup
  time; the first answer character still appears within 2 s and answers still print at ≥ 5
  characters/s.
- **SC-006**: Board budgets hold with ≥ 10 % headroom: firmware ≤ 360,448 B; the knowledge engine
  uses at most 1 KB of static RAM and no heap at runtime; the model arena is unchanged.
- **SC-007**: Every fact in the image traces back to a source fact file line or to a rule plus its
  input facts (100 %), and two builds from the same sources give byte-identical images.
- **SC-008**: Building the chemistry topic, from source files to image and report, takes under one
  minute on a CPU-only machine, so authors can iterate on facts quickly.

## Assumptions

- Spec 007 is done; its benchmark, suites and baseline are used as they are. Image KPIs (F6 by
  image, R3, R4) are deterministic, so their noise threshold is zero; model KPIs keep the 3-seed rule.
- Spec 006 is finished first (roadmap decision "Spec 006: erst abschließen"). The compiler, the
  image and the second topic can be built before `chemie-hybrid` is trained (T044–T047), but the
  end-to-end board demo with the chemistry model needs it.
- The fact area stays where spec 006 put it (64 KB at flash offset 0x100000, file ≤ 58,982 B); the
  model area, the firmware area and the 1 MB mapped window are unchanged.
- The chemistry sources stay the same (Wikidata snapshot CC0, curated and sourced lists, the
  computed facts of spec 006); no new chemistry content is required beyond what reverse
  directions and rules derive.
- Answers stay single German sentences from templates. Grammar beyond fixed templates (cases,
  articles, combining several facts) is spec 010; understanding new phrasings, typos and inflected
  forms is spec 009.
- One knowledge image is on the board at a time; switching topics means flashing another image.
- Fuzzy indexes (HDC), graph embeddings and on-device rule engines are out of scope (roadmap
  "Ideenspeicher", research 03 §1–3).
