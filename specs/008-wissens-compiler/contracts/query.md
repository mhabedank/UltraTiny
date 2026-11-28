# Contract: Query, Rendering and Console

How a query becomes printed text, identical in `runtime/src/knowledge.c` and
`training/src/ultratiny/knowledge/image.py` (FR-014). The image layout is in
[image-format.md](image-format.md). The function output itself (token grammar, UTNY v2) is
unchanged from [006 function-output.md](../../006-hybrid-chemielehrer/contracts/function-output.md).

## Lookup (deterministic)

Input: a view (found by legacy letter or by name) and key bytes `k`.

1. **Status.** If the image status is not `OK`, the outcome is `missing`.
2. **Find the subject.**
   - `forward`, `self`, `profile`: binary search of the key index for `k`. Not found → `unknown`.
     Found → object `o`. If the class of `o` is not in the view's class mask (forward: the relation's
     subject class) → `na`.
   - `reverse`: binary search of the relation's value table for `k` (for `ref`: the target object's
     key). Not found → `unknown`. Found → value ID `x`; the subjects are the entries of posting
     list `x`. An empty list → `unknown`.
3. **Collect the value.**
   - `forward`, `card one`: column entry of `o`; absent → `na`.
   - `forward`, `card many`: posting list of `o`; empty → `na`.
   - `reverse`: the subject list from step 2 (`{name}` = first subject's name).
   - `profile`: every `{r:R}` slot needs a single forward value of `R` for `o`; any missing → `na`.
4. **Render** (below). Outcome `fact`.

A value renders as its string; a `ref` value renders as the target object's name.

## Rendering

- **Prefix**: template bytes before the first slot byte. The console prints it as soon as the view is
  known (006 behaviour).
- **Rest** (outcome `fact`): the template after the prefix, with slots replaced.
- **`na`**: the view's `not_applicable` expanded (slots `{name}`, `{key}`), or, if `NONE`,
  `name + texts.not_applicable`. It continues the prefix.
- **`unknown`**: if a prefix was printed, `texts.fallback_sep + texts.unknown`; otherwise
  `texts.unknown`.
- **`missing`**: the firmware text `Die Faktentabelle fehlt, Faktenfragen gehen gerade nicht.`
  (no prefix is printed, because no view is known).

### Lists

For `{v}` with items `i1 … in` (n ≥ 1):

1. `A` = byte length of the whole answer with `{v}` replaced by nothing; budget `B = 100 − A`.
2. `full` = `i1` if n = 1; otherwise `i1 + sep + i2 + … + sep + i(n−1) + last + in`, with
   `sep = texts.list_sep`, `last = texts.list_last`.
3. If `len(full) ≤ B`, render `full`.
4. Otherwise render `L(k) = i1 + sep + … + sep + ik + more(n − k)` for the largest `k ≥ 1` with
   `len(L(k)) ≤ B`, where `more(m)` is the view's `more` text with `{n}` = `m` in decimal ASCII.
   The compiler guarantees that `L(1)` fits for every list in the image (FR-004); the reader never
   prints more than 100 bytes for an answer.

Item order: forward `card many` in value-table order; reverse in class order (`order_by`).

## Console: function output (unchanged behaviour)

The 006 state machine stays (`<fn>` → letter → key → end). Only the lookup behind it changes:

| Event | Action |
|-------|--------|
| letter arrives, image `OK`, letter mapped | look up the view, print its prefix |
| letter not mapped | remember "unknown"; print nothing yet |
| end (`<eos>`, 12 key chars, `/max`, end of context) | print rest / `na` / `unknown` / `missing` as above |

Tokens, statistics and `/trace` are unchanged; parity of 006 golden cases (`printed`) holds as long
as the compat check (research R10) passes.

## Direct query command

```text
/wissen                         → topic overview
/wissen <letter> <key>          → view by legacy letter      e.g. /wissen O Cu
/wissen <view> <key>            → view by name               e.g. /wissen ordnungszahl Cu
                                                             e.g. /wissen ordnungszahl< 29
```

- The first argument is a view name if it is longer than one character, else a legacy letter.
- The key is the rest of the line after the single space that follows the first argument (keys and
  reverse values may contain spaces). Empty key → usage line.
- Output: the full answer (prefix + rest) on one line, rendered exactly as above, then the prompt.
- With `/trace an`, a second line `wissen: <outcome> <µs> us` follows (lookup and rendering time,
  SC-005).
- Unknown view name or letter → `texts.unknown`.

Overview (`/wissen` alone):

```text
Thema chemie, Schema 1, 3070 Fakten, data a1b2c3d4
Ansichten: ordnungszahl (O), ordnungszahl< (o), atommasse (M), …, familie<, …
```

## `/info` and boot lines

```text
Wissen: OK v1, Thema chemie (Schema 1), 3070 Fakten, data a1b2c3d4
Wissen: fehlt (make nodemcu-flash-facts)
Wissen: defekt (CRC)
Wissen: falsches Thema (Bild schach, Modell chemie)
```

`/info` adds `, Thema nicht geprüft` when the model meta has no `topic` (research R11). The line
replaces `Faktentabelle: …`; `tools/devlib.py` and `bench/board.py` parse the new form.

## Host tool

- `utiny-host --model M --facts IMAGE [--golden G | --console | --prompt P]`: as in 006; `IMAGE` is a
  `.utki` file, loaded into a 64 KB area filled with `0xFF`; unaligned reads trap (alignment check).
- `utiny-host --facts IMAGE --kb-cases CASES.tsv`: runs every query of a cases file through the C
  engine and compares the printed bytes (no model needed).
- `utiny-host --facts IMAGE --query "<view> <key>"`: prints one answer, as `/wissen`.

## Cases file (golden queries)

Written by `ut knowledge cases` for each topic (FR-014):

```text
view	key	outcome	answer
O	Cu	fact	Die Ordnungszahl von Kupfer ist 29.
ordnungszahl<	29	fact	Die Ordnungszahl 29 hat Kupfer.
O	Xx	unknown	Die Ordnungszahl von – Das weiß ich leider nicht.
```

It covers every view with at least one `fact`, one `na` (where possible), one `unknown` and every
shortened list. The Python reference produces it; the C engine (host and board) must match it byte
for byte.

## Python reference API (`ultratiny.knowledge.image`)

| Function | Returns |
|----------|---------|
| `Image(data: bytes \| None)` | reader with `.status`, `.topic`, `.schema_version`, `.n_answerable` |
| `Image.view(letter_or_name: str)` | view or `None` |
| `Image.prefix(view)` | bytes |
| `Image.lookup(view, key: bytes)` | `(outcome, rest_bytes)` |
| `Image.query(text: str)` | full answer bytes for a `/wissen` argument string |
| `answer_bytes(tokens, alphabet, image)` | bytes the console prints for a generated answer (replaces `facttable.answer_bytes`, same signature) |
| `function_output(tokens, alphabet)` | unchanged from 006 |
