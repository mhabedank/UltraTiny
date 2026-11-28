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

### Ohne Docker (kein sudo nötig)

Wenn Docker die GPU nicht durchreicht (z. B. `failed to fulfil mount request ... libnvidia-*.so`
nach einem Treiber-Update ohne Neustart), zuerst den anderen GPU-Modus probieren:

```bash
DOCKER_GPU="--device nvidia.com/gpu=all" tools/spark/train.sh
DOCKER_GPU="--runtime=nvidia -e NVIDIA_VISIBLE_DEVICES=all" tools/spark/train.sh
```

Sonst ganz ohne Docker mit einer venv im Home-Verzeichnis:

```bash
tools/spark/setup_venv.sh              # PyTorch mit CUDA (cu130-Wheels für aarch64), ~2-3 GB
UT_NO_DOCKER=1 tools/spark/train.sh
```

### Chemielehrer für die NodeMCU

Dieselben Chemie-Daten (inkl. Augmentierung), aber in der NodeMCU-Größe (4 × 128, Kontext 104,
siehe `specs/005-nodemcu-port/`). Paare, die nicht in 104 Zeichen passen (~18 %), fallen weg.

```bash
NAME=chemie-nodemcu tools/spark/train.sh configs/chemie-nodemcu-spark.toml
python3 tools/budget_report.py --board nodemcu --model models/chemie-nodemcu.utny   # NodeMCU-Grenzen
```

Aufs Board: `make nodemcu-flash-model PORT=... NODEMCU_MODEL=models/chemie-nodemcu.utny`.

### Hybrid-Chemielehrer (specs/006)

Faktenfragen beantwortet das Board aus dem Wissens-Image (specs/008), das Modell gibt nur `<fn>` + Typ +
Schlüssel aus. Ablauf:

1. **Gekürzte Erklärungen** (≤ 60 Zeichen) mit Ollama vorschlagen lassen:
   `python3 tools/shorten_llm.py --model qwen3.6:35b`. Das schreibt `data/facts/chemie_kurz.tsv`
   mit `reviewed = no`. Die Datei manuell auf den Mac kopieren, prüfen und `reviewed` auf `yes`
   setzen; nur geprüfte Zeilen werden trainiert.
2. **Kurzarbeits-Testset** `data/eval/kurzarbeit.tsv` prüfen und den SHA-256 als
   `kurzarbeit_sha256` in `configs/chemie-hybrid.toml` eintragen.
3. Training:

```bash
NAME=chemie-hybrid tools/spark/train.sh configs/chemie-hybrid.toml 1234
```

Ergebnis: `model.utny` (Format v2, Meta `topic = chemie`), `knowledge.utki`, `golden.json` (mit
gedruckten Antworten), `eval.json` (je Testset: zurückgehaltene Kombinationen und Formulierungen,
Kurzarbeit, falsche Fakten, Abweisungen). Zurück auf den Mac kopieren als
`models/chemie-hybrid.utny`, `models/chemie-hybrid_golden.json` und `models/chemie-hybrid_eval.json`;
das Wissens-Image ist `models/chemie.utki` (aus `topics/chemie`, byte-gleich mit `knowledge.utki`).
Die Pipeline endet mit `FAILED: …`, wenn ein Ziel aus spec 006 verfehlt ist; das Modell ist trotzdem da.

### Loss live auf dem Mac verfolgen

```bash
make spark-loss                                   # SPARK=user@host, SPARK_PATTERN='chemie-nodemcu-spark-s*.log'
```

`tools/loss_viewer.py` startet per `ssh` einen kleinen Log-Follower auf dem Spark (wird über stdin
mitgeschickt, nichts zu installieren), liest `training/runs/*-s*.log` und zeigt den Loss je Seed
live unter http://localhost:8765 (log. Achse, QAT-Beginn markiert, demo/held-out nach der
Auswertung). Bricht die Verbindung ab, verbindet er neu.

## 3. Ergebnis zurück

```bash
git add models/chemie* && git commit -m "model: chemie trained on DGX Spark" && git push
```

Oder ohne Push vom Spark: `scp <spark>:UltraTiny/models/chemie* models/` auf dem Mac. Danach:

```bash
make qemu MODEL=models/chemie.utny             # im Emulator ausprobieren
make flash-model MODEL=models/chemie.utny PORT=/dev/cu.usbserial-XXXX
```
