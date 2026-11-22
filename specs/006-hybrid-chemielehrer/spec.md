# Feature Specification: Hybrid Chemistry Teacher on the NodeMCU

**Feature Branch**: `claude/keen-feynman-z2sszl`

**Created**: 2026-11-22

**Status**: Draft

**Input**: User description: "Hybrid-Chemielehrer für die NodeMCU (Folge-Feature zu 005). Ziel: Das Modell `chemie-nodemcu` (0,58 Mio. Parameter, Kontext 104) beantwortet typische Fragen aus Kurzarbeiten der Klassen 7–10 zuverlässig, auch in neuen Formulierungen. Entscheidung des Nutzers: HYBRID-Antwortmodus. Bei Faktenfragen … erkennt das Modell nur Fragetyp + Objekt (Funktions-Token) und die Firmware setzt den geprüften Wert aus einer Faktentabelle im Flash in eine Antwortvorlage ein. Begrüßungen, Abweisungen und kurze Begriffserklärungen … schreibt das Modell weiter selbst. Trainingsdaten werden deutlich heterogener … Bewertung ehrlich … Grenzen der NodeMCU (Constitution v2.0.0) bleiben … Performance-Tricks sind ein separates Folge-Feature."

## Background

Feature 005 brought the chemistry teacher to the NodeMCU at its size limit (0.58 M parameters, context 104 characters). On the board it answers trained question forms correctly (demo 96 %, held-out phrasings 80.9 %, refusals 90.9 %) and meets the speed budget (first character 158 ms, 5.1 characters/s). In free use it fails in three ways (specs/005-nodemcu-port/measurements.md):

1. **Missing question types.** About 460 curriculum questions have answers longer than the context and were dropped; questions like "Was ist Kohlenstoff?" or "Welche Metalle gibt es?" have no training data at all.
2. **Confused facts.** "Was ist N?" → "N ist die Formel von Stickstoffmonooxid." The model mixes up facts it has stored.
3. **Poor transfer.** A fact learned in one phrasing or direction (element → symbol) is not available in another (symbol → element).

Research (PR #4 and a new literature review, 2026-11-22) suggests that at this size the limit is not how much the model can store but whether it can retrieve a fact for a new phrasing, and that keeping verified facts outside the network removes wrong facts. The user decided on a **hybrid answer mode**.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Ask a factual question in your own words and get a correct answer (Priority: P1)

A student in grades 7–10 types a factual chemistry question the way it appears in a short test ("Kurzarbeit") or the way they would phrase it themselves: element symbols and names in both directions, atomic number, atomic mass, group, period, family, metal or non-metal, state, atomic structure (protons, electrons, neutrons, outer electrons, shells, electron arrangement), ions and their charge, formulas in both directions, molar mass, type of bond, valence, simple reaction equations, acids and bases, and test reactions. The board answers with the correct value in a short German sentence, also for phrasings and combinations it never saw in training.

**Why this priority**: This is what fails today and what a chemistry teacher is used for most. Wrong facts are worse than no answer.

**Independent Test**: Ask questions from the held-back test sets (US3) on the board and on the PC reference; compare answers with the verified fact table.

**Acceptance Scenarios**:

1. **Given** the board with the new model, **When** the student asks "Welche Ordnungszahl hat Kupfer?" and the combination "atomic number × copper" was never in training, **Then** the answer states 29.
2. **Given** the board, **When** the student asks "Was ist N?" or "Wofür steht N?", **Then** the answer says that N is the symbol of nitrogen (Stickstoff).
3. **Given** the board, **When** the student asks "Wie viele Außenelektronen hat Schwefel?", **Then** the answer states 6.
4. **Given** the board, **When** the student asks "Stelle die Formel von Aluminiumoxid auf", **Then** the answer states Al2O3.
5. **Given** the board, **When** the student asks "Welche molare Masse hat Wasser?", **Then** the answer states about 18 g/mol.
6. **Given** a factual question about an object the fact table does not contain (for example a compound outside the curriculum), **When** it is asked, **Then** the board says it does not know, instead of inventing a value.
7. **Given** a factual answer, **Then** every value in it (number, symbol, formula, charge, equation) is identical to the verified fact table: the board never prints a fact value that is not in the table.

---

### User Story 2 - Short explanations, greetings and refusals still come from the model (Priority: P2)

A student asks for a short explanation of a curriculum term ("Was ist eine chemische Reaktion?", "Was ist ein Katalysator?"), greets the teacher, or asks something outside chemistry. The model writes a short answer itself: a short explanation in at most about 60 characters, a greeting, or a polite refusal.

**Why this priority**: The PoC is about a language model on a microcontroller; explanations show that the model still writes text itself. Today these questions are lost because their answers are too long.

**Independent Test**: Ask the curriculum questions from the held-back set and a set of off-topic questions; check that explanations are short, correct in substance and that off-topic questions are refused.

**Acceptance Scenarios**:

1. **Given** the board, **When** the student asks "Was ist eine chemische Reaktion?", **Then** it answers with a short, correct explanation that fits the context.
2. **Given** the board, **When** the student writes "Hi", **Then** it greets and invites a chemistry question.
3. **Given** the board, **When** the student asks "Was ist Berlin?" or "Wie wird das Wetter morgen?", **Then** it politely refuses.
4. **Given** a question that is ambiguous between a fact and an explanation ("Was ist Kohlenstoff?"), **Then** it gives a short profile of the element (for example kind of element, symbol and atomic number) rather than refusing. (Implemented through the profile question type of User Story 1.)

---

### User Story 3 - Honest measurement and one-command training (Priority: P3)

The developer generates the new training data, trains on the DGX Spark and gets an evaluation that shows real generalisation: results on question-type × object combinations and on whole phrasing families that were held back from training, plus a fixed set of realistic short-test questions.

**Why this priority**: Without honest measurement the improvement cannot be shown; today's 96 % mainly reflect memorised phrasings.

**Independent Test**: Run the data generation and training pipeline; the evaluation report lists accuracy per held-back set and per question type.

**Acceptance Scenarios**:

1. **Given** the data generator, **When** it runs, **Then** it reports how many verified facts, question types and structurally different question forms per type were produced, and which combinations and phrasing families are held back.
2. **Given** a trained model, **When** evaluation runs, **Then** it reports accuracy separately for: trained phrasings, held-back phrasing families, held-back type × object combinations, the short-test set, explanations, and refusals.
3. **Given** the same configuration and seed on the CPU, **When** training runs twice, **Then** the results are identical.

---

### Edge Cases

- The student uses a symbol that is also a word or appears in a formula ("Was ist N?", "Was ist CO?", "Was ist Co?"): case matters; the answer must match the correct object (N = nitrogen, CO = carbon monoxide, Co = cobalt).
- The question contains a typo, no capitals or no punctuation ("ordnungszahl von eisen"): it is still understood.
- The object is unknown to the fact table, or a question type does not apply to it ("Welche Ladung hat das Ion von Neon?"): the board explains that it does not know or that the element does not form such an ion, without inventing a value.
- The filled-in answer would exceed the context or the answer limit: answer templates are short enough that this cannot happen.
- A question asks for several facts at once ("Symbol und Ordnungszahl von Gold?"): it answers at least one of them correctly or both; it never mixes values of different elements.
- Follow-up questions without a subject ("gibt es andere?"): every question stands alone (no conversation memory); such questions are answered as unknown.
- The fact table in flash is missing or corrupt: the board reports a clear error at start and keeps answering model-written questions (greetings, explanations, refusals).

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: For factual questions the model MUST output a question type and an object instead of the answer text; the board MUST look up the value in a verified fact table and print it in a fixed short German answer template for that question type.
- **FR-002**: Fact values printed by the board MUST come only from the fact table; the board MUST NOT print a fact value the model generated itself. Model-written explanations (FR-003) MUST NOT contain a value that the fact table holds as a fact (symbol, number, formula of a table object); such entries become factual questions instead.
- **FR-003**: Greetings, refusals and short curriculum explanations MUST be written by the model; explanations MUST be at most 60 characters so that question and answer fit the context.
- **FR-004**: The fact table MUST cover at least these question types: symbol ↔ name (both directions), atomic number ↔ name (both directions), atomic mass, period, group, family, metal/non-metal/semimetal, state at room temperature, protons, electrons, neutrons (most common isotope), outer electrons, number of shells, electron arrangement by shell, typical ion and its charge, formula ↔ name of compounds (both directions), molar mass of compounds, type of bond, valence, reaction equations for the curriculum reactions, acids/bases (name, formula, pH range) and test reactions, plus a short profile answer for "Was ist <Element>?".
- **FR-005**: Values that follow from the periodic table (atomic structure, ions of main-group elements, binary ionic formulas, molar masses, bond type) MUST be computed deterministically from verified element data; curated values (compounds, reaction equations, test reactions, acids/bases) MUST cite their source as today; a language model MUST NOT produce or change any fact value.
- **FR-006**: The training data MUST contain every relation in both directions where it has two (e.g. element → symbol and symbol → element; name → formula and formula → name).
- **FR-007**: For every question type the training data MUST contain at least 10 structurally different question forms, including exam phrasings ("Nenne …", "Gib … an", "Berechne …", "Stelle … auf", "Wie viele …"), short forms ("Ordnungszahl Eisen?"), lower case and missing punctuation.
- **FR-008**: The curriculum explanations (today ~460 entries in grades 7–10 topics) MUST get short answers of at most 60 characters; shortened answers MUST be checked for correctness before training (a language model may propose them, a check accepts them).
- **FR-009**: The data generator MUST hold back from training (a) whole question-type × object combinations, (b) whole phrasing families per question type, and (c) a fixed short-test set; the evaluation MUST report accuracy on each separately.
- **FR-010**: The project MUST include a fixed short-test set of at least 100 realistic questions in the style of grade 7–10 short tests, written independently of the training templates and frozen before training.
- **FR-011**: When the model's question type or object is not in the fact table, or the type does not apply to the object, the board MUST answer that it does not know (or that the element has no such property) instead of guessing.
- **FR-012**: Upper and lower case MUST be distinguished for symbols and formulas (Co ≠ CO, N ≠ Na).
- **FR-013**: The fact table MUST be versioned and validated at start like the model; a missing or corrupt table MUST give a clear error, and model-written answers MUST keep working.
- **FR-014**: The PC reference MUST produce exactly the same answers as the board for the same model, fact table and question (parity as in specs 001/005).
- **FR-015**: Training MUST run with one command on the DGX Spark and on CPU, as in feature 005, and MUST record data version and held-back sets with the run.

### Key Entities

- **Fact table**: Verified facts per object (element, compound, reaction, acid/base, test reaction) and question type; each value has a source (computed, Wikidata, curated). Stored on the board next to the model.
- **Question type**: A kind of factual question (e.g. atomic number, outer electrons, formula), with its answer template, the objects it applies to and its question forms.
- **Answer template**: A short German sentence with slots for object and value, e.g. "Die Ordnungszahl von {Element} ist {Wert}." (starting with fixed text, so the board can print it early).
- **Function output**: What the model produces for a factual question: question type + object (or "explanation"/"greeting"/"refusal" when it writes text itself).
- **Held-back sets**: Type × object combinations, phrasing families and the short-test set that never appear in training.
- **Short-test set**: At least 100 realistic grade 7–10 questions with expected answers, written independently of the templates.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: On held-back type × object combinations, at least **85 %** of factual questions are answered correctly (today not measured; held-out phrasings 80.9 %).
- **SC-002**: On held-back phrasing families, at least **85 %** of factual questions are answered correctly.
- **SC-003**: On the short-test set, at least **80 %** of questions are answered correctly or, if outside the covered types, are declined; at most **3 %** get a wrong fact.
- **SC-004**: Wrong fact values occur only when the question was misunderstood: across all test sets at most **3 %** of factual answers contain a wrong value, and none contain a value that is not in the fact table.
- **SC-005**: Off-topic questions are refused at least **90 %** of the time; chemistry questions are wrongly refused at most **5 %** of the time.
- **SC-006**: The training data covers at least **20 question types** with at least **10 structurally different question forms** each, every two-way relation in both directions.
- **SC-007**: On the board the first character still appears within **2 s** and answers stream at **≥ 5 characters/s**; model and fact table stay within the NodeMCU budgets with at least 10 % headroom (model, arena and firmware as in feature 005; fact table: its own flash area of 64 KB outside the 1 MB mapped window, file ≤ 90 % of it, ≤ 1 KB extra static RAM).
- **SC-008**: The board's answers are identical to the PC reference for 100 % of the golden cases.

## Assumptions

- Board, model size and budgets stay as in feature 005 (NodeMCU, ~0.58 M parameters, context 104, arena ≤ 40 KB, ≥ 5 characters/s); speed or size tricks (int4, sparsity, speculative decoding, retrieval tables) are a separate later feature.
- The fact table is small (expected a few tens of KB) and is stored in its own 64 KB flash area outside the model area and outside the 1 MB mapped window (budget in SC-007; placement in plan.md).
- The short-test set is drafted from typical grade 7–10 short-test questions and reviewed by the user before training; it is never used for training.
- The language model on the DGX Spark (as in feature 003/PR #7) is used only to propose question phrasings and shortened explanations; facts come from computation, Wikidata (CC0) and curated, sourced lists.
- Conversation memory (follow-up questions) remains out of scope; every question is answered on its own.
- Explanations cover the existing curriculum topics (Rahmenlehrplan Berlin-Brandenburg, grades 7–10, as in spec 003); no new topics are added.
