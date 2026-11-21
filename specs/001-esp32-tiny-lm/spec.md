# Feature Specification: Tiny Language Model Demo on a Classic ESP32

**Feature Branch**: `claude/modest-sagan-xrovbt`

**Created**: 2026-11-20

**Status**: Draft

**Input**: User description: "Ein kleines Sprachmodell als Demo, dass ein Sprachmodell vollständig
offline auf einem klassischen ESP32 (kein PSRAM, 4 MB Flash, 520 KB SRAM) laufen kann. Inspiriert
von Tiny-2.1 (zeichenbasierter Transformer, ~367k Parameter, 8-Bit-Gewichte mit Skala pro Zeile,
Training in PyTorch, Inferenz in C). Nutzer tippt über die serielle Konsole einen Prompt bzw. eine
Frage, das Modell generiert Zeichen für Zeichen eine Antwort und streamt sie zurück. Training auf
einem PC (CPU reicht), Export in ein versioniertes Binärformat, das in eine Flash-Partition geflasht
wird."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Ask the board and watch it answer (Priority: P1)

A demo viewer connects a classic ESP32 board to a computer, opens a serial terminal, types a
question or prompt, and watches the board write an answer character by character — with no
network connection and no help from the computer beyond displaying the text.

**Why this priority**: This is the entire point of the demo: visible proof that a language model
runs on a $5 microcontroller.

**Independent Test**: Flash the provided firmware and model onto a board, disconnect all networks,
type a prompt from the demo prompt list, and observe a sensible streamed answer.

**Acceptance Scenarios**:

1. **Given** a flashed board with Wi-Fi/Bluetooth disabled, **When** the user types a prompt from
   the demo prompt list and presses Enter, **Then** the answer starts appearing within 1 second and
   is streamed character by character until it ends on its own.
2. **Given** the board has just answered, **When** the user types another prompt, **Then** a new
   answer is produced without restarting the board.
3. **Given** the board is powered on, **When** the serial terminal is opened, **Then** a short
   banner shows the model name, model format version, parameter count, and a ready prompt.

---

### User Story 2 - Train and export a model on a PC (Priority: P2)

A developer runs one documented command on their computer — primarily an Apple Silicon Mac (M3)
using its GPU cores, with a CPU-only fallback on any machine — that generates the training data,
trains the model, evaluates it, and exports a versioned model file ready for flashing.

**Why this priority**: Without a reproducible training path the demo cannot be rebuilt, improved,
or verified; it is required to produce the model for Story 1 but the demo can be shown with a
pre-built model file.

**Independent Test**: On a clean machine, run the documented training command and confirm it
produces a model file plus an evaluation report, and that repeating it with the same seed on the
same machine and device yields an identical model file.

**Acceptance Scenarios**:

1. **Given** an Apple Silicon Mac (M3) with the documented prerequisites, **When** the developer
   runs the training command with GPU acceleration, **Then** it completes within 2 hours and
   produces a model file, an evaluation report, and a size/budget report.
2. **Given** a machine without a usable GPU, **When** the developer runs the same command, **Then**
   it falls back to the CPU automatically and still completes (slower is acceptable).
3. **Given** the same data, configuration, seed, and device type, **When** training is run twice,
   **Then** the exported model files are byte-identical on CPU; on GPU, where the hardware does not
   guarantee bit-identical math, the evaluation results MUST be identical within ±1 percentage
   point.

---

### User Story 3 - Flash a new model without rebuilding the firmware (Priority: P3)

A developer flashes a newly exported model file into the board's model storage area and the
existing firmware picks it up after a reset.

**Why this priority**: Makes iteration on the model fast and keeps firmware and model independent,
but is not needed for a first demo. It builds on the firmware delivered by User Story 1.

**Independent Test**: Flash firmware once, then flash two different compatible model files one after
another, and confirm the banner and answers reflect the currently flashed model.

**Acceptance Scenarios**:

1. **Given** a board with firmware installed, **When** a compatible model file is flashed to the
   model area and the board is reset, **Then** the banner shows the new model and it answers prompts.
2. **Given** a model file with an unknown format version or that exceeds the device budget,
   **When** the board starts, **Then** it prints a clear error and does not crash or reboot-loop.

---

### Edge Cases

- Empty input (only Enter): the board re-shows the ready prompt and generates nothing.
- Input longer than the model's context: the board uses only the most recent part that fits and
  says so once, or rejects it with a clear message; it never crashes.
- Characters outside the model's alphabet (e.g. emoji): they are skipped or replaced, and the user
  is told; generation still proceeds.
- An answer that does not end on its own: generation stops at a fixed maximum answer length.
- User types while an answer is streaming: the input is ignored or queued until the answer
  finishes; the board stays responsive. A dedicated key/command aborts the current answer.
- No model or a corrupted model in the model area: clear error message at boot, no reboot loop.
- Prompts unrelated to the training content: the board still produces fluent text; factual
  correctness is not guaranteed and the demo documentation says so.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The board MUST run the complete language model locally with all wireless radios
  disabled; no answer may depend on any external computation.
- **FR-002**: The board MUST accept a text prompt over its USB serial console and stream the
  generated answer back one character at a time as it is produced.
- **FR-003**: The model MUST operate on individual characters (character-level), with a fixed
  alphabet documented alongside the model.
- **FR-004**: The model MUST understand prompts and answer in German; the alphabet MUST include
  the German umlauts and ß (ä, ö, ü, Ä, Ö, Ü, ß), and the serial console MUST display them
  correctly.
- **FR-005**: The demo content MUST be question answering over a fixed, documented knowledge base
  of facts (like Tiny-2.1): each fact is asked in many German phrasings during training, and the
  model answers with the fact in a short German sentence.
- **FR-006**: Generation MUST stop at an end-of-answer marker or at a configurable maximum answer
  length (default 200 characters), whichever comes first.
- **FR-007**: The board MUST print a startup banner with model name, model format version,
  parameter count, and memory use, followed by a ready prompt.
- **FR-008**: The board MUST let the user abort an answer in progress with a single key.
- **FR-009**: Output MUST be deterministic by default (same prompt → same answer); an optional
  sampling mode with a fixed seed MAY be offered for variety.
- **FR-010**: Model and firmware MUST fit the constitution's default budgets for the classic
  ESP32: model ≤ 2 MB stored in a dedicated model area, inference working memory ≤ 128 KB.
- **FR-011**: A single documented command MUST generate training data, train, evaluate, and
  export the model; it MUST use the GPU of an Apple Silicon Mac when available and MUST fall back
  to the CPU on any machine without one.
- **FR-012**: The exported model file MUST identify itself (magic number, format version, model
  dimensions) so the board can reject incompatible files.
- **FR-013**: The firmware MUST validate the model file at boot and report a clear error for a
  missing, corrupt, incompatible, or over-budget model.
- **FR-014**: The project MUST include a PC-side reference that produces exactly the same answers
  as the board for the same model and prompt, used to verify the board's output.
- **FR-015**: Training data sources and their licenses MUST be documented; only data with
  compatible licenses may be used.
- **FR-016**: The repository MUST contain step-by-step instructions to build, flash, and run the
  demo, plus a demo prompt list with expected answers.

### Key Entities

- **Training corpus**: the text the model learns from (generated and/or collected), with source and
  license per part.
- **Model file**: versioned, self-describing file containing quantized weights and the model
  dimensions; produced by export, consumed by the board and the PC reference.
- **Alphabet**: the fixed set of characters the model can read and write, including control
  markers (e.g. end of answer).
- **Prompt / Answer**: the user's input line and the generated character stream.
- **Evaluation set**: held-out prompts with expected answers used to measure quality across runs.
- **Budget report**: measured flash and RAM use and speed compared with the budgets.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: On a classic ESP32 board, the first character of an answer appears within 1 second
  of pressing Enter for prompts from the demo list typed at normal human speed (pasted text may
  take longer and is reported separately).
- **SC-002**: The board generates at least 10 characters per second on average, so a 100-character
  answer completes in 10 seconds or less.
- **SC-003**: At least 80% of the demo prompt list produces correct answers. An answer counts as
  correct when, after ignoring case, punctuation and extra spaces, it differs from the expected
  answer in at most 10% of its characters (normalized edit distance ≤ 0.1).
- **SC-004**: At least 60% of held-out rephrasings of trained prompts produce correct answers
  (same rule as SC-003), showing the model generalizes beyond memorized wording.
- **SC-005**: The board answers 100 consecutive prompts over at least 1 hour without a crash,
  reboot, or growing memory use.
- **SC-006**: For 100% of evaluation prompts, the board's output matches the PC reference output
  exactly.
- **SC-007**: Measured flash and RAM use stay within the budgets with at least 10% headroom.
- **SC-008**: A newcomer following the instructions goes from a fresh checkout to a running demo
  in under 30 minutes using the pre-built model file.

## Assumptions

- Target hardware is a standard classic ESP32 development board (no PSRAM, 4 MB flash) connected
  to a computer via USB; the computer only displays text.
- Scope is a single-turn demo: each prompt is answered independently; no conversation memory
  across prompts.
- The model is small (on the order of a few hundred thousand to ~1 million parameters); it is
  expected to be fluent and correct on its training domain only, not a general assistant.
- Sensors or other peripherals attached to the board are out of scope for this feature.
- Training uses only data the project generates itself or data with permissive licenses.
- The knowledge base is a curated list of German facts (topic mix chosen during planning, e.g.
  geography, science, the ESP32 itself), sized so the model can learn it within the budgets
  (order of a few thousand facts, like Tiny-2.1's ~3,500).
- The primary training machine is the developer's Apple Silicon Mac (M3); training must still be
  possible without it (CPU fallback), per the project constitution.
- A pre-built model file will be provided with the release so the demo can be shown without
  training.
