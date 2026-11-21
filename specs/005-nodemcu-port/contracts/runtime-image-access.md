# Contract: Runtime access to the model image (word-access safe)

Extends [001 runtime-api](../../001-esp32-tiny-lm/contracts/runtime-api.md). Public function
signatures in `runtime/include/utiny.h` stay the same; behaviour changes as follows.

## Guarantee

Every read from the model image passed to `ut_model_open` is an **aligned 32-bit load**. This
holds on every platform, so the same code runs from ESP8266 mapped flash (which faults on byte
loads), ESP32 mapped flash and host memory.

| Area | Before | After |
|------|--------|-------|
| Header (64 B) | byte reads (`rd16`, `rd32`) | copied into RAM with 32-bit loads, then parsed |
| Meta JSON | `m->meta` points into the image | copied into `ut_model.meta_buf[256]` (NUL-terminated, longer meta → `UT_ERR_SIZE`); `m->meta` points to the copy |
| Alphabet, float tensors | direct pointers | unchanged pointers, read only via `ut_ld32` |
| int8 matrices, embeddings | byte loads | 4 weights per 32-bit load, unpacked little-endian |
| Payload CRC | byte loop | word loop; a tail that isn't a multiple of 4 is read with one aligned word and masked (exported files end 4-aligned, since every tensor is padded to 4) |

## Rules

- `ut_ld32(const void *p)` in `runtime/src/mathx.h` is the only way to read image memory.
  With `-DUT_IMAGE_ACCESS_CHECK` it asserts `((uintptr_t)p & 3) == 0`.
- `ut_model_open` additionally returns `UT_ERR_DIMS` if `d_model`, `d_ff` or `head_dim` is not
  a multiple of 4 (the exporter already guarantees this).
- Results are bit-identical to the previous runtime: integer dot products are unchanged and
  float operations keep their order. Verified by the existing golden tests (starter and tiny)
  before and after the change.
- `sizeof(ut_model)` grows by 256 bytes (meta copy); this counts toward static RAM.
