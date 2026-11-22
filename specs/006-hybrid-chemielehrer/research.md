# Research: Hybrid Chemistry Teacher on the NodeMCU

Phase 0 of [plan.md](plan.md). Each entry: decision, rationale, alternatives. Inputs: spec 006, feature 005
measurements (`specs/005-nodemcu-port/measurements.md`), research PR #4 (`specs/004-qualitaet`), and the
literature review of 2026-11-22 (function tokens à la Octopus v2, reversal curse, knowledge storage vs.
extraction).

## R1 – How the model signals a factual answer

**Decision**: A new special token `<fn>` (token id 5). For a factual question the model generates
`<fn>`, then **one type character**, then the **object key**, then `<eos>`:

```text
<bos>Welche Ordnungszahl hat Kupfer?<sep><fn>OCu<eos>
                                         │   │└┴── key "Cu"
                                         │   └──── type 'O' = atomic number
                                         └──────── function output follows
```

Everything else (greeting, explanation, refusal, "I don't know") is plain text, as today.

**Rationale**:
- Every generated character costs one forward pass of ~196 ms (5.1 chars/s). `<fn>` + type + "Cu" +
  `<eos>` is 5 steps (~1.0 s). The written answer "Kupfer hat die Ordnungszahl 29." would take 31 steps (~6 s).
- One type character instead of a mnemonic ("oz ") saves 2–3 steps. The type table maps the character to the type (R4).
- A special token can never be typed by the user, so a user question can't trigger function mode. It also
  keeps the alphabet's text characters unchanged.
- The vocabulary has 92 of 96 slots in use, so `<fn>` fits (93).

**Alternatives considered**:
- *A printable marker character (e.g. `§`)*: the user could type it, and it mixes text and control.
- *One special token per question type (Octopus v2 style)*: needs ~25 tokens, but only 4 slots are free.
- *Mnemonic type codes ("oz", "sym")*: easier to read, but 2–3 extra steps per answer.

## R2 – What the object key is: canonical key, or a copy of the user's words

**Decision**: The key is a canonical, case-sensitive identifier from the fact table:
- elements: the symbol (`Cu`, `N`, `Co`)
- compounds, acids and bases: the formula (`H2O`, `CO`, `Al2O3`, `HCl`)
- reactions and test reactions: a short lowercase slug (`knallgas`, `kalkwasser`), at most 12 characters

For **reverse questions**, the value the user gave is itself the key, copied from the question:
- "Welches Element hat die Ordnungszahl 29?" → `<fn>o29`
- "Was ist N?" → `<fn>sN`
- "Was ist CO?" → `<fn>fCO`

The firmware looks these up in reverse (value → object, R5).

**Rationale**:
- Copying from the question is what small transformers do most reliably, and it generalises to unseen combinations by construction.
- The only real "knowledge" left in the network is name → key (Kupfer → Cu, Wasser → H2O): about 300
  mappings. Every question type uses them, so a held-back type × object combination still has its
  name → key mapping trained through the other types. This attacks failure modes 2 and 3 in spec 006.
- Keys are short (≤ 5 chars for 95 % of objects), so answers stay fast. Case distinguishes Co/CO and N/Na (FR-012).

**Alternatives considered**:
- *Copy the name as typed ("Kupfer", "kupfers", "kupfa")*: longer and slower. The firmware would also need
  fuzzy matching for inflection and typos. The model handles typos better.
- *Numeric object ids*: arbitrary, so they can't be copied or shared between types, and are hard to learn.

## R3 – Where the fact table lives

**Decision**: A separate flash blob, **UTFT**, at flash offset **0x100000** (the first byte after the
memory-mapped megabyte), area **64 KB** (0x100000–0x10FFFF). The firmware reads it with the SDK
flash-read call (`ESP.flashRead`, 4-byte aligned offset, length and buffer) through a small read callback.
The host reads it from a file. Its own magic, version and CRC are checked at boot (FR-013). It is
flashed with `make nodemcu-flash-facts`.

**Rationale**:
- The mapped megabyte is full. The model area has 688,128 B, and with 10 % headroom the model may use
  619 KB. The current model needs 601 KB, which leaves ~18 KB, less than the table (estimated 25–45 KB, R6).
- Flash 0x100000–0x2FFFFF is unused in the 005 layout (the FS starts at flash 0x300000).
- A lookup happens once per answer and reads a few hundred bytes. SPI reads take microseconds, so they
  don't need to be memory-mapped. Constitution Principle II's "read in place" rule applies to weights, not to this table.
- A separate blob means facts can be fixed without retraining or reflashing the model, and the table
  has its own version for parity runs.

**Alternatives considered**:
- *Inside the model file (new section)*: too little headroom in the model area, and every fact fix would mean a new model file.
- *As `PROGMEM` data in the firmware*: firmware headroom is 59 KB, so it would fit. But every data
  version would need a firmware rebuild, and the host reference would need a second copy.
- *LittleFS file*: adds a file system library, flash-wear logic and ~10 KB of firmware for one read-only blob (Principle V).

## R4 – Question types and answer templates

**Decision**: 26 types, each with one type character, an answer template, an optional "not applicable"
text, and a direction (forward key = object; reverse key = value). Templates start with a constant
**prefix**, so the firmware can print the prefix as soon as the type character arrives, before the key is complete:

| Char | Type | Key | Template (prefix underlined in data-model.md) |
|------|------|-----|------------------------------------------------|
| `S` | symbol of element | symbol | `Das Symbol von {name} ist {key}.` |
| `s` | element of symbol (reverse) | symbol | `Das Symbol {key} steht für {name}.` |
| `O` | atomic number | symbol | `Die Ordnungszahl von {name} ist {v}.` |
| `o` | element of atomic number (reverse) | number | `Die Ordnungszahl {key} hat {name}.` |
| `M` | atomic mass | symbol | `Die Atommasse von {name} beträgt {v} u.` |
| `P` | period | symbol | `Die Periode von {name} ist die {v}.` |
| `G` | group (main group and IUPAC) | symbol | `Die Gruppe von {name}: {v}.` |
| `F` | family | symbol | `Die Elementfamilie von {name}: {v}.` |
| `K` | metal / non-metal / semimetal | symbol | `Zur Stoffart: {name} ist ein {v}.` |
| `Z` | state at 20 °C | symbol | `Bei Raumtemperatur ist {name} {v}.` |
| `p` | protons | symbol | `Ein Atom {name} hat {v} Protonen.` |
| `e` | electrons | symbol | `Ein Atom {name} hat {v} Elektronen.` |
| `n` | neutrons (most common isotope) | symbol | `Ein Atom {name} hat meist {v} Neutronen.` |
| `a` | outer electrons | symbol | `Die Zahl der Außenelektronen von {name} ist {v}.` |
| `h` | number of shells | symbol | `Die Zahl der Schalen von {name} ist {v}.` |
| `v` | electron arrangement | symbol | `Die Elektronenverteilung von {name}: {v}.` |
| `i` | typical ion and charge | symbol | `Das typische Ion von {name} ist {v}.` |
| `w` | valence | symbol | `Die Wertigkeit von {name} ist {v}.` |
| `R` | formula of compound | formula | `Die Formel von {name} ist {key}.` |
| `f` | name of formula (reverse) | formula | `Die Formel {key} steht für {name}.` |
| `m` | molar mass | formula | `Die molare Masse von {name} beträgt {v} g/mol.` |
| `b` | type of bond | formula | `Die Bindung in {name} ist eine {v}.` |
| `q` | reaction equation | slug | `Gleichung für {name}: {v}` |
| `c` | acid/base character and pH | formula | `Säure oder Lauge? {name} ist eine {v}.` |
| `t` | test reaction | slug | `Nachweis für {name}: {v}` |
| `E` | profile of element ("Was ist X?") | symbol | `Das Element {name} ({key}) ist ein {K} mit der Ordnungszahl {O}.` |

- Slots: `{name}` (object name), `{key}`, `{v}` (this type's value), and `{X}` (the value of type
  character X for the same object, used by the profile).
- Every template starts with a non-empty fixed prefix, so the first character appears after the type character (~2 forward passes) for every type.
- Every rendered answer is ≤ 100 characters (checked by the builder). Values of `q` and `t` are ≤ 50 B so that template + name (≤ 40 B) + value stays within 100 B.
- Values and templates are printed only by the board and may use characters outside the model alphabet (e.g. `→`). The answer is printed by the
  firmware and never fed back to the model, so it doesn't use context.
- The exact wording is fixed in the data, not in C. It may be polished during implementation as long
  as the prefix rule and the length limit hold. The authoritative wording is
  `training/data/templates/hybrid.toml` (implementation, 2026-11-22).

**Rationale**:
- Covers every type in FR-004 (26 ≥ 20, SC-006). Two-way relations (symbol, atomic number, formula)
  have a forward and a reverse type (FR-006).
- A constant prefix after 2 steps keeps the first visible character at ~0.4 s (SC-007), however long the key is.

**Alternatives considered**:
- *Templates in C*: wording fixes would need firmware rebuilds, and Python and C would need two copies.
- *Combined types ("symbol and atomic number")*: the edge case only requires answering one of the two
  correctly. The model may pick either type, which is allowed.

## R5 – Lookup when the key or the fact is missing

**Decision**: The firmware resolves `<fn>` + type + key in this order:

1. No (valid) fact table → `Die Faktentabelle fehlt, Faktenfragen gehen gerade nicht.`
2. Unknown type character → `Das weiß ich leider nicht.`
3. Forward type, unknown key → `Das weiß ich leider nicht.`
4. Reverse type (`s`, `o`, `f`): scan this type's values for the key. No match → `Das weiß ich leider nicht.`
5. Object known but the type doesn't apply (e.g. ion of neon) → the type's "not applicable" text, e.g.
   `{name} gibt es nicht.` after the prefix `Das typische Ion von `, otherwise
   `{name}: dazu habe ich keine Angabe.` (the text continues the already printed prefix)

For names it does not know (compounds outside the table), the model is trained to answer
`Das weiß ich leider nicht.` as plain text. Training includes such negatives: made-up and
out-of-curriculum compound names, plus unknown formulas, which are copied and caught by rule 3.

**Rationale**: FR-011 says the board never invents a value. Rules 1–5 are deterministic and identical in
C and Python (parity).

## R6 – Building the fact table (FR-005)

**Decision**: A new builder (`training/src/ultratiny/factgen.py`) computes all values from one source of truth:

- **Element base data**: `data/facts/wikidata_elemente_chemie.tsv`, existing and CC0. It provides name,
  symbol, atomic number, mass, period, group, family, category and state.
- **Computed by rule from the atomic number and group**, extending `tools/periodic.py`:
  - protons = electrons = Z
  - neutrons = round(mass) − Z, the school convention for the most common isotope
  - outer electrons and shells for main-group elements
  - electron arrangement for Z ≤ 20 and Ga–Kr
  - typical ion and charge for main groups I–III and V–VII
  - valence for main-group elements
- **Binary ionic compounds**: the 11 main-group metals (Li, Na, K, Rb, Cs, Be, Mg, Ca, Sr, Ba, Al) × the
  8 anions (F, Cl, Br, I, O, S, N, P). For each pair the builder computes:
  - formula from the charges (least common multiple)
  - German name (`Aluminiumoxid`)
  - molar mass
  - bond type `Ionenbindung`
- **Curated, with sources as today (`own`, curriculum)**: molecules and other compounds from
  `chemie_verbindungen.tsv` (90), plus new files for:
  - reactions (`chemie_gleichungen.tsv`, ~30 curriculum equations, checked for atom balance by the builder)
  - acids/bases (`chemie_saeuren_basen.tsv`)
  - test reactions (`chemie_nachweise.tsv`)
- **Bond type** for every compound is computed from its elements: metal + non-metal → `Ionenbindung`, only non-metals → `Elektronenpaarbindung`, only metals → `Metallbindung` (curated overrides allowed with a source).
- **Molar masses** are computed from formulas with atomic masses rounded to 0.1 (school tables) and
  printed with one decimal and a German comma (`18,0`).

Estimated size: 118 elements × ~12 values + ~180 compounds × ~4 values + ~60 curated records, about
2,500 records of ~12 B, plus names and templates, giving **25–45 KB**. The builder fails if the table is
larger than 90 % of the 64 KB area.

**Rationale**: FR-005 says computed values come from rules, and an LLM never creates a fact. Atom-balance
and charge-neutrality checks catch curation errors.

## R7 – Question forms, phrasing families, held-back sets (FR-007, FR-009)

**Decision**:

- **Templates**: new `data/templates/hybrid.toml`. Each type gets ≥ 12 forms grouped into **families**
  of structurally similar forms:
  - `w`: W-question
  - `imp`: "Nenne/Gib an/Bestimme/Berechne/Stelle auf"
  - `kurz`: "Ordnungszahl Eisen?"
  - `satz`: "Die Ordnungszahl von Eisen ist …?"
  - `alltag`: "Wie viele Protonen stecken in Eisen?"
  - `rev`: reverse forms
  - `multi`: two-fact forms ("Symbol und Ordnungszahl von {name}?"), trained with the target of one of the two types (the first named)
- **Surface noise** at generation time, as today:
  - lower case
  - no punctuation
  - one typo outside the key
  - symbols and formulas in the question (`{key}`, e.g. `CO`, `Co`, `N`) are never changed by noise, so case stays meaningful (FR-012); names may be lowercased
- **LLM paraphrases** from the Spark (PR #7 pipeline) may add forms but never values. Paraphrases go
  through the existing augment checks.
- **Held back**, deterministically from the seed and a stable hash:
  - (a) **combinations**: 10 % of the type × object pairs, chosen so that every object keeps ≥ 3
    trained types and every type keeps ≥ 80 % of its objects
  - (b) **families**: one family per type (≥ 2 forms), never seen in training for that type
  - (c) the **short-test set** (R9): any training prompt whose normalised form equals a short-test question is dropped
- **Data mix per epoch**: about 55 % facts, 30 % explanations, 15 % greetings, refusals and "unknown".
  Set by repeat weights in the config, so explanations keep capacity.

**Rationale**: In the literature, retrieval for unseen phrasings needs diverse phrasings per fact in
training. Honest generalisation needs whole combinations and families held back (spec US3).

## R8 – Short curriculum explanations (FR-003, FR-008)

**Decision**: The ~460 `frei` entries of the `chemie_rlp_*.tsv` and `chemie_reaktionen.tsv` files get
an answer of at most 60 characters:
- A Spark script (an extension of `tools/augment_llm.py`, prompt "kürze auf ≤ 60 Zeichen, keine neuen
  Fakten") proposes them into `data/facts/chemie_kurz.tsv`.
- An **automatic check** rejects a proposal when:
  - it is longer than 60 characters
  - it uses characters outside the alphabet
  - it contains a number, formula or symbol that is not in the long answer
  - it lacks the topic's key term (the first noun of the question's subject)
- The user reviews the accepted file in the PR before training. A `reviewed` column is set per row.

Entries whose content fits the fact table (e.g. "Was ist Kalk chemisch?" → CaCO3) become fact questions instead.

**Rationale**: FR-008 says an LLM may propose, but a check accepts. At 60 characters, a 40-character
question plus the answer fits context 104.

**Alternative considered**: *Raise the context*: the arena grows ~340 B per position, and it is already at 35.5 of 36 KB.

## R9 – Short-test set (FR-010)

**Decision**: `data/eval/kurzarbeit.tsv`, at least 120 questions in grade 7–10 short-test style. I
draft it from typical question formats, not from the templates. It mixes:
- ~70 % factual
- ~15 % explanations
- ~10 % out of scope or unknown
- ~5 % multi-fact or tricky case (N/Na/Co/CO)

Each row has the expected function output or an expected text with keywords. The user reviews it, and
its SHA-256 is pinned in the config. Datagen refuses to run if the file changed without updating the pin.

## R10 – Evaluation (FR-009, US3)

**Decision**: `evaluate.py` reports these sets separately:
- trained phrasings (sample)
- held-back families
- held-back combinations
- short-test set
- explanations
- refusals and false refusals

**Scoring**:
- **Factual items** are scored on the **function output**. Type and key must match exactly; a
  different type that leads to the same rendered answer counts as correct.
- **Wrong fact** = the function output renders a value that differs from the expected one. Unknown and
  declined answers are not wrong facts (SC-003/SC-004).
- **Explanations**: all expected keywords present and ≤ 60 characters.
- **Refusals**: as today (refusal relation).

The pipeline's pass/fail thresholds are those of SC-001–SC-005.

## R11 – Parity across model and table (FR-014, SC-008)

**Decision**: The golden file gains a `facts_sha256` and, per case, the **rendered** answer text next
to the token sequence. The table renderer exists twice:
- `runtime/src/facts.c`
- `training/src/ultratiny/facttable.py`

Both are tested against the same golden cases on the host:
- `utiny-host --facts file.utft`
- the alignment-checked build

`tools/device_parity.py` compares the rendered text on the board. Values are stored as finished strings,
so there is no number formatting at runtime and nothing that could diverge.

## R12 – Model format change

**Decision**: UTNY format **version 2**: token id 5 is `<fn>`, encoded as `0xFFFF0005` in the alphabet
table, and text characters start at id 6. The loader accepts v1 (5 specials, no function mode) and v2.
Exporter, reference, runtime loader and golden files change in the same PR (constitution workflow rule).
Model size grows by one embedding row (128 B + 4 B scale). Arena is unchanged except the logits
(+4 B).

## R13 – Firmware RAM and console

**Decision**: The fact-table module uses one static 128 B read buffer and a 16 B key buffer. Boot
validation computes the CRC in 128 B chunks, which takes a few milliseconds for 45 KB and yields to the
watchdog every 4 KB. The console gets a `fn` sub-state:
- `<fn>` → wait for the type character
- type character → print the template prefix
- then collect up to 12 key characters without printing them
- `<eos>`, or the key limit → look up and print the rest

The `/info` command shows the fact table version, record count and status.

Static DRAM grows by about 200 B. That is measured against the 4,960 B free heap from 005, and the
board test checks it.
