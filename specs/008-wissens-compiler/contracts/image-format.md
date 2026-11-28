# Contract: Knowledge Image Format (UTKI v1)

The knowledge image replaces the 006 fact table (UTFT v1, FR-010). It is written by
`training/src/ultratiny/knowledge/compile.py`, read by `runtime/src/knowledge.c` and by the Python
reference `training/src/ultratiny/knowledge/image.py`. Both readers MUST render identical bytes
(FR-014). Design: [research.md](../research.md) R5–R7.

## Placement

Unchanged from 006: flash offset `0x100000`, area 64 KB, file ≤ 58,982 B (90 %), read through the
`read(user, offset, buf, n)` callback with offset, `n` and `buf` 4-byte aligned. Flash command:
`make nodemcu-flash-facts FACTS=models/<topic>.utki`.

## Conventions

- Little-endian. All offsets are `u16` byte offsets from the start of the file (the file is
  < 65,536 B). Every section starts at a 4-byte-aligned offset; padding bytes are 0.
- Strings are NUL-terminated UTF-8 in the string area; a string reference is a `u16` offset
  relative to `off_strings`. Each distinct string is stored once.
- `NONE` = `0xFFFF` (absent string or section).
- Byte order of keys and values: `memcmp` order, a shorter string before a longer one with the same
  start (as in 006).

## Header (80 B)

| Offset | Type | Field | Rule |
|--------|------|-------|------|
| 0 | char[4] | magic | `"UTKI"` |
| 4 | u16 | version | `1` |
| 6 | u16 | header_size | `80` |
| 8 | char[16] | topic | topic id, NUL-padded, ≤ 15 bytes |
| 24 | u16 | schema_version | 1–65535 |
| 26 | u16 | n_classes | 1–8 |
| 28 | u16 | n_objects | 1–65535 |
| 30 | u16 | n_relations | 0–254 |
| 32 | u16 | n_views | 1–254 |
| 34 | u16 | n_answerable | answerable facts (F7), capped at 65535 |
| 36 | u16 | off_strings | |
| 38 | u16 | size_strings | |
| 40 | u16 | off_classes | n_classes × 4 B |
| 42 | u16 | off_objects | n_objects × 4 B |
| 44 | u16 | off_keyidx | n_objects × 2 B |
| 46 | u16 | off_relations | n_relations × 16 B |
| 48 | u16 | off_views | n_views × 12 B |
| 50 | u16 | off_texts | 6 × u16 |
| 52 | u32 | payload_size | file size − 80 |
| 56 | u32 | data_sha | first 4 bytes of the SHA-256 over all source files of the topic (display) |
| 60 | u32 | payload_crc | CRC-32 (IEEE) of bytes 80 … end |
| 64 | u8[12] | reserved | 0 |
| 76 | u32 | header_crc | CRC-32 of bytes 0–75 |

## Classes (4 B each)

| Offset | Type | Field |
|--------|------|-------|
| 0 | u16 | first object number |
| 2 | u16 | object count |

Classes are stored in schema order; their object ranges are contiguous and ascending.

## Objects (4 B each)

| Offset | Type | Field |
|--------|------|-------|
| 0 | u16 | key (string) |
| 2 | u16 | name (string) |

Objects are grouped by class, in the class's declared order. The object number is the position in
this table; the class follows from the class ranges; the *local index* is `number − first`.

## Key index (2 B each)

Object numbers sorted by key bytes. A key lookup is a binary search over this table.

## Relations (16 B each)

| Offset | Type | Field |
|--------|------|-------|
| 0 | u16 | name (string) |
| 2 | u8 | type: 0 text, 1 int, 2 dec, 3 enum, 4 ref |
| 3 | u8 | flags: bit0 `card many`, bit1 reverse present, bit2 `reverse many`, bit3 value IDs are 2 B, bit4 subject IDs are 2 B |
| 4 | u8 | subject class |
| 5 | u8 | target class (`ref`), else `0xFF` |
| 6 | u16 | n_values |
| 8 | u16 | off_values: n_values × u16, sorted by value bytes (for `ref`: by the target object's key); each entry is a string, or for `ref` an object number |
| 10 | u16 | off_forward: see below |
| 12 | u16 | off_reverse: posting lists by value ID, or `NONE` |
| 14 | u16 | reserved (0) |

Widths: value IDs are 1 B when `n_values ≤ 254` (absent = `0xFF`), else 2 B (absent = `0xFFFF`).
Subject IDs (local indices in the subject class) are 1 B when the class has ≤ 255 objects, else 2 B.

**Forward, `card one`**: a column with one value ID per object of the subject class, in local-index
order.

**Forward, `card many`**, and **reverse**: a posting-list block:

```text
u16 offsets[n + 1]     # n = objects in the subject class (forward) or n_values (reverse);
                       # offsets in entries, relative to the first entry
entries[]              # forward: value IDs, ascending; reverse: subject IDs, in class order
```

The entries of item `i` are `offsets[i] … offsets[i+1] − 1`. The block is 4-byte aligned.

## Views (12 B each)

| Offset | Type | Field |
|--------|------|-------|
| 0 | u16 | name (string) |
| 2 | u8 | kind: 0 forward, 1 reverse, 2 self, 3 profile |
| 3 | u8 | legacy letter (ASCII), 0 = none |
| 4 | u8 | relation index, `0xFF` for self/profile |
| 5 | u8 | class mask (bit i = class i) |
| 6 | u16 | template (string with slot bytes) |
| 8 | u16 | not_applicable (string with slot bytes), `NONE` = generic text |
| 10 | u16 | more (string with slot bytes), `NONE` = no continuation |

Views are stored in schema order. Legacy letters are unique.

## Slot bytes in templates

| Byte | Slot |
|------|------|
| `0x01` | `{name}` |
| `0x02` | `{key}` |
| `0x03` | `{v}` (value, or list) |
| `0x04` R | `{r:<relation>}`: single forward value of the relation with index R − 1 of the same object (R = index + 1, so the byte is never NUL) |
| `0x05` | `{n}` (number of items left out, decimal ASCII; only in `more`) |

The **prefix** of a view is every template byte before the first slot byte (non-empty, checked by the
compiler).

## Topic texts (6 × u16 at `off_texts`)

`unknown`, `not_applicable` (generic continuation after `{name}`), `fallback_sep`, `list_sep`,
`list_last`, reserved (`NONE`).

## Validation at boot (FR-011)

1. Magic, version, header_size, header_crc. Wrong magic or erased flash (`FF FF FF FF`) → `MISSING`;
   any other failure → `CORRUPT`.
2. Every offset and size lies inside `80 + payload_size`, every section is aligned, counts are in
   range, the class ranges are contiguous and add up to `n_objects`.
3. Payload CRC over the whole file, read in 128 B chunks.
4. Firmware only: topic check against the model meta (research R11) → `WRONG_TOPIC`.

Only `OK` answers queries. Lookup and rendering: [query.md](query.md).

## Size report

The compiler writes the size of each section to `build.json` (`header`, `strings`, `classes`,
`objects`, `keyidx`, `relations`, `values`, `columns`, `lists`, `views`, `texts`, `padding`).
