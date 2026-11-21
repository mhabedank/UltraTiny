# Training auf dem DGX Spark

Der Spark übernimmt zwei Aufgaben:

1. **Trainingsdaten erweitern** mit einem lokalen LLM über Ollama: zusätzliche Frageformulierungen,
   zusätzliche Fragevorlagen für Element- und Formelfragen sowie viele Abweisungsbeispiele.
   Antworten erzeugt das LLM nie; sie bleiben die geprüften aus `data/facts/`.
2. **Training auf der GPU** in einem Docker-Container: längeres Training, mehrere Seeds, und das
   beste Modell wird automatisch ausgewählt.

Die Modellgröße ändert sich dadurch nicht, die setzt der ESP32 (siehe Constitution).

## 0. Einmalig: Repo auf den Spark

```bash
ssh <spark>
git clone https://github.com/mhabedank/UltraTiny.git && cd UltraTiny
git checkout claude/modest-sagan-xrovbt        # oder später: main
```

Voraussetzungen auf dem Spark (laut `ollama ls` vorhanden): Ollama mit `gpt-oss:120b`, Docker
mit NVIDIA Container Toolkit (bei DGX OS Standard), Python 3.

## 1. Trainingsdaten erweitern (Ollama)

```bash
git pull
OLLAMA_NUM_PARALLEL=4 ollama serve &           # nur nötig, falls Ollama nicht schon so läuft
tools/spark/augment.sh                         # Standard: qwen3.6:35b ohne "Denken", mit Prüf-Prompt
JUDGE=none tools/spark/augment.sh              # PoC-schnell: ohne Prüf-Prompt (halb so viele Aufrufe)
MODEL=gemma4:e4b JUDGE=none tools/spark/augment.sh   # noch kleiner/schneller
MODEL=gpt-oss:120b tools/spark/augment.sh      # beste Qualität, deutlich langsamer
```

Fortschritt: eine Zeile pro Eintrag mit Restzeit, mitlesen auch mit
`tail -f training/runs/augment.log`. Ohne Prüf-Prompt filtern nur Zeichen-, Leck- und
Konfliktprüfung in `datagen`; für einen PoC reicht das, ein Blick auf Stichproben lohnt trotzdem.

Ergebnis in `training/data/augment/`:

| Datei | Inhalt | Zielgröße |
|-------|--------|-----------|
| `paraphrasen.tsv` | weitere Formulierungen für jede freie Frage (Lehrplan, Reaktionen, Persona) | ~10 je Frage |
| `vorlagen.tsv` | weitere Fragevorlagen für Element-Steckbriefe und Formeln | ~10 je Relation |
| `abweisen.tsv` | fachfremde Fragen und Unsinn, über 34 Themen verteilt | ~1.200 |

Das LLM bekommt die zurückgehaltenen Testfragen nie zu sehen. Jede Ausgabe durchläuft einen
zweiten Prüf-Prompt („passt die Antwort wirklich?“ bzw. „hat das nichts mit Chemie zu tun?“) und
danach die Zeichen-, Leck- und Konfliktprüfung in `datagen`. Abgebrochene Läufe setzen dort
fort, wo sie aufgehört haben (Cache in `training/runs/augment_cache/`).

Kurz prüfen und committen:

```bash
cd training && python3 - <<'EOF'
import csv, random
for f in ["paraphrasen", "vorlagen", "abweisen"]:
    rows = list(csv.DictReader(open(f"data/augment/{f}.tsv"), delimiter="\t"))
    print(f, len(rows)); [print("  ", r) for r in random.sample(rows, min(5, len(rows)))]
EOF
git add data/augment && git commit -m "data: LLM augmentation snapshot"
```

## 2. Training auf der GPU (Docker)

```bash
tools/spark/train.sh                           # configs/chemie-spark.toml, Seeds 1234 2345 3456
# eigene Seeds:   tools/spark/train.sh configs/chemie-spark.toml 1 2 3 4 5
# anderes Basis-Image:  BASE_IMAGE=nvcr.io/nvidia/pytorch:<tag>-py3 tools/spark/train.sh
```

Das Skript

1. baut das Image `ultratiny-train` (`training/docker/Dockerfile.spark`, NGC-PyTorch mit CUDA für
   den GB10); das Repo wird nur eingebunden, Code-Änderungen brauchen keinen Neubau,
2. trainiert jeden Seed mit `ut pipeline --device cuda` (60.000 Schritte, Batch 128, QAT falls die
   int8-Rechnung mehr als 2 Punkte kostet) inklusive Auswertung, Golden-Vektoren und Budgetprüfung,
3. prüft für jeden Lauf bit-genau C-Runtime gegen Referenz (`utiny-host --golden`),
4. vergleicht die Läufe und kopiert den besten nach `models/chemie.utny` (+ `_golden.json`,
   `_eval.json`, `_run.json`).

Falls `nvcr.io/nvidia/pytorch:25.10-py3` nicht verfügbar ist, ein aktuelleres Tag nehmen
(`docker build --build-arg BASE_IMAGE=...`) oder das Tag in `Dockerfile.spark` anpassen.

## 3. Ergebnis zurück

```bash
git add models/chemie* && git commit -m "model: chemie trained on DGX Spark" && git push
```

Oder ohne Push vom Spark: `scp <spark>:UltraTiny/models/chemie* models/` auf dem Mac. Danach:

```bash
make qemu MODEL=models/chemie.utny             # im Emulator ausprobieren
make flash-model MODEL=models/chemie.utny PORT=/dev/cu.usbserial-XXXX
```
