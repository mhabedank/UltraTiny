# Research: 005-nodemcu-port

All "NEEDS CLARIFICATION" items of the Technical Context are resolved here. Numbers marked
*estimate* are derived from the code and datasheet-level facts and MUST be replaced by
measurements on a real board (tasks for T-Measure in `tasks.md`).

## R1 – Board SDK

- **Decision**: Arduino core for ESP8266 (3.1.x), built with PlatformIO (`platform =
  espressif8266`, `board = nodemcuv2`, versions pinned in `firmware-nodemcu/platformio.ini`).
  The portable C runtime (`runtime/`) is compiled unchanged as C; the platform layer is one small
  C++ file (`main.cpp`) that only wires UART, clock and flash address into the existing
  `ut_console_io` callbacks.
- **Rationale**: actively maintained, well-documented memory layout (custom linker script),
  one-command build/flash (`pio run -t upload`), easy CI (`pip install platformio`), and the most
  common way NodeMCU boards are used, so makers can follow the quickstart.
- **Alternatives considered**:
  - *ESP8266_RTOS_SDK 3.4* (IDF-like, closest to the existing ESP-IDF firmware): in maintenance
    mode since 2021, older toolchain, fewer CI images; its IDF-style structure gives no real
    advantage because only ~150 lines of platform code are ported.
  - *ESP8266 NONOS SDK*: deprecated by Espressif.
  - *NodeMCU Lua firmware*: interpreted, cannot run the C runtime within the RAM budget.

## R2 – Where the model lives in flash

- **Facts**: the ESP8266 maps only the first 1 MB of flash into the address space
  (`0x40200000`–`0x402FFFFF`); the firmware runs from the same window.
- **Decision**: a custom linker script splits the first megabyte (provisional numbers, checked
  by the budget report – see [contracts/flash-layout.md](contracts/flash-layout.md)):
  - `0x000000`–`0x057FFF` (352 KB): bootloader + firmware image
  - `0x058000`–`0x0FFFFF` (672 KB): model area, mapped at `0x40258000`
- **Rationale**: keeps weights in place (Principle II), keeps the 001 behaviour "flash a new model
  without rebuilding the firmware" (`esptool.py write_flash 0x58000 model.utny`), and leaves ≥10 %
  headroom for both the starter-sized model (~600 KB) and a typical Arduino firmware without
  Wi-Fi use (~260–300 KB, *estimate*).
- **Alternatives considered**: model compiled into the firmware as a `PROGMEM` array (simple,
  but every model change needs a rebuild and the firmware/model budgets merge); model above 1 MB
  read with `spi_flash_read` into RAM buffers (violates "read in place", slower, needs extra RAM).

## R3 – 32-bit-only access to mapped flash

- **Facts**: the ESP8266 flash cache only supports aligned 32-bit loads. A byte or 16-bit load
  from the model area raises exception 3 (LoadStoreError). The current runtime reads int8 weights,
  embeddings, header fields, the meta string and the CRC byte by byte.
- **Decision**: make the runtime "word-access safe" for the model image, on all platforms:
  - All reads from the model image go through one macro/inline `ut_ld32(p)` (aligned 32-bit load).
  - `ut_dot_i8` / `ut_matvec` and the embedding lookup unpack four int8 weights per 32-bit load
    (little-endian, as the format already is). Integer results are identical, so parity holds.
  - `ut_crc32` processes the payload word by word.
  - `ut_model_open` copies the 64-byte header and the meta JSON (≤ 256 bytes) into RAM; the
    alphabet (uint32) and float tensors are already aligned and are read via `ut_ld32`.
  - A host test build (`UT_IMAGE_ACCESS_CHECK`) asserts alignment in `ut_ld32`, and a lint check
    fails if code dereferences model-image pointers outside the accessor.
- **Rationale**: no format change (FR-007), every tensor and row is already 4-byte aligned
  (contract: model-format.md, all `cols` are multiples of 4), and the ESP32 build keeps working.
- **Alternatives considered**: the Arduino core's "non-32-bit access" exception handler (emulates
  byte loads in an exception, orders of magnitude too slow for the per-token path); copying each
  weight row to RAM before use (extra copy per row, no benefit over word loads).

## R4 – Context length

- **Measured on the starter knowledge base** (all train + held-out pairs, `<bos> q <sep> a <eos>`):
  2,578 pairs, longest 121 positions, median 78, longest answer 72 characters.

  | ctx_len | Pairs that fit | Arena (budget report formula) | Share of 40 KB |
  |---------|----------------|-------------------------------|----------------|
  | 96      | 97.2 %         | 33,184 B                      | 81.0 %         |
  | **104** | **99.4 %**     | **35,520 B**                  | **86.7 %**     |
  | 112     | 99.8 %         | 37,856 B                      | 92.4 % (fails headroom) |
  | 128     | 100 %          | 42,528 B                      | 103.8 % (over budget) |

- **Decision**: `ctx_len = 104`, `max_answer_len = 72`. Pairs that don't fit are dropped by the
  existing `fits()` filter in datagen (0.6 %).
- **Rationale**: the largest context that keeps ≥10 % arena headroom.

## R5 – RAM map

- **Facts**: ~80 KB DRAM in total. An Arduino sketch with Wi-Fi switched off starts with roughly
  50 KB free heap (*estimate*, core and SDK keep the rest). The sketch loop runs on a 4 KB stack.
- **Decision**:
  - Static (`.bss`): arena 35,520 B (sized from the model header at build time, `UT_ARENA_MAX =
    36 KB`), `ut_model` (~1.7 KB), `ut_ctx`, `ut_console` (~1.2 KB), header/meta copies (~0.3 KB).
  - Wi-Fi off at boot (`WiFi.mode(WIFI_OFF)` + forced sleep), so the radio uses no RAM buffers.
  - The firmware prints free heap and free stack (`ESP.getFreeHeap()`,
    `ESP.getFreeContStack()`) in `/info` and `/stats`; the budget report reads static RAM from
    the linker map.
- **Fallback if RAM is short**: Arduino's MMU option "16 KB cache + 48 KB IRAM" yields a second
  16 KB heap in IRAM (32-bit access only), usable for the int8 KV cache.

## R6 – No FPU: arithmetic and parity

- **Facts**: the LX106 has no FPU; GCC emits calls to libgcc/ROM soft-float routines, which are
  IEEE-754 single precision with round-to-nearest-even, the same as SSE on the host. The runtime
  already builds with `-ffp-contract=off -fno-fast-math -fsingle-precision-constant` and has its own
  `ut_expf`; `sqrtf` is correctly rounded by IEEE in newlib and glibc.
- **Decision**: keep the math unchanged; build the runtime with the same flags on the ESP8266.
  Parity is shown on a real board with the existing golden file and `tools/device_parity.py`
  (SC-001).
- **Rationale**: changing the math (fixed point) would require a new reference, new golden
  vectors and a format bump; not justified until measurements show float is the bottleneck.

## R7 – Speed estimate and risk (SC-003)

- **Estimate per token** at 160 MHz, mid-context (*estimate*): int8 MACs ~600k × ~8 cycles ≈ 30 ms;
  streaming ~600 KB of weights through the 32 KB flash cache ≈ 30–60 ms; soft-float attention and
  scaling ≈ 25–30 ms. Total ≈ 90–120 ms → **~8–11 chars/s** (meets ≥ 5 chars/s).
- **Risk**: the first answer character needs the whole prompt to be fed first. A 40-character
  prompt ≈ 3.5–5 s, which would **miss the 2 s budget** for longer prompts; prompts of up to about
  15–20 characters would meet it.
- **Decision**: measure first, then decide (gate G-Speed in plan.md):
  1. Early hardware spike: run the current starter model (ctx 256 doesn't fit, so a ctx-104
     build) and record per-token time and the split between flash streaming, int8 and float.
  2. If the first character takes > 2 s for demo prompts, apply in this order: run at 160 MHz;
     hot loops in IRAM; batched prompt prefill (feed 2 prompt tokens per weight pass, bit-identical
     per token, costs ~4.5 KB arena per extra token, so it needs the IRAM heap from R5).
  3. If it still misses, record the measured values and propose a budget amendment (Principle I),
     instead of merging over budget.
- **Alternatives considered**: shrinking the model (worse answers, retraining, against the
  clarified scope "starter model").

## R8 – Watchdog and responsiveness

- **Facts**: the ESP8266 software watchdog fires after ~3.2 s without `yield()`, the hardware
  watchdog after ~8 s.
- **Decision**: `loop()` calls `ut_console_poll` once and returns (the core feeds the watchdogs
  between iterations, plus an explicit `yield()`). The console feeds every typed character to the
  model inside `poll`, so the platform's `read_byte` hands out at most one byte per `loop()`; a
  pasted prompt waits in a 512-byte UART RX buffer instead of running dozens of forward passes in
  one call. No call blocks longer than one forward pass (~0.1 s). The abort key is checked
  between tokens, as on the ESP32.

## R9 – Testing without an emulator

- **Decision**:
  - Host: existing CTest suite + a new ctest target built with `UT_IMAGE_ACCESS_CHECK` (R3),
    golden parity for the new NodeMCU model.
  - CI: new job `firmware-nodemcu` (`pio run`) plus the budget report with `--board nodemcu`.
    The ESP32 `firmware` job stays, so the legacy build doesn't silently break (constitution v2:
    "MAY stay").
  - Hardware: `tools/device_smoke.py`, `tools/device_parity.py`, `tools/soak.py` are serial-only
    and board-agnostic; they get a `--board nodemcu` default for flashing commands only.
- **Alternatives considered**: an ESP8266 QEMU fork (unmaintained, not reliable enough for parity).

## R10 – Observability (spec 002) on the NodeMCU

- **Decision**: `/info` and `/stats` keep their format; values the ESP8266 can't provide (per-core
  CPU load, second core) are printed as `-`. Stage profiling uses `micros()`. `/trace` works
  unchanged because it only uses the clock callback.

## R11 – Board identification and flashing

- **Decision**: the quickstart identifies supported boards by `esptool.py flash_id` (chip
  ESP8266EX, 4 MB flash) and the USB chip (CP2102 or CH340, drivers linked). Flashing:
  `pio run -t upload` for the firmware, `esptool.py write_flash 0x58000 models/nodemcu.utny` for
  the model (wrapped as `make nodemcu-flash-model`).
