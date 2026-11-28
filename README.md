# UltraTiny

> **Proof of Concept.** UltraTiny ist ein Experiment und kein Produkt: Es zeigt, dass ein
> Sprachmodell auf einem sehr kleinen Mikrocontroller überhaupt läuft. Antworten können falsch
> sein, Formate und Schnittstellen können sich jederzeit ändern. Nicht für den produktiven Einsatz
> und nicht als Lernquelle gedacht.

Ein kleines deutsches Sprachmodell, das **komplett offline auf einer NodeMCU (ESP8266)** läuft –
einem der kleinsten WLAN-Mikrocontroller (rund 80 KB RAM, keine FPU, 4 MB Flash). Du tippst über
die serielle Konsole eine Frage, der Chip schreibt die Antwort Buchstabe für Buchstabe zurück.
Ursprünglich für den klassischen ESP32 gebaut (Firmware dafür bleibt als Altbestand erhalten).
Inspiriert von [Tiny-2.1](https://github.com/WollyMonjac/Tiny-2.1), das ein ähnliches Modell auf
DOS-PCs bringt (nur die Idee, kein übernommener Code).

Ein Projekt von [Martin Habedank](https://www.linkedin.com/in/martin-habedank/), entwickelt mit
[Claude Code](https://claude.com/claude-code) (siehe [Mit KI entwickelt](#mit-ki-entwickelt)).

## Stand (November 2026)

| Ziel | Stand |
|------|-------|
| NodeMCU v2 (ESP8266, CP2102, 160 MHz) | **läuft auf echter Hardware**: erstes Zeichen nach 158 ms, 5,1 Zeichen/s, ~5 KB Heap frei nach dem Boot |
| Modell `nodemcu` (Allgemeinwissen, im Repo) | 583 296 Parameter, 588 KB Flash, 35 KB RAM; Demo 100 %, ungesehene Formulierungen 70 % (PC-Referenz) |
| Modell `chemie-nodemcu` (DGX Spark, nicht im Repo) | Demo 96 %, Chemie-Held-out 80,9 %; auf dem Board erkennbare Wissenslücken |
| Klassischer ESP32 | Altbestand: baut in CI, läuft in QEMU; auf echter Hardware nie gemessen |
| Wissens-Baukasten | [`specs/008-wissens-compiler/`](specs/008-wissens-compiler/): Themen als Daten, Wissens-Image (UTKI) statt Faktentabelle; Board-Messung offen |
| Nächster Schritt | [`specs/ROADMAP.md`](specs/ROADMAP.md): 006 abschließen (Spark-Training), dann Spec 009 „Fragen verstehen“ |

Messwerte und offene Board-Prüfungen: [`specs/005-nodemcu-port/measurements.md`](specs/005-nodemcu-port/measurements.md).

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

## Chemielehrer (in Arbeit)

Ziel ist ein Modell, das nur Chemie für die Klassen 7–10 kann: Themen angelehnt an die
Themenfelder 3.1–3.12 des Rahmenlehrplans Chemie Berlin-Brandenburg, dazu Steckbriefe aller
118 Elemente, Formeln, Alltagsstoffe und einfache Reaktionen. Fragen außerhalb der Chemie soll es
ehrlich mit „Das weiß ich leider nicht.“ beantworten. Ein fertiges Chemie-Modell liegt **nicht**
im Repo.

- Das größere ESP32-Modell (6 × 192, ~1,75 Mio. Parameter) wurde nicht fertig trainiert
  ([`specs/003-chemielehrer/`](specs/003-chemielehrer/), pausiert).
- Ein Chemie-Modell in NodeMCU-Größe (`configs/chemie-nodemcu-spark.toml`) ist auf dem DGX Spark
  trainiert und auf dem Board getestet. Lange Lehrplan-Antworten passen nicht in den Kontext von
  104 Zeichen, deshalb fehlen ihm Fragetypen. Die Lösung plant
  [`specs/006-hybrid-chemielehrer/`](specs/006-hybrid-chemielehrer/).

```bash
cd training && uv run ut pipeline --config configs/chemie-nodemcu-spark.toml --out runs/chemie-nodemcu   # selbst trainieren
```

Training und Datenerweiterung auf dem DGX Spark (Ollama + Docker/CUDA): [`training/SPARK.md`](training/SPARK.md).

## Hybrid-Chemielehrer für die NodeMCU (Modell `chemie-hybrid`)

Auf der NodeMCU ist das Modell zu klein, um viele Fakten sicher zu behalten. Deshalb arbeitet es
**hybrid** ([`specs/006-hybrid-chemielehrer/`](specs/006-hybrid-chemielehrer/)):

- Bei Faktenfragen schreibt das Modell nur eine **Funktionsausgabe**: das Spezialzeichen `<fn>`,
  einen Buchstaben für den Fragetyp und einen Schlüssel. Aus „Welche Ordnungszahl hat Kupfer?“
  wird `<fn>OCu`. Die Firmware sucht den Wert in einem geprüften **Wissens-Image** und druckt
  „Die Ordnungszahl von Kupfer ist 29.“ Das Modell erfindet keine Werte.
- Bei Fragen in Gegenrichtung kopiert das Modell nur den Wert aus der Frage
  („Was ist N?“ → `<fn>sN`), die Firmware sucht das Objekt dazu.
- Begrüßungen, Abweisungen und kurze Erklärungen (höchstens 60 Zeichen) schreibt das Modell selbst.
- Das Wissens-Image (UTKI, rund 23 KB) liegt im Flash ab 0x100000, also außerhalb des
  eingeblendeten Megabytes, und hat eine eigene Prüfsumme.

### Wissens-Baukasten (spec 008)

Das Wissen ist ein **Thema aus Daten** ([`topics/`](topics/README.md), [`specs/008-wissens-compiler/`](specs/008-wissens-compiler/)):
Schema (Klassen, Beziehungen, Regeln, Antwortvorlagen) und Fakten als Tripel mit Quelle. Der
Compiler rechnet Rückrichtungen und einfache Regeln beim Bauen aus und schreibt das Wissens-Image;
auf dem Board wird nur nachgeschlagen. Das Chemie-Image beantwortet 3.145 Fakten mit 7,45 Bytes
pro Fakt (spec 006: 2.364 Fakten, 12,31 Bytes). Ein zweites Thema (Schachfiguren) läuft ohne
Codeänderung. `/wissen` fragt das Image auf der Konsole direkt ab, ohne Modell:

```text
> /wissen familie< Halogenen
Zu den Halogenen gehören: Fluor, Chlor, Brom, Iod und Astat.
```

```bash
make knowledge                                                                      # alle Themen -> models/<thema>.utki
make hybrid-smoke                                                                   # Mini-Pipeline auf der CPU
make nodemcu-flash-model PORT=... NODEMCU_MODEL=models/chemie-hybrid.utny            # Modell
make nodemcu-flash-facts PORT=... FACTS=models/chemie.utki                           # Wissens-Image
```

Training auf dem DGX Spark: [`training/SPARK.md`](training/SPARK.md), Abschnitt „Hybrid-Chemielehrer“.

## Selbst trainieren

Siehe [`training/README.md`](training/README.md) — ein Befehl erzeugt Daten, trainiert (Apple-GPU
über MPS oder CPU), wertet aus und exportiert das Modell.

## Grenzen

Das Modell ist winzig: Es kennt nur, was im Wissensbestand steht, und antwortet bei fremden
Themen flüssig, aber falsch. Es ist eine Demo, dass ein Sprachmodell auf einem Mikrocontroller
überhaupt läuft — kein Assistent. Die Chemie-Antworten sind nicht fachlich geprüft und ersetzen
keinen Unterricht.

## Mit KI entwickelt

Spezifikation, Code, Tests, Trainingsdaten-Werkzeuge und Dokumentation sind größtenteils mit
[Claude Code](https://claude.com/claude-code) (Anthropic) entstanden, nach dem
Spec-Kit-Ablauf in [`specs/`](specs/) und [`.specify/`](.specify/). Martin Habedank hat die
Anforderungen vorgegeben, die Ergebnisse geprüft und auf echter Hardware getestet.

Für die Trainingsdaten gilt: Fakten und Antworten stammen aus eigenen Texten und Wikidata. Ein
lokal laufendes Open-Weight-Modell (Gemma 4) hat nur zusätzliche *Frageformulierungen* erzeugt,
nie Antworten (siehe [`DATA_LICENSES.md`](DATA_LICENSES.md)).

## Lizenzen

- **Code und Modelle** (`models/*.utny`): MIT, siehe [`LICENSE`](LICENSE).
- **Trainingsdaten**: Quellen und Lizenzen je Zeile in [`DATA_LICENSES.md`](DATA_LICENSES.md)
  (eigene Daten MIT, Wikidata CC0 1.0, LLM-Frageformulierungen aus Apache-2.0-Modellen).
- **Fremdsoftware** wird nicht mitgeliefert, sondern beim Bauen geladen und steht unter ihrer
  eigenen Lizenz: ESP-IDF (Apache 2.0), ESP8266-Arduino-Core (LGPL 2.1) und ESP8266 NONOS SDK
  (Espressif-MIT-Lizenz) über PlatformIO, PyTorch und NumPy (BSD). Wer eine gebaute NodeMCU-Firmware
  weitergibt, muss die Pflichten der LGPL 2.1 für den Arduino-Core beachten.
- **Marken**: ESP32 und ESP8266 sind Marken von Espressif Systems, NodeMCU ist ein
  Open-Source-Projekt; Claude ist eine Marke von Anthropic. UltraTiny ist mit keinem davon
  verbunden.
