# Contract: Function Output and Console Behaviour

This contract covers how the model signals a factual answer (research R1, R2), how the model file
encodes it (UTNY v2, R12), and what the console prints (R13). Table lookup is in
[fact-table-format.md](fact-table-format.md).

## Token sequence

```text
<bos> question <sep> answer
answer := text-char* <eos>
        | <fn> type-char key-char{1,12} <eos>
```

- `<fn>` is special token **id 5**. In the UTNY v2 alphabet table it is the code point `0xFFFF0005`.
  Text characters start at id 6.
- `type-char`: one ASCII letter (types in research R4).
- `key-char`: alphabet characters. The key is copied or mapped exactly and case-sensitively (research R2).
- In training text files `<fn>` is written as `\x01`. `Alphabet.encode` maps `\x01` → 5, and
  `Alphabet.decode` maps 5 → `\x01`.

### Examples (targets the training data teaches)

| Question | Model output | Printed answer |
|----------|--------------|----------------|
| Welche Ordnungszahl hat Kupfer? | `<fn>OCu` | Die Ordnungszahl von Kupfer ist 29. |
| Was ist N? | `<fn>sN` | Das Symbol N steht für Stickstoff. |
| Welches Element hat die Ordnungszahl 29? | `<fn>o29` | Die Ordnungszahl 29 hat Kupfer. |
| Wie viele Außenelektronen hat Schwefel? | `<fn>aS` | Die Zahl der Außenelektronen von Schwefel ist 6. |
| Stelle die Formel von Aluminiumoxid auf | `<fn>RAl2O3` | Die Formel von Aluminiumoxid ist Al2O3. |
| Welche molare Masse hat Wasser? | `<fn>mH2O` | Die molare Masse von Wasser beträgt 18,0 g/mol. |
| Was ist CO? | `<fn>fCO` | Die Formel CO steht für Kohlenstoffmonooxid. |
| Was ist Kohlenstoff? | `<fn>EC` | Kohlenstoff (C) ist ein Nichtmetall mit der Ordnungszahl 6. |
| Welche Ladung hat das Ion von Neon? | `<fn>iNe` | Neon bildet kein typisches Ion. |
| Formel von Unobtanium? | `Das weiß ich leider nicht.` | (model text) |
| Was ist eine chemische Reaktion? | text ≤ 60 chars | (model text) |
| Hi | greeting text | (model text) |

## UTNY v2 (model file)

- Header `version = 2`; the rest of the layout is as in v1 (specs/001 `contracts/model-format.md`).
- In the alphabet table, entries 0–5 MUST be `0xFFFF0000 + k`.
- The loader accepts v1 (5 specials, function mode off) and v2. `ut_model` gains `int has_fn`.
- `ut_token_from_codepoint` never returns a special (unchanged: it searches from id `n_specials`).
  `ut_codepoint_from_token(5)` returns 0.
- The exporter writes v2 when the alphabet has `<fn>`. The Python `read_model` accepts both versions.

## Console behaviour (`runtime/src/console.c`)

| State | Token | Action |
|-------|-------|--------|
| GENERATING | text char | Print it (as today). |
| GENERATING, first token | `<fn>` | Enter FN_TYPE. Nothing is printed. |
| GENERATING, later token | `<fn>` | Treated as `<eos>`. The training data never produces it. |
| FN_TYPE | letter | Store the type. Print the template prefix if the table is OK, otherwise the "missing" text and finish. |
| FN_TYPE | other / `<eos>` | Print `UNKNOWN` and finish. |
| FN_KEY | key char | Append it to the key buffer (≤ 12) and don't print it. |
| FN_KEY | `<eos>`, or 12 chars, or end of context | Resolve: print the rest of the template (after the prefix) or the fallback text, then finish. |
| any FN state | Ctrl-C | Abort as today; print nothing more. |

- The prefix is printed only once. If resolving ends in `UNKNOWN` or `not_applicable` after the prefix
  is already out, the console prints ` – ` and then the fallback text. Example:
  `Die Ordnungszahl von – Das weiß ich leider nicht.`. To avoid that, the training data maps unknown
  names to plain text (research R5). Parity covers this path as well.
- Statistics and `/trace` count every generated token, including `<fn>`, type and key, so speed numbers
  stay comparable. `/trace` shows `<fn>` as `⟨fn⟩`.
- `/info` adds the line `Faktentabelle: OK v1, 2534 Einträge, data a1b2c3d4`, or `fehlt` / `defekt (CRC)`.
- `/raw on|off` (new, default off) prints the raw function output (`<fn>OCu`) after the answer. It is
  meant for debugging and is part of the host tests, not of parity.

## Host and reference

- `utiny-host --model M --facts F [--golden G]`: same console, with the facts read from a file.
- `Reference.generate()` returns the token ids. `facttable.render(ids)` returns exactly the bytes the
  console prints for the answer: prefix, rest and fallbacks.
- The golden file (`*_golden.json`) gains `"facts_sha256"` and `"text"` per case (the printed answer).
  The host check compares tokens and text.
