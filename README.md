# UltraTiny

Ein kleines deutsches Sprachmodell, das **komplett offline auf einem klassischen ESP32** läuft
(kein PSRAM, 4 MB Flash, 520 KB SRAM). Du tippst über die serielle Konsole eine Frage, der Chip
schreibt die Antwort Buchstabe für Buchstabe zurück. Inspiriert von
[Tiny-2.1](https://github.com/WollyMonjac/Tiny-2.1), das ein ähnliches Modell auf DOS-PCs bringt.

```text
UltraTiny v0.1.0 — Sprachmodell offline auf dem ESP32
Modell: starter | Format v1 | 602752 Parameter | 607 KB Flash | 79 KB RAM
Funk: aus. Tippe eine Frage und drücke Enter. /hilfe für Befehle.
> Was ist die Hauptstadt von Frankreich?
Die Hauptstadt von Frankreich ist Paris.
> Welches Element hat das Symbol Hg?
Hg ist das Symbol von Quecksilber.
```

## Wie es funktioniert

| Teil | Inhalt |
|------|--------|
| Modell | Zeichenbasierter Transformer, 4 Schichten × 128, Multi-Query-Attention, ~0,6 Mio. Parameter |
| Speicher | int8-Gewichte (Skala pro Zeile) in einer eigenen 2-MB-Flash-Partition, direkt aus dem Flash gelesen; ~78 KB statischer RAM (int8-KV-Cache) |
| Geschwindigkeit | Prompt wird schon beim Tippen verarbeitet; die Antwort startet direkt nach Enter |
| Korrektheit | Eine NumPy-Referenz rechnet bit-genau wie der Chip; Golden-Vektoren prüfen PC und Board |
| Wissen | Fester deutscher Wissensbestand (Hauptstädte, Elementsymbole, Fragen über den ESP32 selbst) |

Spezifikation, Plan und Aufgaben: [`specs/001-esp32-tiny-lm/`](specs/001-esp32-tiny-lm/) ·
Projektprinzipien: [`.specify/memory/constitution.md`](.specify/memory/constitution.md).

## Schnellstart (fertiges Modell)

Voraussetzungen: ESP32-Devboard (klassisch, 4 MB Flash), [ESP-IDF v5.4](https://docs.espressif.com/projects/esp-idf/),
`make`.

```bash
. $IDF_PATH/export.sh
cd firmware && idf.py set-target esp32 && idf.py -p /dev/ttyUSB0 flash && cd ..
make flash-model PORT=/dev/ttyUSB0 MODEL=models/starter.utny
make monitor PORT=/dev/ttyUSB0          # Strg-] beendet den Monitor
```

Auf macOS heißt der Port meist `/dev/cu.usbserial-*` oder `/dev/cu.SLAB_USBtoUART`.
Demo-Fragen mit erwarteten Antworten: [`training/data/demo_prompts.tsv`](training/data/demo_prompts.tsv).

Konsolenbefehle: `/hilfe`, `/info` (Speicher, Latenz, Zeichen/s), `/modus gierig|zufall [seed] [temp]`,
`/max <n>`; Strg-C bricht eine Antwort ab.

## Ohne Hardware ausprobieren

```bash
cmake -S runtime -B build && cmake --build build && ctest --test-dir build
./build/utiny-host --model models/starter.utny --prompt "Wer bist du?"
```

## Im ESP32-Emulator (QEMU) ausprobieren

Läuft die echte Firmware mit Modell auf einem emulierten ESP32 – ohne Board:

```bash
make qemu                                        # oder: make qemu MODEL=training/runs/v1/model.utny
```

Das Skript richtet beim ersten Mal alles selbst ein und fragt vorher nach: Es findet ESP-IDF über
`$IDF_PATH` oder `~/esp/esp-idf` (kein manuelles `export.sh` nötig), installiert sonst ESP-IDF
v5.4.1 nach `~/esp/esp-idf` (~2 GB), danach QEMU für den ESP32 und auf dem Mac die nötigen
Homebrew-Pakete. `UT_YES=1 make qemu` beantwortet alle Fragen mit Ja.

Beenden mit **Strg-A, dann X**. Der Emulator nutzt DIO/40 MHz statt QIO/80 MHz
(`firmware/sdkconfig.qemu`), weil QEMU QIO nicht kann. Er prüft Funktion und Antworten, nicht die
Geschwindigkeit – die Werte in `/info` sind dort nicht aussagekräftig.

## Chemielehrer (Modell `chemie`)

Ein größeres Modell (6 × 192, ~1,75 Mio. Parameter, 1,79 MB Flash, 91 KB RAM), das nur Chemie
für die Klassen 7–10 kann – nach dem Rahmenlehrplan Chemie Berlin-Brandenburg (Themenfelder
3.1–3.12), dazu Steckbriefe aller 118 Elemente, Formeln, Alltagsstoffe und einfache Reaktionen.
Fragen außerhalb der Chemie beantwortet es ehrlich mit „Das weiß ich leider nicht.“

```bash
make qemu MODEL=models/chemie.utny                       # im Emulator
make flash-model MODEL=models/chemie.utny PORT=...       # aufs Board
cd training && uv run ut pipeline --config configs/chemie.toml --out runs/chemie   # selbst trainieren
```

Details und Messwerte: [`specs/003-chemielehrer/`](specs/003-chemielehrer/).
Training und Datenerweiterung auf dem DGX Spark (Ollama + Docker/CUDA): [`training/SPARK.md`](training/SPARK.md).

## Selbst trainieren

Siehe [`training/README.md`](training/README.md) — ein Befehl erzeugt Daten, trainiert (Apple-GPU
über MPS oder CPU), wertet aus und exportiert das Modell.

## Grenzen

Das Modell ist winzig: Es kennt nur, was im Wissensbestand steht, und antwortet bei fremden
Themen flüssig, aber falsch. Es ist eine Demo, dass ein Sprachmodell auf einem Mikrocontroller
überhaupt läuft — kein Assistent.

## Lizenzen

Code: MIT. Trainingsdaten und deren Quellen: [`DATA_LICENSES.md`](DATA_LICENSES.md).
