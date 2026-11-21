# Training, Export und Referenz

Python-Projekt (verwaltet mit [uv](https://docs.astral.sh/uv/)). Befehle: siehe
[`specs/001-esp32-tiny-lm/contracts/training-cli.md`](../specs/001-esp32-tiny-lm/contracts/training-cli.md).

## Einrichtung

```bash
cd training
uv sync            # macOS: PyTorch mit MPS (Apple-GPU); Linux: CPU-Wheels
```

## Modell trainieren (ein Befehl)

```bash
uv run ut pipeline --config configs/nodemcu.toml --out runs/nodemcu --device cpu   # NodeMCU-Modell
uv run ut pipeline --config configs/starter.toml --out runs/starter   # Startermodell (~165 Fakten)
uv run ut pipeline --config configs/v1.toml --out runs/v1             # volles Modell (ESP32)
```

**NodeMCU (ESP8266, aktuelles Zielboard)**: `configs/nodemcu.toml` ist die Starter-Architektur
(4 × 128, MQA, d_ff 384) mit **Kontext 104** statt 256 und Antworten bis 72 Zeichen. So bleibt
die Arena bei 35.520 Bytes und damit unter der NodeMCU-Grenze von 40 KB mit 10 % Reserve
(`specs/005-nodemcu-port/research.md` R4); 99,4 % der Frage-Antwort-Paare passen in den
Kontext. Die Budgets des Boards prüft `make budget` (bzw. `tools/budget_report.py --board
nodemcu`) – die Budgetprüfung in Schritt 6 der Pipeline nutzt noch die großzügigeren
ESP32-Grenzen. Aufs Board: `make -C .. nodemcu-flash-model PORT=... NODEMCU_MODEL=training/runs/nodemcu/model.utny`.

`--device auto` (Standard) nutzt auf dem Mac die GPU-Kerne über MPS und fällt sonst auf die CPU
zurück; erzwingen mit `--device mps` bzw. `--device cpu`. Die Pipeline:

1. `datagen` – Fakten × deutsche Vorlagen → `train.txt`, `heldout.jsonl`, `demo.jsonl` (+ SHA-256)
2. `train` – Training, schreibt `ckpt.pt` und `run.json` (Config, Seed, Daten-Hash, Git-Commit, Gerät, Dauer)
3. `export` – UTNY-v1-Datei `model.utny` (int8, siehe `contracts/model-format.md`)
4. `eval` – Genauigkeit mit der **quantisierten** Referenz (genau die Rechnung des Chips)
5. `golden` – Paritätsvektoren für `utiny-host --golden` und `tools/device_parity.py`
6. Budgetprüfung (Modell ≤ 1,8 MB, Arena ≤ 115 KB) – Exit-Code ≠ 0 bei Fehlschlag

Gemessen im Container (4 CPU-Kerne): Startermodell 3000 Schritte ≈ 7 min. Auf dem M3 mit MPS
sollte es deutlich schneller gehen (bitte messen und in `specs/001-esp32-tiny-lm/measurements.md` eintragen).

## Reproduzierbarkeit

Gleicher Seed + gleiche Daten + CPU ⇒ byte-identische `model.utny`
(`tests/test_determinism.py`). Auf MPS garantiert die Hardware keine bit-gleiche Rechnung; dort
sollen die Auswertungen zweier Läufe innerhalb von ±1 Prozentpunkt liegen.

## Neues Modell aufs Board

```bash
make -C .. nodemcu-flash-model PORT=/dev/cu.usbserial-XXXX NODEMCU_MODEL=training/runs/nodemcu/model.utny
make -C .. flash-model PORT=/dev/cu.usbserial-XXXX MODEL=training/runs/v1/model.utny   # ESP32 (Altbestand)
```

## Daten

- `data/facts/*.tsv` – Fakten (`id, topic, relation, subject, object, source`)
- `data/templates/*.toml` – deutsche Frage-/Antwortvorlagen (≥ 8 je Relation, ≥ 2 zurückgehalten)
- `data/topics.toml` – erlaubte Themen
- `data/demo_prompts.tsv` – Demo-Fragen mit erwarteten Antworten

Nur Quellen aus [`DATA_LICENSES.md`](../DATA_LICENSES.md) sind erlaubt; `datagen` prüft das.

## Tests

```bash
uv run ruff check . && uv run pytest -q
```
