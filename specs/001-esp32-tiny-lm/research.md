# Research: Tiny Language Model Demo on a Classic ESP32

All Technical Context unknowns are resolved below. Format per item: Decision / Rationale /
Alternatives considered.

## R1. Model architecture and size

- **Decision**: Decoder-only, character-level transformer.
  - `d_model = 128`, `n_layers = 4`, `n_heads = 4` (head dim 32), **multi-query attention**
    (1 shared K/V head of dim 32), `d_ff = 384`, ReLU activation, pre-RMSNorm, learned absolute
    positional embeddings, tied input/output embedding, no biases.
  - Context length `ctx = 256` characters (prompt + answer).
  - ≈ 0.60 M parameters → ≈ 0.61 MB as int8 + per-row scales.
- **Rationale**:
  - Tiny-2.1 shows 367 k params (4 × 96) learn ~3,500 facts; ~2× capacity gives headroom for
    German umlauts, longer answers, and better generalization to rephrasings (SC-004).
  - Decode speed is bound by streaming all weights from flash once per token:
    0.61 MB at ~20–40 MB/s effective ≈ 15–30 ms/token → ≥ 25 chars/s, well above SC-002
    (10 chars/s). Compute ≈ 0.6 M MAC/token ≈ 3 M cycles ≈ 12 ms at 240 MHz.
  - MQA shrinks the KV cache 4× (see R3) at small quality cost for this size.
  - ReLU, RMSNorm and learned positions avoid transcendental functions other than `exp`
    (softmax), which simplifies bit-exact parity (R5).
- **Alternatives considered**:
  - Exact Tiny-2.1 size (4 × 96, 367 k): fits easily, kept as the fallback config if speed or
    RAM measurements disappoint.
  - 6 × 128 (1.2 M params): ~2× slower decode, larger KV cache; rejected for v1.
  - RNN/GRU: no KV cache, but worse quality per parameter on fact recall; rejected.
  - RoPE: needs sin/cos tables and more parity surface; learned positions are cheap at ctx 256.

## R2. Alphabet / tokenization (German)

- **Decision**: Fixed character alphabet of ≤ 96 symbols, stored in the model file:
  - special tokens `<pad> <bos> <sep> <eos> <unk>`
  - space, `a–z`, `A–Z`, `0–9`, `ä ö ü Ä Ö Ü ß`
  - punctuation `. , ; : ! ? - ' " ( ) / % + = & °`
  - The device decodes UTF-8 from the serial line into code points and maps them via a sorted
    table; unknown code points map to `<unk>` and are reported once (spec edge case).
- **Rationale**: Character-level keeps vocab tiny (embedding ≈ 12 k params); UTF-8 handling on
  the device is a few dozen lines.
- **Alternatives considered**: BPE/subword (shorter sequences but a vocab of ≥ 1 k tokens costs
  RAM/flash and complicates the tokenizer); bytes (umlauts would cost 2 tokens each).

## R3. RAM budget (≤ 128 KB inference memory)

- **Decision**: Static arena sized from the model header:

  | Buffer | Size |
  |--------|------|
  | KV cache, int8, MQA: 4 layers × 2 × 256 pos × 32 dims | 64 KB |
  | KV scales, float32 per position/layer/K-or-V | 8 KB |
  | Activations (x, normed x, q, ffn hidden, attn scores, logits; float32 + int8 copies) | ≈ 6 KB |
  | **Total** | **≈ 78 KB** (61% of budget; ≥ 10% headroom ✔) |

- **Rationale**: Full multi-head float32 KV would need 1 MB; MQA + int8 KV brings it to ~72 KB.
- **Alternatives considered**: float16 KV (128 KB, no headroom); shorter context of 128
  (too short for question + 200-char answer per FR-006).

## R4. Numerics on the device

- **Decision**:
  - Weights int8 with one float32 scale per output row.
  - Activations are quantized to int8 per vector (dynamic absmax scale) right before each
    matmul; int8 × int8 → int32 accumulation; result rescaled to float32.
  - Attention scores q·k computed as int8 × int8 → int32; softmax in float32; weighted sum
    over V done as float32 × int8 with a fixed sequential accumulation order.
  - RMSNorm, residual adds, softmax in float32 (classic ESP32 has a hardware single-precision
    FPU, so these are cheap); `exp` is a project-owned polynomial approximation (no libm).
  - Greedy argmax decoding by default; optional sampling uses a project-owned xorshift PRNG.
- **Rationale**: Integer matmuls are exact and order-independent, which makes the dominant part
  of the math trivially bit-exact. The remaining float ops are few, use only IEEE-exact
  operations (+, −, ×, ÷, sqrt) plus our own `exp`, so they can be reproduced exactly.
- **Alternatives considered**: Fully fixed-point (CMSIS-style requantization): more code,
  harder to debug, no speed benefit on a core with an FPU. Pure float32 with int8 weights:
  summation-order differences break bit-exact parity.

## R5. Reference parity strategy (Constitution III)

- **Decision**:
  - `reference.py` (NumPy, float32) reimplements R4 exactly: same quantization rounding
    (round-half-away-from-zero), same `exp` polynomial, sequential float reductions via
    `np.cumsum(..., dtype=np.float32)[-1]` or explicit loops.
  - C is compiled with `-ffp-contract=off -fno-fast-math` and float literals only
    (`-fsingle-precision-constant`) on host and device.
  - Golden vectors: JSON with prompts, per-step argmax tokens and logits for (a) a tiny
    random-weight test model committed to the repo and (b) the released model.
  - Pass criteria: generated tokens identical; logits within 1e-5 absolute (expected 0).
- **Rationale**: Logit-exact match on host and device guarantees identical text (SC-006).
- **Alternatives considered**: Testing only against PyTorch fake-quant (not exact); running the
  C code from Python via ctypes as "reference" (would not be an independent oracle).

## R6. Prompt latency (SC-001: first answer char ≤ 1 s)

- **Decision**: **Incremental prefill while typing.** Each character the user types is fed into
  the model immediately (KV cache grows as they type); Backspace rolls the position back by one.
  On Enter only `<sep>` remains to process, so the first answer character appears after
  ~2 token-steps (≈ 70 ms). Pasted input is processed at model speed with batched prefill
  (chunks of 16 tokens reuse each weight row) as a fallback.
- **Rationale**: Decode is flash-bandwidth bound; batching amortizes weight reads.
  Typing-time prefill makes the latency target independent of prompt length.
- **Alternatives considered**: Prefill only after Enter (80-char prompt ≈ 1–3 s, misses SC-001);
  dual-core matmul split (kept as an optional optimization task if measurements require it).

## R7. Flash layout and model flashing

- **Decision**: Custom partition table on 4 MB flash:

  | Name | Type | Offset | Size |
  |------|------|--------|------|
  | nvs | data/nvs | 0x9000 | 24 KB |
  | phy_init | data/phy | 0xF000 | 4 KB |
  | factory | app | 0x10000 | 1 MB |
  | model | data/0x40 (custom) | 0x110000 | 2 MB |
  | (free) | – | 0x310000 | ~0.9 MB |

  - The model partition is memory-mapped with `esp_partition_mmap` (read-only, data cache).
  - Model files are flashed with `parttool.py --partition-name model write_partition` (wrapped
    in a `make flash-model` target), independent of the firmware (User Story 3).
- **Rationale**: Meets constitution budget (model ≤ 2 MB, never copied to RAM); app stays small.
- **Alternatives considered**: Embedding the model in the firmware image (forces rebuilds on
  every model change); SPIFFS/LittleFS (file system overhead, no zero-copy mmap).

## R8. Firmware toolchain

- **Decision**: ESP-IDF v5.x (latest stable at implementation time, pinned in CI via the
  `espressif/idf` Docker image), C11, build with `idf.py`. Wi-Fi and Bluetooth disabled in
  `sdkconfig.defaults` (`CONFIG_BT_ENABLED=n`, Wi-Fi never initialized). Console on UART0
  via the board's USB-UART bridge at 115200 baud; `CONFIG_ESP_CONSOLE_UART`.
- **Rationale**: Official SDK, first-class `esp_partition_mmap`, works on macOS (developer's
  M3) and Linux/CI. 115200 baud ≈ 11 KB/s ≫ 25 chars/s.
- **Alternatives considered**: Arduino core (hides partition/mmap details, less reproducible);
  PlatformIO (fine wrapper, but adds a layer; can be added later).

## R9. Portable runtime build

- **Decision**: `runtime/` is plain C11 with a single `CMakeLists.txt` that registers an
  ESP-IDF component when `ESP_PLATFORM` is set and otherwise builds a static library, a host CLI
  (`utiny-host`) and CTest tests. Platform-specific code (mmap, UART, timers) lives only in
  `firmware/main/`.
- **Rationale**: Constitution V (thin platform layer) and III (host-testable).
- **Alternatives considered**: Separate host and device copies of the code (drift risk).

## R10. Training stack on the M3 Mac

- **Decision**: Python 3.12, PyTorch ≥ 2.5 with the **MPS** backend (Apple GPU) when
  `torch.backends.mps.is_available()`, else CPU; NumPy for reference/export; project managed with
  `uv` (`pyproject.toml` + `uv.lock`). Seeds fixed for Python, NumPy and torch; run metadata
  (config, data hash, git commit, device) saved next to the checkpoint.
- **Training recipe**: AdamW, cosine LR, batch of packed Q/A sequences, loss only on answer
  tokens; then **quantization-aware fine-tuning** (fake-quant weights + activations + KV,
  straight-through estimator) for the last ~10% of steps if the quantized eval drops > 2 pp.
- **Rationale**: 0.6 M params × ~50 M training tokens is minutes-to-an-hour on an M3 GPU,
  inside the 2 h target; MPS is the native GPU path on Apple Silicon.
- **Alternatives considered**: MLX (fast on Apple Silicon but no CPU fallback on Linux/CI);
  JAX (weaker macOS GPU support).

## R11. Knowledge base and data generation (German, license-clean)

- **Decision**:
  - Facts stored as TSV files in `training/data/facts/` grouped by topic, each row
    `relation \t subject \t object \t source`.
  - Topics (target ≈ 3,000 facts): capitals and continents of countries, German federal states and
    their capitals, big German cities/rivers/mountains, chemical elements (symbol, atomic number),
    planets and moons, units/physics basics, famous inventions/inventors, and a hand-written
    set about the ESP32 and this project ("Wer bist du?").
  - Structured facts come from a **committed snapshot of Wikidata (CC0)** queries; hand-written
    facts are original (MIT). Sources/licenses listed in `DATA_LICENSES.md`.
  - `datagen.py` expands each relation through 8–20 German question templates and 1–3 answer
    templates, with case/punctuation noise and typos; templates are split train/held-out so SC-004
    measures unseen phrasings.
- **Rationale**: CC0 + own text = no license risk (Constitution IV); templates give the
  "many phrasings per fact" recipe that worked for Tiny-2.1.
- **Alternatives considered**: German Wikipedia text (CC BY-SA, attribution/share-alike burden,
  and free text is not Q&A); generating paraphrases with a large LLM (reproducibility and
  license questions).

## R12. Evaluation and budget reporting

- **Decision**:
  - `eval.py` runs the **quantized NumPy reference** (not the float model) on: (a) the demo prompt
    list (SC-003, exact/near-exact match = normalized edit distance ≤ 0.1), (b) held-out
    phrasings (SC-004).
  - `tools/budget_report.py` combines `idf.py size` output, the model header and arena size into a
    Markdown/JSON report and fails if any budget headroom < 10% (Constitution I).
  - On-device timing (`/info` command) prints chars/s and first-char latency (SC-001/002).
- **Rationale**: Evaluating the exact deployed math avoids surprises after quantization.

## R13. CI

- **Decision**: GitHub Actions with three jobs: `python` (ruff + pytest on CPU, tiny config),
  `runtime-host` (CMake build, CTest, parity vs golden vectors), `firmware` (`idf.py build` in the
  pinned `espressif/idf` image + budget report).
- **Rationale**: Enforces the constitution's quality gates on every PR without hardware.
