# Feature Specification: ESP32-Chemielehrer

**Feature Branch**: `claude/modest-sagan-xrovbt`

**Created**: 2026-11-21

**Status**: Draft

**Input**: User description: "ich würde gerne dass wir ein thema intensiv lernen. ich denke chemie
ist ganz cool. das modell ist ja noch recht klein. können wir es vergrößern? können wir es mehr
trainieren? ich will eine demo die sehr gute antworten für ein begrenztes thema gibt. Was hältst
du davon: der ESP32 wird ein Chemielehrer." Clarified: level Mittelstufe (Kl. 7–10); content =
everything in the Berlin-Brandenburg Rahmenlehrplan Chemie 7–10 plus element profiles, basic
concepts, compounds & formulas, simple reactions; model size "groß" (~1.7 M parameters).

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Ask the chemistry teacher (Priority: P1)

A student types a chemistry question at Mittelstufe level (e.g. "Was ist ein Ion?", "Welche Formel
hat Kochsalz?", "Was entsteht, wenn Wasserstoff verbrennt?", "Welche Ordnungszahl hat Eisen?") and
the board answers with a short, correct, school-level German answer — offline on the ESP32.

**Why this priority**: This is the demo.

**Independent Test**: Flash firmware + chemistry model (or run `make qemu MODEL=…`), ask the demo
questions; answers are correct and free of typos.

**Acceptance Scenarios**:

1. **Given** the chemistry model, **When** a question from the demo list is asked, **Then** the
   answer matches the expected answer (SC-001).
2. **Given** a question phrased differently than in training, **When** asked, **Then** the answer
   is still correct in most cases (SC-002).

### User Story 2 - Honest "I don't know" (Priority: P1)

Off-topic or nonsense input ("Wer wurde 2014 Weltmeister?", "Alle", "asdf") gets a friendly
refusal ("Das weiß ich leider nicht. Frag mich etwas zur Chemie!") instead of invented chemistry.

**Why this priority**: A teacher that makes things up is worse than one that admits limits.

**Independent Test**: Ask held-out off-topic questions; most are refused, while chemistry
questions are (almost) never refused.

**Acceptance Scenarios**:

1. **Given** an off-topic question not seen in training, **When** asked, **Then** the refusal is
   given (SC-003).
2. **Given** a chemistry question from the demo or held-out set, **When** asked, **Then** it is
   not refused (SC-004).

### User Story 3 - Bigger model, longer training, still on the ESP32 (Priority: P2)

The model grows to ~1.7 M parameters (6 layers × 192) and trains longer, staying within the
constitution budgets; it trains on the M3 (MPS) or CPU with one command.

**Independent Test**: `uv run ut pipeline --config configs/chemie.toml --out runs/chemie` passes
eval and budget checks; host + QEMU parity stay bit-exact.

**Acceptance Scenarios**:

1. **Given** the chemistry config, **When** the pipeline runs, **Then** model ≤ 1.8 MB and arena
   ≤ 96 KB (fits the firmware buffer and the 128 KB budget with headroom).

### Edge Cases

- Questions mixing chemistry with other topics ("Welches Element hat Messi erfunden?"): refusal
  or chemistry answer, never an invented fact about the other topic.
- Questions about elements beyond the curriculum (e.g. Oganesson): element profile facts still
  answer (all 118 elements known).
- Very long questions: limited by the 192-character context (console reports "zu lang").

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The knowledge base MUST cover every Themenfeld 3.1–3.12 of the Rahmenlehrplan
  Chemie 7–10 Berlin-Brandenburg (Teil C, amtliche Fassung 2015) with explanations at Mittelstufe
  level, each concept asked in ≥ 4 phrasings (1 held out).
- **FR-002**: Element profiles MUST cover all 118 elements: symbol, atomic number, atomic mass,
  group/period, metal/non-metal/semimetal, state at room temperature; plus melting/boiling point
  where reliable data exist. Lookups in both directions where unique (symbol → element,
  atomic number → element).
- **FR-003**: The knowledge base MUST include common compounds (name ↔ formula, everyday names,
  use) and simple reactions (word equations) from the curriculum.
- **FR-004**: Off-topic and nonsense inputs MUST be answered with a fixed refusal sentence; the
  persona answers ("Wer bist du?") describe a small chemistry teacher on an ESP32.
- **FR-005**: Answers MUST be ≤ 160 characters, German, school-level, and use only the model
  alphabet (formulas written as H2O, CO2, Na+, Cl-).
- **FR-006**: Rare long answers MUST be oversampled in training so they are reproduced without
  typos.
- **FR-007**: Model size ~1.7 M parameters, context 192, within constitution budgets; runtime,
  format (UTNY v1) and firmware unchanged.
- **FR-008**: Evaluation MUST report demo accuracy, held-out accuracy, refusal rate on held-out
  off-topic prompts and false-refusal rate on chemistry prompts.
- **FR-009**: All data MUST be own text (MIT) or Wikidata (CC0), recorded per row.

### Key Entities

- **Concept Q&A**: curriculum topic (Themenfeld), question phrasings, answer.
- **Element profile**: per element facts (from Wikidata + computed periodic-table position).
- **Compound**: name, formula, everyday name, use.
- **Refusal example**: off-topic question/nonsense → refusal sentence.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: ≥ 95 % of the chemistry demo list answered correctly (edit-distance rule of 001).
- **SC-002**: ≥ 75 % of held-out chemistry phrasings answered correctly.
- **SC-003**: ≥ 80 % of held-out off-topic/nonsense inputs refused.
- **SC-004**: ≤ 3 % of chemistry demo + held-out prompts wrongly refused.
- **SC-005**: Model ≤ 1.8 MB, arena ≤ 96 KB; host and QEMU golden parity 100 %.
- **SC-006**: On the board ≥ 10 characters/s (to be measured; estimate 11–20).

## Assumptions

- Curriculum structure taken from the Bildungsserver page "Themen und Inhalte" (Themenfelder 3.1
  to 3.12); explanations are written for this project, not copied.
- Capitals/currencies are dropped from this model (focus on chemistry); the starter and v1
  configs stay available.
- Training runs on the developer's M3 (MPS) or in the container on CPU (slower).
