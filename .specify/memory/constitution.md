# UltraTiny Constitution

UltraTiny builds a tiny language model that is trained on a PC and runs fully offline on an
ESP32 microcontroller (inspired by Tiny-2.1, a ~367k-parameter character-level transformer
with 8-bit row-scaled weights running on DOS-era PCs).

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
  measured to be necessary or cheaper on the target.
- Weights MUST be read in place from flash (memory-mapped) where possible, not copied to RAM.

Rationale: predictable memory and timing on a device with no OS-level safety net.

### III. Reference Parity (NON-NEGOTIABLE)

- A Python reference implementation MUST replicate the exact quantized on-device math.
- The C inference code MUST be buildable and testable on the host (Linux) without hardware.
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

- **Target hardware**: classic ESP32 (Xtensa LX6, dual-core up to 240 MHz, single-precision
  FPU, no SIMD, 520 KB on-chip SRAM, no PSRAM assumed, 4 MB external flash).
- **Default budgets** (a feature spec MAY tighten them; loosening requires an amendment):
  - Model weights: ≤ 2 MB in a dedicated flash data partition, memory-mapped, never copied
    to RAM.
  - Runtime RAM for inference (arena + KV cache + activations): ≤ 128 KB, statically sized.
  - Firmware application image: fits the chosen partition table alongside the model partition.
  - Without PSRAM, nothing in the model design may rely on external RAM.
- **Firmware**: ESP-IDF (directly or via PlatformIO), C; host build via a standard C compiler
  (e.g. gcc/clang) for tests.
- **Training**: Python 3 with PyTorch and NumPy; MUST run on a CPU-only machine (GPU optional).
- **Interfaces**: the device exposes the model through a simple, documented text interface
  (e.g. serial console); additional interfaces are specified per feature.
- **Licensing**: project code is open source; third-party code and data MUST have compatible
  licenses, recorded in the repository.

## Development Workflow & Quality Gates

- Features follow the Spec Kit flow: specify → (clarify) → plan → tasks → implement.
- Every plan MUST include a Constitution Check covering Principles I–V.
- Every pull request MUST pass: host build of the runtime, unit tests, parity tests
  (Principle III), and the size/budget report (Principle I).
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

**Version**: 1.0.0 | **Ratified**: 2026-11-20 | **Last Amended**: 2026-11-20
