# Feature Specification: Observability for Device and Model

**Feature Branch**: `claude/observability-002`

**Created**: 2026-11-21

**Status**: Implemented

**Input**: User description: "ich brauche ein bisschen observability sowohl für die hardware in
qemu (arbeitsspeicher auslastung, CPU auslastung, ein paar timings) also auch observability fürs
model."

**Builds on**: [001-esp32-tiny-lm](../001-esp32-tiny-lm/spec.md) (board, budgets, console).

## User Scenarios & Testing *(mandatory)*

### User Story 1 - See how the device is doing (Priority: P1)

A developer runs the firmware in QEMU (or on a board), types `/stats` and sees free heap (now,
minimum since boot, largest block), free stack of the inference task, arena use, KV-cache fill,
CPU load per core, uptime, clock, and the timings of the last answer (prefill length, time to
first character, total time, characters/s, ms per character avg/min/max) plus a profile of where
the forward pass spends its time (embed, norm, qkv, attn, wo, ffn, head).

**Independent Test**: `make qemu`, ask a question, type `/stats`. All values appear, and:
heap free > 0 and ≤ 520 KB, minimum ≤ free, arena needed ≤ buffer, CPU load per core in 0–100 %,
KV position 1 after the answer, and the profile shares add up to 100 % (± rounding). That core 1
is near 100 % *while* generating is checked on hardware (quickstart Scenario F), because `/stats`
reports load since its previous call, idle time included.

**Acceptance Scenarios**:

1. **Given** a booted device, **When** the user types `/stats` before any question, **Then**
   system values are shown and "Letzte Antwort: noch keine".
2. **Given** an answered question, **When** `/stats` is typed, **Then** timings and the stage
   profile of that answer are shown.
3. **Given** an invalid model (HALT_ERROR), **When** `/stats` is typed, **Then** the system
   values and the model error are shown.

### User Story 2 - See how sure the model is (Priority: P1)

A developer types `/trace an`; after every answer the console prints one row per generated
character (position, character, probability, top-3 candidates, entropy in bit, ms) and a summary
(mean/min probability and where, mean entropy, context use). `/trace json` prints the same as
machine-readable `@ut {...}` lines for tools. `/trace aus` (default) restores the plain output.

**Independent Test**: `/trace an`, ask a demo question, check the table; `/trace aus`, ask again,
check the output is byte-identical to before.

**Acceptance Scenarios**:

1. **Given** `/trace an`, **When** an answer ends (by `<eos>`, `/max`, full context or Ctrl-C),
   **Then** the table covers exactly the characters produced (plus the `<eos>` decision, if any).
2. **Given** `/trace aus`, **When** an answer is produced, **Then** the output is byte-identical to
   001 (device parity scripts keep working).

### User Story 3 - Watch it live from the PC (Priority: P2)

A developer runs `make observe`: QEMU is started with the console on TCP, the demo questions are
sent, and a viewer shows every answer with characters coloured by probability, timings, the least
certain positions with alternatives, profile bars and system values; `--log` writes all events as
JSON lines. The same viewer works with a real board (`--port`) or the PC runtime (`--host`).

**Independent Test**: `make observe` ends with "Demo: N/N Antworten wie erwartet" and QEMU is gone.

### Edge Cases

- Ctrl-C during an answer: timings and trace cover the characters produced so far.
- Platform without clock / stats callbacks (host): in text, unknown values are left out or
  shown as `?`; in JSON they are `null`.
- Trace JSON lines exceed the UART speed: they are printed after the answer, so they do not
  distort the per-character timings.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: `/stats` MUST show heap free/minimum/largest block, free stack of the inference
  task, arena needed/buffer, KV position/context length, CPU load per core since the previous
  `/stats`, uptime and CPU clock, where the platform provides them.
- **FR-002**: `/stats` MUST show for the last answer: number of characters, end reason, prefill
  length, time to first character, total time, characters/s, ms per character (avg/min/max), and
  the share of each forward-pass stage.
- **FR-003**: `/trace aus|an|json` MUST switch the model trace; default `aus`.
- **FR-004**: Trace rows MUST contain position, character, probability (softmax at T = 1),
  top-3 candidates with probabilities, entropy in bit and time in ms.
- **FR-005**: With trace `aus`, the answer output (echo, answer, ` [abgebrochen]`, prompt), the
  banner and the output of all 001 commands except `/hilfe` MUST be byte-identical to feature 001.
  `/hilfe` additionally lists `/stats` and `/trace`.
- **FR-006**: Observability MUST NOT change any computed logit (parity, constitution III).
- **FR-007**: No heap allocation at inference time; trace buffers are static (≤ `UT_MAX_ANSWER`
  + 1 steps).
- **FR-008**: The JSON format MUST be documented ([contracts/observability.md](contracts/observability.md)).
- **FR-009**: `tools/observe.py` MUST connect via serial port, TCP, local process, or start QEMU
  itself, and write all events to a JSON-lines log on request.

### Budgets (constitution I)

The budgets are unchanged from [001](../001-esp32-tiny-lm/spec.md) and restated here.

| Budget | Limit | This feature |
|--------|-------|--------------|
| Target board | classic ESP32, 4 MB flash, 520 KB SRAM, **no PSRAM** (nothing may rely on external RAM) | unchanged |
| Flash: model | ≤ 2 MB data partition, ≥ 10 % headroom | unchanged (621,468 B) |
| Flash: firmware | app image ≤ 1 MB factory partition, ≥ 10 % headroom | measured 220,544 B (21.0 %) |
| SRAM: inference | arena + KV + activations ≤ 128 KB static, ≥ 10 % headroom | unchanged (79,888 B) |
| SRAM: additional static DRAM | trace buffer + run-time stats ≤ 8 KB | measured +4,608 B |
| Time per token | ≥ 10 characters/s (001 SC-002), first character ≤ 1 s (001 US1) | profiling + trace add ≤ 5 % (SC-003) |

SC-003 is a **release gate**, not a merge gate. Constitution I requires the measurement on real
hardware before a release; QEMU timings are emulated and cannot show it.

### Key Entities

- **SysStats**: platform values (heap, stack, CPU load, uptime, MHz); `< 0` = unknown.
- **TraceStep**: chosen token, top-3 tokens, probabilities (Q16), entropy (millibit), position,
  µs since the previous character.
- **StageProfile**: µs per forward-pass stage, accumulated per answer.
- **AnswerSummary**: snapshot of the last answer (characters, end reason, prefill, timings,
  profile copy).
- **TraceMode**: `aus` | `an` | `json`, default `aus`.

Fields and rules are defined in [data-model.md](data-model.md).

## Success Criteria *(mandatory)*

- **SC-001**: `/stats` and `/trace an` work in QEMU (shown in the PR).
- **SC-002**: Golden parity unchanged: host 24/24 bit-identical, QEMU 24/24 identical text.
- **SC-003**: Profiling plus trace cost ≤ 5 % generation time on real hardware (release gate,
  see Budgets).
- **SC-004**: Budget report passes with ≥ 10 % headroom.
