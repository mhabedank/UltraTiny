# Feature Specification: UltraTiny PoC on NodeMCU (ESP8266)

**Feature Branch**: `claude/keen-feynman-z2sszl`

**Created**: 2026-11-21

**Status**: Draft

**Input**: User description: "we want to switch from esp32 to nodeMCU" — clarified: "wir wollen ja einfach nur einen PoC für unser LLM Modell machen", running on the NodeMCU itself; the model "passt knapp auf einen ESP32", so it has to be adapted.

**Clarifications (2026-11-21)**:
- Purpose: a proof of concept that the UltraTiny language model (specs 001–003) runs fully offline on a NodeMCU board. The NodeMCU boards are already on hand.
- Inference runs on the NodeMCU itself, not on a server.
- PoC model: the **starter model** (~600k parameters, `configs/starter.toml`) with its context shortened to **104 characters** (plan research R4: the largest context that keeps 10 % arena headroom). The Chemielehrer (1.75 M parameters) is out of scope for this PoC.
- ESP32 is no longer the target board for new work (constitution v2.0.0).

## Target Board and Budgets *(constitution Principle I)*

| Item | ESP32 (legacy, spec 001) | NodeMCU (constitution v2.0.0 defaults) |
|------|------------------------|-------------------------|
| Board | classic ESP32, 520 KB SRAM, 4 MB flash, FPU | NodeMCU v2/v3: ESP8266, ~80 KB data RAM, 4 MB flash, **no FPU** |
| Model file | ≤ 2 MB | **≤ 700 KB** (effectively ≤ 672 KB: the size of the model area in the flash layout) |
| Firmware + model, readable in place | – | together ≤ the board's directly readable flash window (1 MB) |
| Inference working memory | ≤ 128 KB | **≤ 40 KB** |
| PSRAM | none | none |
| First answer character | ≤ 1 s | **≤ 2 s** |
| Generation speed | ≥ 10 chars/s | **≥ 5 chars/s** |
| Headroom | ≥ 10 % of each memory budget | ≥ 10 % of each memory budget |

These are the default budgets of constitution v2.0.0 (amended 2026-11-21), which made the NodeMCU the project's target board. This feature uses them unchanged; no per-feature amendment is needed. The ESP32 column is shown only for comparison.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Ask the NodeMCU and watch it answer (Priority: P1)

A demo viewer connects a NodeMCU board to a computer, opens a serial terminal, types a question from the demo prompt list, and watches the board write the answer character by character, with no network and no help from the computer.

**Why this priority**: This is the proof of concept: the same tiny language model running on an even smaller and cheaper board.

**Independent Test**: Flash the firmware and the PoC model onto a NodeMCU board, keep Wi-Fi off, type prompts from the demo prompt list, and compare the answers with the expected answers.

**Acceptance Scenarios**:

1. **Given** a flashed NodeMCU with Wi-Fi off, **When** the user types a demo prompt and presses Enter, **Then** the answer starts within 2 seconds and streams character by character until it ends on its own.
2. **Given** the board has just answered, **When** the user types another prompt, **Then** it answers again without a restart.
3. **Given** the board is powered on, **When** the serial terminal is opened, **Then** a banner shows the model name, format version, parameter count, memory use and the board type, followed by a ready prompt.
4. **Given** a question about the board itself (e.g. "Auf welchem Chip läufst du?"), **When** the user asks it, **Then** the answer names the NodeMCU/ESP8266, not the ESP32.

---

### User Story 2 - Train a NodeMCU-sized model with the existing pipeline (Priority: P2)

A developer runs the existing one-command training pipeline with a NodeMCU configuration and gets a model file, an evaluation report, and a budget report that checks the model against the NodeMCU budgets.

**Why this priority**: The PoC needs a model that fits. Reusing the existing pipeline keeps it reproducible, but a pre-built model is enough to show Story 1.

**Independent Test**: Run the pipeline with the NodeMCU configuration on a clean checkout, then run the budget report against the NodeMCU budgets.

**Acceptance Scenarios**:

1. **Given** the NodeMCU configuration, **When** the developer runs the training pipeline, **Then** it produces a model file, an evaluation report and a budget report, as in spec 001.
2. **Given** a model that exceeds a NodeMCU budget (file size, working memory or headroom), **When** the budget report runs, **Then** it fails and names the budget that was exceeded.
3. **Given** the same seed and configuration on CPU, **When** training runs twice, **Then** the model files are byte-identical.

---

### User Story 3 - Prove the NodeMCU gives exactly the reference answers (Priority: P3)

A developer runs the existing parity check against the NodeMCU board and confirms that the board produces the same answers as the PC reference for every golden test case.

**Why this priority**: The board has no floating-point unit, so its arithmetic differs from the ESP32's; parity proves the port is correct rather than "roughly working". It builds on Story 1.

**Independent Test**: Run the parity tool against a flashed NodeMCU with the PoC model's golden file.

**Acceptance Scenarios**:

1. **Given** a flashed NodeMCU and the PoC model's golden file, **When** the parity check runs, **Then** all golden cases produce text identical to the PC reference.
2. **Given** the PoC model on the host, **When** the host runtime is compared with the Python reference, **Then** the results match within the tolerance stated in spec 001 (bit-identical for integer paths).

---

### Edge Cases

- Prompt plus answer longer than the shortened context (104 characters): the board stops the answer cleanly at the context limit, or uses only the most recent part of the prompt that fits and says so once; it never crashes.
- A model file too big for the board's directly readable flash window, or needing more working memory than the budget: the board prints a clear error at boot and does not reboot-loop.
- The board's watchdog during a long answer: generation never triggers a watchdog reset.
- Empty input, characters outside the alphabet, typing during an answer, and the abort key behave as in spec 001.
- A board from stock that isn't an ESP8266 NodeMCU with 4 MB flash: the instructions say how to identify the board and which variants are supported.
- Corrupted or missing model on the board: clear error at boot, the board stays responsive.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The NodeMCU (ESP8266, 4 MB flash) MUST be a supported target board, running the complete model locally with Wi-Fi off.
- **FR-002**: The serial console behaviour of spec 001 (prompt in, streamed answer out, German including umlauts and ß, banner, abort key, deterministic output, empty-input and unknown-character handling) MUST work the same on the NodeMCU.
- **FR-003**: The project MUST provide a NodeMCU model configuration derived from the starter model with a context of 104 characters, trained on the starter knowledge base. This is the largest context that keeps the 10 % working-memory headroom (104 → 35,520 B of 40 KB; 112 would leave only 7.6 %, 128 needs ~42.5 KB and exceeds the budget).
- **FR-004**: The PoC model and firmware MUST meet the constitution's NodeMCU default budgets (see "Target Board and Budgets"), with at least 10 % headroom on each memory budget.
- **FR-005**: The budget report MUST check models against the NodeMCU default budgets (replacing the ESP32 budgets of 2 MB model and 128 KB working memory) and fail when one is exceeded.
- **FR-006**: The maximum answer length MUST be limited so that prompt and answer together fit the shortened context.
- **FR-007**: The model file format and the PC reference MUST stay shared with the ESP32 work; the NodeMCU MUST read the same model file format, and a format change is out of scope.
- **FR-008**: The NodeMCU MUST produce output identical to the PC reference for every golden case of the PoC model.
- **FR-009**: The firmware MUST validate the model at boot and report a missing, corrupt, incompatible or over-budget model clearly, without a reboot loop.
- **FR-010**: The knowledge-base facts in which the model describes its own hardware MUST be updated for the NodeMCU/ESP8266.
- **FR-011**: The repository MUST contain step-by-step instructions to build, flash and run the PoC on a NodeMCU, including how to identify supported board variants.
- **FR-012**: The board MUST stay responsive while answering and MUST NOT be reset by its watchdog during generation.
- **FR-013**: The existing ESP32 firmware is no longer developed further; removing it is not part of this feature.

### Key Entities

- **NodeMCU model configuration**: The starter model's dimensions with the shortened context and the NodeMCU budgets; input to the training pipeline.
- **PoC model file**: The trained, quantized starter-sized model in the existing format, sized for the NodeMCU.
- **NodeMCU budget**: Model file limit, readable-flash limit, working-memory limit, speed targets and headroom used by the budget report.
- **Golden file**: Reference prompts with the exact expected answers, used for the parity check on the board.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: On a real NodeMCU board, 100 % of the golden cases of the PoC model give text identical to the PC reference.
- **SC-002**: Demo accuracy of the PoC model is at least 80 %, and held-out accuracy at least 60 %, the same thresholds as the starter configuration.
- **SC-003**: The first answer character appears within 2 seconds of pressing Enter, and answers stream at 5 characters per second or faster.
- **SC-004**: The budget report passes with at least 10 % headroom on model size and working memory.
- **SC-005**: The board answers 100 prompts in a row over at least one hour without a reset and with stable free memory.
- **SC-006**: A developer goes from a fresh checkout and a blank NodeMCU to a running PoC in under 30 minutes using only the instructions and a pre-built model.

## Assumptions

- The boards on hand are ESP8266 NodeMCU v2/v3 with 4 MB flash. The SDK and toolchain for the ESP8266 are chosen during planning.
- The portable C runtime (`runtime/`) can be reused unchanged or with small platform adjustments; the ESP-IDF firmware for the ESP32 cannot be reused directly and needs a NodeMCU counterpart.
- Floating-point maths runs in software on the ESP8266. The speed targets above are estimates for the starter model and will be confirmed by measurement; if they can't be met, the plan records the measured values and the reason.
- Emulated testing (QEMU) as used for the ESP32 is not available for the ESP8266; hardware parity is checked on a real board.
- Losing context length (from 256 to 104 characters) lowers the maximum prompt and answer length; the starter knowledge base has short questions and answers, so this is acceptable for the PoC.
- The Chemielehrer model (spec 003) stays ESP32-sized and is not part of this PoC.
