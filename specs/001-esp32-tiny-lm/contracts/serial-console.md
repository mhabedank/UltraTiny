# Contract: Serial Console (device ↔ user)

UART0 via the board's USB-UART bridge, 115200 8N1, UTF-8 in both directions, line ending
`\r\n` on output; input accepts `\r`, `\n` or `\r\n` as Enter.

## Boot banner

```text
UltraTiny v<fw-version> — Sprachmodell offline auf dem ESP32
Modell: <name> | Format v1 | <n_params> Parameter | <model_kb> KB Flash | <arena_kb> KB RAM
Funk: aus. Tippe eine Frage und drücke Enter. /hilfe für Befehle.
> 
```

## Interaction

| Input | Behavior |
|-------|----------|
| printable char in alphabet | echoed; fed to model immediately |
| char not in alphabet | not echoed; once per line: `(Zeichen '<c>' unbekannt, ignoriert)` |
| Backspace (`0x08`/`0x7F`) | erase last char on screen, model position −1 |
| Enter, non-empty line | newline, then answer streamed char by char, then `\r\n> ` |
| Enter, empty line | `\r\n> ` only |
| Ctrl-C (`0x03`) during answer | stop, print ` [abgebrochen]`, then `\r\n> ` |
| any other input during answer | discarded |
| line too long for context | `(Frage zu lang, max <n> Zeichen)`; extra chars ignored |

## Commands (line starting with `/`; not fed to the model)

| Command | Output |
|---------|--------|
| `/hilfe` | list of commands |
| `/info` | model header fields, arena usage, last answer: first-char latency (ms), chars/s |
| `/modus gierig` | greedy decoding (default) |
| `/modus zufall [seed] [temp]` | sampling with seed (default 1) and temperature (default 0.8) |
| `/max <n>` | max answer length (1–200, default 200) |
| `/stats`, `/trace aus\|an\|json` | observability, see [002 contract](../../002-observability/contracts/observability.md) |

## Error output at boot (no reboot loop)

```text
FEHLER: Modell ungültig (<code>: <text>). Bitte Modell neu flashen (siehe README).
```

The device then accepts only `/hilfe` and `/info`.
