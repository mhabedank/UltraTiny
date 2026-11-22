# Firmware für die NodeMCU (ESP8266)

Dünne Arduino-Plattformschicht (PlatformIO) für UltraTiny auf einer NodeMCU. Die gesamte Logik
(Modell, Konsole) liegt im portablen [`runtime/`](../runtime), das hier als lokale Bibliothek
(`lib/utiny`) mitgebaut wird. Spezifikation, Plan und Messwerte:
[`specs/005-nodemcu-port/`](../specs/005-nodemcu-port/).

| Datei | Aufgabe |
|-------|---------|
| `src/main.cpp` | WLAN aus, statische Arena (36 KB), Modell aus dem Flash einblenden, Konsolen-Schleife |
| `include/layout.h` | Flash-Aufteilung und Arena-Größe (eine Quelle für Firmware, Makefile, Budget-Report) |
| `ld/eagle.flash.4m.ultratiny.ld` | Linker-Skript: Firmware bis `0x57FFF`, Modellbereich ab `0x58000` |
| `lib/utiny/library.json` | bindet `../runtime` mit denselben Float-Flags wie auf dem PC ein |
| `platformio.ini` | Board `nodemcuv2`, 160 MHz, Plattform-Version fest |

## Unterstützte Boards

NodeMCU v2/v3 (auch „LoLin“) mit **ESP8266EX und 4 MB Flash**. So prüfst du ein Board:

```bash
esptool.py --port /dev/ttyUSB0 flash_id
```

Erwartet: `Chip is ESP8266EX` und `Detected flash size: 4MB`. Boards mit 1 MB oder 2 MB Flash
funktionieren nicht (der Modellbereich liegt fest bei `0x58000`–`0xFFFFF`, die Firmware
braucht zusätzlich die Konfigurationssektoren am Ende eines 4-MB-Flashs).

USB-Seriell-Chip: v2 nutzt meist **CP2102**, v3/LoLin meist **CH340**. Falls kein Port
erscheint, den passenden Treiber installieren (Silicon Labs CP210x bzw. WCH CH34x). Auf macOS
heißt der Port meist `/dev/cu.usbserial-*` oder `/dev/cu.SLAB_USBtoUART`, unter Linux
`/dev/ttyUSB0`. Manche USB-Kabel laden nur und übertragen keine Daten.

## Bauen, flashen, starten

Voraussetzungen: [PlatformIO](https://platformio.org/) (`pip install platformio`), `esptool.py`
(`pip install esptool`), `make`. Alle Befehle im Repository-Hauptverzeichnis:

```bash
make nodemcu-build                                   # Firmware bauen (lädt beim 1. Mal die Toolchain)
make nodemcu-flash PORT=/dev/ttyUSB0                 # Firmware flashen
make nodemcu-flash-model PORT=/dev/ttyUSB0           # Modell models/nodemcu.utny nach 0x58000
make nodemcu-monitor PORT=/dev/ttyUSB0               # Konsole (115200 Baud), Strg-C beendet
```

Ein anderes Modell flashen, ohne die Firmware neu zu bauen:
`make nodemcu-flash-model PORT=... NODEMCU_MODEL=pfad/zum/modell.utny`. Das Makefile prüft
vorher die Kennung `UTNY` und die Größe (höchstens 688.128 Bytes).

Nach dem Reset zeigt die Konsole den Grund des letzten Resets, dann die Startmeldung mit Modell,
Board und Speicher, dann `> `. Demo-Fragen mit erwarteten Antworten:
[`training/data/demo_prompts.tsv`](../training/data/demo_prompts.tsv), z. B.
„Worauf läufst du?“ oder „Was ist die Hauptstadt von Frankreich?“.

## Grenzen auf der NodeMCU

- **Kontext 104 Zeichen** (der ESP32 schafft 256): Fragen höchstens 70 Zeichen; die Antworten
  im Wissensbestand sind höchstens 72 Zeichen lang. `/max` wird automatisch auf das begrenzt,
  was in den Kontext passt.
- **Kein FPU**: Gleitkomma läuft in Software. Die Ergebnisse sind trotzdem bitgleich zur
  PC-Referenz; die Geschwindigkeit wird auf dem Board gemessen (`/info`, `/stats`).
- **Wenig RAM**: rund 80 KB insgesamt; 36 KB davon sind die Arena für das Modell. `/stats`
  zeigt freien Heap und freien Stack der Schleife.
- **Eingabe**: Jedes getippte Zeichen wird sofort ins Modell gespeist (~0,1 s pro Zeichen). Ein
  eingefügter Prompt wird zeichenweise abgearbeitet; die Antwort beginnt, sobald alles
  eingelesen ist.
- WLAN wird beim Start abgeschaltet; das Modell läuft komplett offline.

## Fehler beim Start

Ist kein oder ein beschädigtes Modell geflasht, oder braucht das Modell mehr Arbeitsspeicher als
die Arena hat (z. B. `models/starter.utny` mit Kontext 256), meldet die Konsole
`FEHLER: Modell ungültig (...)`. `/hilfe` und `/info` funktionieren weiter, das Board startet
nicht ständig neu. Abhilfe: das passende Modell mit `make nodemcu-flash-model` flashen.
