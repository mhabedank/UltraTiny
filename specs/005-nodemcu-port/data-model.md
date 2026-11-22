# Data Model: 005-nodemcu-port

Entities from the spec, with fields and validation rules. Entities that are unchanged from
spec 001 (Model file, Alphabet, Golden file, Evaluation set) are referenced, not repeated:
see [001 data-model](../001-esp32-tiny-lm/data-model.md).

## NodeMCU model configuration (`training/configs/nodemcu.toml`)

| Field | Value | Rule |
|-------|-------|------|
| `name` | `"nodemcu"` | written into the model meta JSON |
| `model.d_model / n_layers / n_heads / n_kv_heads / d_ff` | 128 / 4 / 4 / 1 / 384 | same as `starter.toml` |
| `model.ctx_len` | 104 | arena ≤ 36,864 B (40 KB − 10 %) per budget report formula (research R4) |
| `data.facts` | `data/facts/starter.tsv` | self-description facts updated for the NodeMCU (FR-010) |
| `data.max_answer_len` | 72 | `len(q) + len(a) + 3 ≤ ctx_len` (datagen `fits`) |
| `eval.demo_min / heldout_min` | 0.80 / 0.60 | SC-002 |

Derived: ~589k parameters, model file ~600 KB, arena 35,520 B.

## Board budget profile (`tools/budget_report.py`)

One profile per board; `--board` selects it (default `nodemcu`, constitution v2.0.0).

| Field | `nodemcu` | `esp32` (legacy) |
|-------|-----------|------------------|
| `model_max` | model area size: 688,128 B (672 KB) | 2,097,152 B |
| `arena_max` | 40,960 B | 131,072 B |
| `firmware_arena` | `UT_ARENA_MAX` of `firmware-nodemcu` (36,864 B) | 98,304 B |
| `firmware_max` | firmware area: 360,448 B (352 KB) | factory partition size |
| `mapped_window` | 1,048,576 B (firmware area + model area must fit) | – |
| `headroom` | 0.10 | 0.10 |

Validation: the report fails (exit 1) when any value has < 10 % headroom, when
`firmware_area + model_area > mapped_window`, or when the model's arena exceeds `firmware_arena`.

## Flash layout

See [contracts/flash-layout.md](contracts/flash-layout.md). Two regions inside the first 1 MB
(firmware area, model area); the model area start address is a single constant shared by the
linker script, the firmware and the flash command.

## Device status (console `/info`, `/stats`)

Unchanged fields from spec 001/002, plus for the NodeMCU:

| Field | Source | Notes |
|-------|--------|-------|
| `board` | constant `"NodeMCU (ESP8266)"` | also in the boot banner (spec US1 scenario 3) |
| `cpu_mhz` | `ESP.getCpuFreqMHz()` | 160 expected |
| `free_heap` | `ESP.getFreeHeap()` | stability check in `soak.py` (SC-005) |
| `free_stack` | `ESP.getFreeContStack()` | new; loop stack is 4 KB |
| `reset_reason` | `ESP.getResetReason()` | shows watchdog resets (FR-012) |
| per-core load | – | printed as `-` (single core) |

## State transitions

Unchanged console state machine from spec 001 (`BOOT → READY ⇄ GENERATING`, `HALT_ERROR` on an
invalid model). New boot check before `READY`: the model area must hold a valid image whose
arena fits `UT_ARENA_MAX`; otherwise `HALT_ERROR` with the existing error texts, no reboot loop.
