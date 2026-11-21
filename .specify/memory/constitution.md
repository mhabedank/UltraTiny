# UltraTiny Constitution

UltraTiny builds a tiny language model that is trained on a PC and runs fully offline on a
NodeMCU board (ESP8266 microcontroller), as a proof of concept that a language model fits on
one of the smallest Wi-Fi microcontrollers (inspired by Tiny-2.1, a ~367k-parameter
character-level transformer with 8-bit row-scaled weights running on DOS-era PCs).

## Core Principles

### I. Hard On-Device Budget (NON-NEGOTIABLE)

- Every feature spec MUST state the target board and explicit budgets: flash (model + firmware),
  internal SRAM, PSRAM (if any), and time per generated token.
- Model weights and runtime MUST fit those budgets with a documented headroom
  (default: ≥10% of each memory budget free).
- Budgets MUST be verified by a reproducible size report (binary size, static RAM, peak arena
  use) and, before a release, by a measurement on real hardware.
- A change that exceeds a budget MUST NOT be merged; raising a budget requires amending the
  spec with justification.

Rationale: on a microcontroller, memory is the product constraint; everything else is negotiable.

### II. Quantized, Allocation-Free Inference

- Weights MUST be stored quantized at ≤8 bits per weight (per-row or per-group scale);
  wider formats require measured justification in the plan.
- The on-device inference path MUST NOT allocate heap memory at runtime: all buffers come from
  a statically sized arena whose size is computed from the model header.
- Integer / fixed-point arithmetic is preferred; float use MUST be limited to places where it is
  measured to be necessary or cheaper on the target. The target has no FPU, so every float
  operation in the per-token path is software-emulated and MUST be justified by measurement.
- Weights MUST be read in place from flash (memory-mapped), not copied to RAM; the model MUST
  therefore fit, together with the firmware, in the flash window the target can map at once.

Rationale: predictable memory and timing on a device with no OS-level safety net.

### III. Reference Parity (NON-NEGOTIABLE)

- A Python reference implementation MUST replicate the exact quantized on-device math.
- The C inference code MUST be buildable and testable on the host (Linux) without hardware.
- Because no emulator for the target is used, parity on the device MUST be shown on a real
  board before a release (same golden cases, identical output text).
- Golden test vectors (input tokens → logits/next token) produced by the reference MUST pass
  against the C implementation within a stated tolerance (bit-exact for integer paths).
- Every change to model math, export format, or runtime MUST be covered by these parity tests
  before merge.

Rationale: bugs in embedded numerics are silent; parity tests are the only reliable oracle.

### IV. Reproducible Training & Export

- Training, data generation, and export MUST be scripted end to end; no manual steps.
- Runs MUST fix random seeds and record config, data version, and git commit alongside the
  checkpoint.
- The exported model binary MUST start with a magic number, a format version, and the
  hyperparameters needed to size the runtime; any layout change bumps the format version.
- Training data sources and their licenses MUST be recorded (e.g. `DATA_LICENSES.md`); data
  with unclear licensing MUST NOT be used.

Rationale: a tiny model is cheap to retrain, so results must be cheap to reproduce and compare.

### V. Simplicity & Portability

- The runtime is plain C (C99 or later) with no dependencies beyond the C standard library and
  the board SDK; SDK-specific code is isolated in a thin platform layer.
- Start with the smallest architecture that can meet the spec's quality target; added
  complexity (new layers, ops, tokenizers, accelerators) MUST be justified with measurements.
- Prefer one clear code path over configurable variants; YAGNI applies.

Rationale: small, portable code is easier to fit, verify, and port to other microcontrollers.

## Technical Constraints

- **Target hardware**: NodeMCU v2/v3 board with an ESP8266 (Xtensa LX106, single core,
  80/160 MHz, **no FPU**, no SIMD, ~80 KB data RAM of which roughly 40–50 KB is free at
  runtime, no PSRAM, 4 MB external flash of which about 1 MB can be memory-mapped at once).
- **Legacy hardware**: the classic ESP32 (specs 001–003) is no longer a target for new work.
  Its firmware MAY stay in the repository but MUST NOT constrain NodeMCU design decisions.
- **Default budgets** (a feature spec MAY tighten them; loosening requires an amendment):
  - Model weights: ≤ 700 KB in a dedicated flash area, memory-mapped, never copied to RAM.
  - Firmware image + model: together inside the flash window the ESP8266 can map at once
    (1 MB).
  - Runtime RAM for inference (arena + KV cache + activations): ≤ 40 KB, statically sized.
  - Time per token: first answer character ≤ 2 s after Enter, generation ≥ 5 chars/s.
  - Without PSRAM, nothing in the model design may rely on external RAM.
- **Firmware**: an ESP8266 SDK (ESP8266_RTOS_SDK or the Arduino core, directly or via
  PlatformIO), C; the choice is made and justified in the plan. Host build via a standard C
  compiler (e.g. gcc/clang) for tests.
- **Training**: Python 3 with PyTorch and NumPy; MUST run on a CPU-only machine (GPU optional).
- **Interfaces**: the device exposes the model through a simple, documented text interface
  (e.g. serial console); additional interfaces are specified per feature.
- **Licensing**: project code is open source; third-party code and data MUST have compatible
  licenses, recorded in the repository.

## Development Workflow & Quality Gates

- Features follow the Spec Kit flow: specify → (clarify) → plan → tasks → implement.
- Every plan MUST include a Constitution Check covering Principles I–V.
- Every pull request MUST pass: host build of the runtime, unit tests, parity tests
  (Principle III), the size/budget report against the NodeMCU budgets (Principle I), and,
  once NodeMCU firmware exists, a firmware build for the ESP8266.
- Changes to the model binary format MUST update the format version, the exporter, the
  runtime loader, and the parity vectors in the same change.
- Model quality is reported with a fixed evaluation set and metric defined in the spec, so
  results stay comparable across runs.

## Governance

- This constitution supersedes other project practices; conflicts are resolved in its favor.
- Amendments are made via pull request that updates this file, states the rationale, and
  describes any migration needed for existing specs or code.
- Versioning follows semantic versioning: MAJOR for removed or redefined principles, MINOR for
  added principles or materially expanded guidance, PATCH for clarifications.
- Plans and reviews MUST verify compliance; any deviation MUST be recorded with justification
  in the plan's Complexity Tracking section.

**Version**: 2.0.0 | **Ratified**: 2026-11-20 | **Last Amended**: 2026-11-21
