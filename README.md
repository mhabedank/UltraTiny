# UltraTiny

Ein kleines deutsches Sprachmodell, das **komplett offline auf einer NodeMCU (ESP8266)** läuft –
einem der kleinsten WLAN-Mikrocontroller (rund 80 KB RAM, keine FPU, 4 MB Flash). Du tippst über
die serielle Konsole eine Frage, der Chip schreibt die Antwort Buchstabe für Buchstabe zurück.
Ursprünglich für den klassischen ESP32 gebaut (Firmware dafür bleibt als Altbestand erhalten).
Inspiriert von [Tiny-2.1](https://github.com/WollyMonjac/Tiny-2.1), das ein ähnliches Modell auf
DOS-PCs bringt.

```text
UltraTiny v0.1.0 — Sprachmodell offline auf dem Mikrocontroller
Board: NodeMCU (ESP8266)
Modell: nodemcu | Format v1 | 583296 Parameter | 588 KB Flash | 35 KB RAM
Funk: aus. Tippe eine Frage und drücke Enter. /hilfe für Befehle.
> Wer bist du?
Ich bin UltraTiny, ein kleines Sprachmodell auf einer NodeMCU.
> Was ist die Hauptstadt von Frankreich?
Die Hauptstadt von Frankreich ist Paris.
```

(Antworten mit der PC-Runtime erzeugt, die bitgenau wie der Chip rechnet; die Messung auf dem
Board steht in [`specs/005-nodemcu-port/measurements.md`](specs/005-nodemcu-port/measurements.md).)

## Wie es funktioniert

| Teil | Inhalt |
|------|--------|
| Modell | Zeichenbasierter Transformer, 4 Schichten × 128, Multi-Query-Attention, ~0,6 Mio. Parameter |
| Speicher | int8-Gewichte (Skala pro Zeile) in einem eigenen Flash-Bereich, direkt aus dem Flash gelesen (auf dem ESP8266 nur in 32-Bit-Wörtern); NodeMCU: 588 KB Modell, 35 KB Arena (int8-KV-Cache, Kontext 104) |
| Geschwindigkeit | Prompt wird schon beim Tippen verarbeitet; die Antwort startet direkt nach Enter |
| Korrektheit | Eine NumPy-Referenz rechnet bit-genau wie der Chip; Golden-Vektoren prüfen PC und Board |
| Wissen | Fester deutscher Wissensbestand (Hauptstädte, Elementsymbole, Fragen über den Chip selbst) |

Spezifikation, Plan und Aufgaben: NodeMCU [`specs/005-nodemcu-port/`](specs/005-nodemcu-port/),
ursprünglich ESP32 [`specs/001-esp32-tiny-lm/`](specs/001-esp32-tiny-lm/) ·
Projektprinzipien: [`.specify/memory/constitution.md`](.specify/memory/constitution.md).

## Schnellstart NodeMCU (fertiges Modell)

Voraussetzungen: NodeMCU v2/v3 mit ESP8266 und 4 MB Flash, [PlatformIO](https://platformio.org/)
(`pip install platformio`), `esptool.py` (`pip install esptool`), `make`.

```bash
esptool.py --port /dev/ttyUSB0 flash_id           # erwartet: ESP8266EX, 4MB
make nodemcu-flash PORT=/dev/ttyUSB0              # Firmware bauen und flashen
make nodemcu-flash-model PORT=/dev/ttyUSB0        # Modell models/nodemcu.utny nach 0x58000
make nodemcu-monitor PORT=/dev/ttyUSB0            # Konsole, Strg-C beendet
```

Details, Treiber und Grenzen (Kontext 104 Zeichen, kein FPU, wenig RAM):
[`firmware-nodemcu/README.md`](firmware-nodemcu/README.md).

## Schnellstart ESP32 (Altbestand)

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

Konsolenbefehle: `/hilfe`, `/info` (Speicher, Latenz, Zeichen/s), `/stats`, `/trace aus|an|json`, `/modus gierig|zufall [seed] [temp]`,
`/max <n>`; Strg-C bricht eine Antwort ab.

## Ohne Hardware ausprobieren

```bash
cmake -S runtime -B build && cmake --build build && ctest --test-dir build
./build/utiny-host --model models/nodemcu.utny --prompt "Wer bist du?"
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

## Observability

Zwei Konsolenbefehle zeigen, was auf dem Gerät und im Modell passiert (Details und JSON-Format:
[`specs/002-observability/contracts/observability.md`](specs/002-observability/contracts/observability.md)):

- **`/stats`** – Heap frei / Minimum seit Boot / größter Block, freier Stack des Inferenz-Tasks,
  Arena benötigt/Puffer, KV-Cache-Füllstand, CPU-Last je Kern (seit dem letzten `/stats`),
  Laufzeit und Takt; dazu die Timings der letzten Antwort (Prefill-Länge, erstes Zeichen,
  Gesamtzeit, Zeichen/s, ms pro Zeichen Ø/min/max) und das Profil des Forward-Pass
  (embed, norm, qkv, attn, wo, ffn, head in %).
- **`/trace an`** – nach jeder Antwort eine Tabelle pro Zeichen: Position, Zeichen,
  Wahrscheinlichkeit, Top-3-Kandidaten, Entropie (bit), ms; dazu Ø/min-Wahrscheinlichkeit und
  Kontextnutzung. **`/trace json`** liefert dasselbe als `@ut {...}`-Zeilen für Tools,
  **`/trace aus`** (Standard) die unveränderte Ausgabe.

Am bequemsten mit dem Viewer, der die Demo-Fragen schickt und jede Antwort farbig nach
Wahrscheinlichkeit (grün = sicher, rot = unsicher) mit Timings, unsicheren Stellen samt
Alternativen, Profilbalken und Systemwerten zeigt:

```bash
make observe                              # startet QEMU, fragt 5 Demo-Fragen, beendet QEMU
make observe OBSERVE_ARGS="--demo"        # alle Demo-Fragen; oder eigene: OBSERVE_ARGS='"Wer bist du?"'
make observe-host                         # gleiche Ansicht mit der PC-Runtime, ohne Emulator
cd training && uv run python ../tools/observe.py --port /dev/ttyUSB0 --log out.jsonl   # echtes Board
```

Ohne Fragen und ohne `--demo` fragt der Viewer interaktiv (`/befehle` werden durchgereicht);
`--log datei.jsonl` schreibt alle Ereignisse mit. `make observe` und `make observe-host`
protokollieren automatisch nach `logs/observe-<datum>-<zeit>.jsonl` (abschalten mit
`OBSERVE_LOG=`); der Kopf-Eintrag nennt Quelle (QEMU, Host, Board), Modell und Git-Stand. Damit
lassen sich Läufe vergleichen, z. B. die Profilanteile:
`jq -c 'select(.type=="answer") | .prof_us' logs/observe-*.jsonl`. QEMU lässt sich auch separat mit Konsole auf TCP
starten (`UT_QEMU_TCP=5555 make qemu`, dann `observe.py --tcp localhost:5555`). In QEMU sind
Zeiten und CPU-Last emuliert und nur grob aussagekräftig; Speicherwerte und Modell-Trace sind
echt.

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
