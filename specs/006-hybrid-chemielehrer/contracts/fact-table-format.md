# Contract: Fact Table Format (UTFT v1)

The fact table holds the verified facts and answer templates. It is written by
`training/src/ultratiny/facttable.py`, read by `runtime/src/facts.c` and by the Python reference.
Both MUST render identical bytes (research R11).

## Placement

| Item | Value |
|------|-------|
| Flash offset (NodeMCU) | `0x100000` (first byte after the memory-mapped megabyte) |
| Area | 64 KB (`0x100000`–`0x10FFFF`), `UT_FACTS_AREA_SIZE 0x10000` |
| Budget | file ≤ 58,982 B (90 % of the area). Checked by the builder and `tools/budget_report.py`. |
| Access | `read(user, offset, buf, n)` callback with offset, `n` and `buf` 4-byte aligned. NodeMCU: `ESP.flashRead`; host: memory buffer. |
| Flash command | `make nodemcu-flash-facts FACTS=models/<name>.utft` (`esptool write_flash 0x100000`). |

The layout of 005 (firmware 0x0–0x57FFF, model 0x58000–0xFFFFF, FS from 0x300000) is unchanged.

## File layout

All integers are little-endian `u32`. Every section starts at a 4-byte-aligned offset. Offsets are from
the start of the file.

### Header (64 B)

| Offset | Field | Rule |
|--------|-------|------|
| 0 | magic | `"UTFT"` |
| 4 | version | `1` |
| 8 | header_size | `64` |
| 12 | n_types | 1–52 |
| 16 | n_objects | 1–4096 |
| 20 | n_records | 0–65535 |
| 24 | types_off | Start of the type table (16 B per entry) |
| 28 | objects_off | Start of the object table (12 B per entry), sorted by key bytes (`memcmp`, case-sensitive; shorter key first when one key is a prefix of the other) |
| 32 | records_off | Start of the record table (8 B per entry), sorted by (object index, type code) |
| 36 | strings_off | Start of the string area: NUL-terminated UTF-8 |
| 40 | strings_size | Size of the string area in bytes |
| 44 | payload_size | File size − 64 |
| 48 | payload_crc | CRC-32 (IEEE, as for UTNY) of bytes 64 … end |
| 52 | data_sha | First 4 bytes of the SHA-256 of the source data, for display only |
| 56 | reserved | 0 |
| 60 | header_crc | CRC-32 of bytes 0–59 |

### Type entry (16 B)

| Offset | Field |
|--------|-------|
| 0 | `code` (u8, ASCII letter) |
| 1 | `flags` (u8): bit0 `needs_value`, bit1 `reverse` |
| 2 | `kinds` (u8 bit mask): 1 element, 2 compound, 4 acidbase, 8 reaction, 16 test |
| 3 | `reverse_of` (u8 code, 0 if none) |
| 4 | `template` (u32 string offset, relative to strings_off) |
| 8 | `not_applicable` (u32 string offset, `0xFFFFFFFF` = generic text) |
| 12 | reserved (u32, 0) |

### Object entry (12 B)

| Offset | Field |
|--------|-------|
| 0 | `key` (u32 string offset) |
| 4 | `name` (u32 string offset) |
| 8 | `kind` (u8), 3 B padding |

### Record entry (8 B)

| Offset | Field |
|--------|-------|
| 0 | `object` (u16 index into the object table) |
| 2 | `type` (u8 code), 1 B padding |
| 4 | `value` (u32 string offset) |

### Templates in the string area

Slots are stored as control bytes, so neither side needs a parser for `{…}`:

| Byte | Slot |
|------|------|
| `0x01` | `{name}` |
| `0x02` | `{key}` |
| `0x03` | `{v}` (value of this type for the object) |
| `0x04` X | `{X}`: value of type X for the same object (the next byte is the type code) |

The **prefix** is every byte before the first control byte.

## Validation at boot (FR-013)

Status values are `OK`, `MISSING` (magic is `FF FF FF FF` or not `UTFT`), and `CORRUPT` (wrong version,
header CRC, size or offsets, or payload CRC). The checks:

1. Magic, version, header_size and header_crc.
2. All offsets and sizes lie inside `payload_size + 64` and the area, and are aligned.
3. Payload CRC over the whole file, read in 128 B chunks.

Without status `OK`, function output is answered with the "fact table missing" text (function-output.md).

## Lookup (deterministic, identical in C and Python)

Given type code `t` and key `k` (bytes):

1. Find the type entry with `code == t`. If there is none, render `UNKNOWN`.
2. If `reverse`: scan the records with `type == reverse_of` for `value == k` (byte-equal). On a match,
   the object is that record's object; otherwise render `UNKNOWN`.
3. Otherwise: binary search the object table for `key == k`. If there is none, render `UNKNOWN`.
4. If the object's kind is not in `kinds`: render `not_applicable` (or the generic text).
5. If `needs_value`: binary search the records for (object, `t`). If there is none, render `not_applicable`.
6. Render the template. A `{X}` slot whose record is missing renders `?`. The builder forbids this for
   shipped tables, and the check is only a safety net.

Fixed texts (stored in C and Python, not in the table):
- `UNKNOWN` = `Das weiß ich leider nicht.`
- generic not applicable = `Dazu habe ich zu ` + name + ` keine Angabe.`
- `MISSING`/`CORRUPT` = `Die Faktentabelle fehlt, Faktenfragen gehen gerade nicht.`

## RAM use (NodeMCU)

- One static 128 B read buffer and the ≤ 16 B key buffer in the console. The handle stores the header
  fields (≈ 48 B).
- No heap use and no float.
- A binary search over ≤ 4096 objects needs ≤ 12 probes of 2 reads each.
