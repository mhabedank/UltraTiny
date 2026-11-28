# Hardware-Recherche November 2026: eigener Chip für Modelle auf Datenströmen

Abschätzung aus einer Gesprächsrunde vom 28. November 2026: Lohnt sich eigene Hardware für die
Modelle aus UltraTiny, und was wäre an Leistung herauszuholen?

**Wichtigste Einschränkung:** Das ist kein Deep-Research-Lauf wie
[`2026-11-architektur`](../2026-11-architektur/README.md), keine Aussage wurde gegengeprüft.
Gemessen sind nur die ESP8266-Werte aus Spec 005 und 007. Alles andere sind Überschlagsrechnungen
aus Datenblatt- und Lehrbuchwerten, gut auf Faktor 2 bis 3. Die Annahmen stehen in
[`abschaetzung.py`](abschaetzung.py); das Skript rechnet alle Zahlen dieser Seite nach:

```bash
python3 research/2026-11-hardware/abschaetzung.py
```

## Kernaussagen

1. **Nur verallgemeinert sinnvoll.** Ein Chip nur für UltraTiny lohnt sich nicht. Sinnvoll wäre ein
   Chip für Wahrscheinlichkeitsmodelle auf Datenströmen: Text und Sensordaten mit demselben
   Rechenwerk. Im IIoT ist Sprache Nebensache; Vorhersage, Anomalie-Erkennung und Kompression sind
   es nicht.
2. **Rechnen ist billig, Daten bewegen ist teuer.** Eine 8-Bit-Addition kostet etwa 0,03 pJ, ein
   Bit aus SRAM im Chip 0,3 bis 1,6 pJ, ein Bit aus externem QSPI-Flash etwa 165 pJ. Wo die
   Gewichte liegen, entscheidet über Tempo und Energie.
3. **Tempo gibt es fertig zu kaufen.** Ein Mikrocontroller mit genug RAM (RP2350, ESP32-S3)
   schafft geschätzt das 35- bis 330-Fache von heute. Für Tempo allein lohnt eigene Hardware nicht.
4. **Energie ist der eigentliche Gewinn.** Ein FPGA mit den Gewichten im Chip-RAM braucht geschätzt
   2 bis 9 µJ pro Schritt statt rund 21 mJ heute, also drei bis vier Größenordnungen weniger. Ein
   eigener Chip mit SRAM käme auf etwa 0,3 µJ.
5. **Fester Speicher im Chip, kein Cache.** Jedes Gewicht wird pro Schritt genau einmal gelesen.
   Ein Cache, der kleiner ist als das Modell, trifft deshalb praktisch nie. Das Modell muss ganz in
   festem SRAM liegen, sonst wird es vorausschauend nachgeladen.
6. **Mehrere Kanäle teilen sich die Gewichte.** Laufen 8 Sensorkanäle mit demselben Modell, braucht
   jeder Messwert nur ein Achtel der Speicherzugriffe.
7. **Tiny Tapeout zeigt das Prinzip, nicht die Leistung.** Eine Kachel ist zu klein für
   nennenswertes RAM; die Gewichte kämen über die Pins aus externem Flash (etwa 200 Schritte/s bei
   0,6 Mio. Parametern). Ein iCE40 UP5K mit 128 KB Chip-RAM liegt näher an einem echten Chip.
8. **Der ESP8266 hat selbst noch Reserven.** Heute braucht er 50 bis 60 Takte pro Multiplikation,
   der Flash erklärt davon etwa ein Drittel. QIO mit 80 MHz, Rechenschleifen im IRAM und ternäre
   Gewichte könnten zusammen etwa das 5- bis 10-Fache bringen (geschätzt 23 bis 52 Schritte/s).

## Verallgemeinerung: ein Rechenwerk für Text und Sensoren

UltraTiny sagt das nächste Zeichen voraus. Ersetzt man Zeichen durch quantisierte Sensorwerte
(z. B. 256 Stufen pro Kanal), bleibt der Rest gleich. Die Kennzahl, die im IIoT zählt, gibt es
schon: `/trace` zeigt pro Zeichen Wahrscheinlichkeit und Entropie, S1 misst Bit pro Zeichen. Bei
Sensordaten ist das der Anomalie-Wert.

| IIoT-Aufgabe | Was das Modell macht | Entspricht heute |
|--------------|----------------------|------------------|
| Vorhersage (Temperatur, Vibration, Last) | nächste Werte erzeugen | Antwort generieren |
| Anomalie-Erkennung | Überraschung in Bit pro Messwert | Entropie in `/trace`, KPI S1 |
| Telemetrie komprimieren | Wahrscheinlichkeiten plus arithmetische Codierung | Recherche 4 §5 „Kompression als Vorhersage“ |
| Lücken füllen, Rauschen entfernen | wahrscheinlichste fehlende Werte erzeugen | Generieren mit Vorgabe |
| Virtueller Sensor | nicht gemessenen Kanal aus anderen erzeugen | Frage rein, Antwort raus |
| Synthetische Testdaten | frei generieren mit Zufall | `/modus zufall` |

Diffusionsmodelle passen nicht: Sie brauchen viele Durchläufe durch das ganze Netz und arbeiten auf
Blöcken statt auf Strömen. Auf Sensorebene passen **rekurrente Modelle mit festem Zustand**, also
die minGRU/SSM-Linie aus der Roadmap (Spec 011, 012): ein Messwert rein, Zustand aktualisieren,
Verteilung raus.

Die Prüfung der Verallgemeinerung folgt dem Muster aus Spec 008, wo der Baukasten Chemie und Schach
ohne Codeänderung können musste: hier ein Rechenwerk, zwei Bereiche (Text und Sensor).

## Wo der ESP8266 heute steht

| Größe | Wert | Herkunft |
|-------|------|----------|
| Multiplikationen pro Zeichen | 568.832 linear plus bis zu 106.496 Attention | Modellkopf von `models/nodemcu.utny` (4 × 128, MQA, d_ff 384, 92 Zeichen) |
| Tempo | T2 4,8 Zeichen/s, T3 3,8 Zeichen/s | [Baseline 007](../../bench/results/baseline.md), Board |
| Takte pro Multiplikation | 49 bis 59 (T2), 62 (T3) | gerechnet, 160 MHz |
| Flash-Modus | DIO mit 40 MHz | `firmware-nodemcu/platformio.ini` setzt nichts; PlatformIO-Standard für `nodemcuv2` |
| Obergrenze nur durch Flash-Lesen | 14,8 Zeichen/s (DIO 40 MHz), 51 Zeichen/s (QIO 80 MHz) | Annahme: 32-Byte-Cache-Zeilen, 24 Takte Aufschlag pro Zeile |
| Anteil Flash an der Zeit | etwa 32 %; Rest etwa 40 Takte pro Multiplikation | gerechnet |
| Energie pro Zeichen | etwa 21 mJ | Annahme 0,1 W (Chip und Flash, Funk aus) |

Die restlichen rund 40 Takte pro Multiplikation sind weit mehr, als die Rechnung selbst braucht.
Ein plausibler Grund: Die Rechenschleifen haben kein `IRAM_ATTR`, laufen also aus demselben
Flash-Cache wie die Gewichte und verdrängen sich gegenseitig. Das Profil in `/stats` teilt die Zeit
nach Modellteilen auf (embed, norm, qkv, attn, wo, ffn, head), nicht nach Flash-Warten und Rechnen;
das sollen die Mikrobenchmarks aus Spec 011 messen.

Mögliche Sofortmaßnahmen, ungemessen: `board_build.flash_mode = qio` und
`board_build.f_flash = 80000000L`, falls der Flash-Chip des Boards das kann; die Matrix-Vektor-Schleife
ins IRAM (IRAM ist knapp, vorher prüfen); danach T2 und T3 mit `tools/bench.py board` messen.

## Energie: Rechnen gegen Speicher

| Vorgang | Energie | Quelle |
|---------|---------|--------|
| 8-Bit-Addition | 0,03 pJ | Horowitz 2014, 45 nm |
| 8-Bit-Multiplikation | 0,2 pJ | Horowitz 2014, 45 nm |
| SRAM lesen, Block um 32 KB | etwa 0,3 pJ pro Bit | Horowitz 2014 (20 pJ pro 64 Bit) |
| SRAM lesen, um 1 MB | etwa 1,6 pJ pro Bit | Horowitz 2014 (100 pJ pro 64 Bit) |
| Externer QSPI-NOR-Flash | etwa 165 pJ pro Bit | Annahme: 10 mA bei 3,3 V, 25 MB/s |

Ternäre Gewichte helfen doppelt: weniger Bits zu bewegen (1,6 statt 8 pro Gewicht) und Addieren
statt Multiplizieren. Rekurrente Modelle helfen, weil kein KV-Cache gelesen wird. Die Prozesse, die
Hobby-Projekten offenstehen (IHP 130 nm, GF180 180 nm), sind gröber als 45 nm; dort kostet jedes
Bit mehr.

## Plattformen im Vergleich

Annahme: ternäres rekurrentes Modell (minGRU-artig) mit 0,6 Mio. Parametern (so groß wie heute,
120 KB bei 1,6 Bit pro Gewicht) oder 2,4 Mio. Parametern (so viel Flash wie heute, 480 KB). Ein
Schritt ist ein Zeichen oder ein Messwert. Nur die erste Zeile ist gemessen.

| Plattform | Schritte/s, 0,6 Mio. | Schritte/s, 2,4 Mio. | Energie pro Schritt, 0,6 Mio. |
|-----------|---------------------:|---------------------:|------------------------------:|
| ESP8266 heute (gemessen, int8-Transformer, 0,6 Mio.) | 4,8 | – | etwa 21 mJ |
| ESP8266, ternär, QIO, IRAM | 23–52 | 6–13 | 1,9–4,4 mJ |
| RP2350, Gewichte im RAM | 167–333 | 42–83 (knapp im RAM) | 0,18–0,36 mJ |
| ESP32-S3, Gewichte im RAM | 533–1.600 | 133–400 (knapp im RAM) | 94–281 µJ |
| FPGA iCE40 UP5K, Gewichte im Chip-RAM | 1.600–3.200 | passt nicht (128 KB) | 1,6–9,4 µJ |
| FPGA oder Tiny Tapeout, Gewichte aus QSPI-Flash | etwa 210 | etwa 50 | 160–240 µJ, fast alles Flash |
| Eigener Chip mit SRAM (45-nm-Werte) | etwa 85.000 | etwa 21.000 | etwa 0,3 µJ (2,4 Mio.: etwa 6 µJ) |

Annahmen im Einzelnen (alle in `abschaetzung.py`):

- ESP8266: 4 bis 8 Takte pro ternärem Gewicht; Flash-Lesen und Rechnen addieren sich, weil die CPU
  bei jedem Cache-Fehlgriff wartet.
- RP2350: 1,5 bis 3 Takte pro Gewicht und Kern, 2 Kerne, 150 MHz, 60 mW.
- ESP32-S3: 0,5 bis 1,5 Takte pro Gewicht und Kern (SIMD), 2 Kerne, 240 MHz, 150 mW.
- iCE40 UP5K: 4 SPRAM-Blöcke × 16 Bit = 8 Byte pro Takt = 40 ternäre Gewichte (5 pro Byte),
  24 bis 48 MHz, 5 bis 15 mW.
- QSPI-Flash: 25 MB/s (4 Bit, 50 MHz), 33 bis 50 mW beim Lesen.
- Eigener Chip: 256 ternäre Gewichte pro Takt bei 200 MHz, SRAM-Energie nach Horowitz.

## Fester Speicher statt Cache

Gemeint ist dieselbe Technik wie bei einem CPU-Cache (SRAM im Chip), aber anders benutzt:

| | Cache (wie in CPUs) | Fester Speicher im Chip („Scratchpad“) |
|---|---|---|
| Wer entscheidet, was drinliegt? | die Hardware, automatisch | der Modell-Compiler |
| Inhalt | Kopien, die verdrängt werden | die Gewichte, dauerhaft |
| Energie pro Zugriff | höher (Adressvergleich, Verwaltung) | nur das reine Lesen |
| Zeitverhalten | schwankt je nach Treffer | immer gleich, gut für Echtzeit |

Ein Cache hilft, wenn Daten bald wieder gebraucht werden. Pro Schritt wird jedes Gewicht genau
einmal gelesen, in fester Reihenfolge, und erst im nächsten Schritt wieder gebraucht. Ist das Modell
größer als der Cache, ist jedes Gewicht bis dahin verdrängt. Genau das passiert heute auf dem
ESP8266: rund 570 KB Gewichte pro Zeichen laufen durch einen Flash-Cache von wenigen Dutzend KB.

Passt das Modell nicht in den Chip, ist ein Cache trotzdem die falsche Lösung. Weil die
Lesereihenfolge vorher feststeht, kann eine kleine Lade-Einheit (DMA) den nächsten Block holen,
während der aktuelle gerechnet wird. Das versteckt die Wartezeit, senkt aber nicht die Energie für
den Flash. Große KI-Chips (etwa Groq, Cerebras) setzen aus demselben Grund auf viel SRAM im Chip
statt auf eine klassische Cache-Hierarchie.

## Mehrere Kanäle teilen sich die Gewichte

Hat eine Maschine mehrere Sensorkanäle mit demselben Modell, wird jedes Gewicht einmal gelesen und
auf alle Kanäle angewendet. Kosten: ein kleiner Zustand pro Kanal (einige hundert Byte). Beispiel
mit Gewichten aus QSPI-Flash, 0,6 Mio. Parameter:

| Kanäle | Flash-Energie pro Messwert |
|-------:|---------------------------:|
| 1 | 158 µJ |
| 4 | 40 µJ |
| 8 | 20 µJ |
| 16 | 10 µJ |

GPUs machen das mit Batches genauso. Für einen eigenen Chip ist das vermutlich der billigste große
Gewinn, gerade wenn die Gewichte doch aus externem Flash kommen.

## Was der Chip können müsste

1. **Ternäres Matrix-Vektor-Werk:** der Großteil der Arbeit, nur Addieren und Subtrahieren.
2. **Kleines Ganzzahl-Werk für Werte paarweise:** Gates (Zustand mal Gate), Addition, Normierung;
   wenige echte Multiplizierer.
3. **Tabellen-Einheit:** Sigmoid, Kehrwert der Wurzel, Logarithmus.
4. **Wahrscheinlichkeits-Einheit:** Softmax, Sampling, Bit pro Messwert, optional ein
   arithmetischer Codierer in Hardware. Hier könnte sich der Chip abheben; die üblichen kleinen
   KI-Beschleuniger zielen nach unserem Kenntnisstand auf CNNs zum Klassifizieren (ungeprüft).
5. **Kleiner Befehlssatz** (etwa 10 Operationen), damit verschiedene Modelle laufen. Ein
   Modell-Compiler übersetzt das trainierte Netz, wie der Wissens-Compiler aus Spec 008.

Gewichte im festen SRAM des Chips (oder per DMA aus externem Flash), Zustand im Chip, ein
Mikrocontroller für Ein- und Ausgabe.

## Tiny Tapeout

[Tiny Tapeout](https://tinytapeout.com/) ist ein Bildungsprojekt, über das Hobbyleute für wenig Geld
eigene Designs auf einem echten Chip fertigen lassen. Hunderte Designs teilen sich einen Chip.

- Jedes Design bekommt eine Kachel, auf GF180 geplant mit etwa 1.000 Logikzellen; größere Designs
  belegen mehrere Kacheln.
- Anschlüsse: 8 Eingänge, 8 Ausgänge, 8 bidirektionale Pins, dazu Takt und Reset.
- Entwurf in Verilog oder im Browser-Editor Wokwi; eine GitHub-Vorlage mit GitHub Actions erzeugt
  das Chip-Layout.
- Gefertigt wird inzwischen bei IHP (Frankfurt an der Oder, 130 nm) und auf GF180 über wafer.space,
  nachdem der frühere Partner Efabless 2025 geschlossen hat.
- Preise: Für die IHP-Runde 25b nannte die FAQ etwa 50 € pro Kachel, 100 € für das Entwicklerkit
  und 25 € Versand. Aktuelle Preise zeigt der Rechner auf der Website.
- Dauer: Die Runde TTIHP26b schloss am 21. September 2026; die Termine für die Chips liegen Mitte bis
  Ende 2027.

Für UltraTiny hieße das: Das Modell passt nicht auf den Chip, wohl aber ein kleines ternäres
Rechenwerk mit SPI-Anschluss. Die Gewichte kämen über die Pins aus externem Flash, die Leistung läge
also in der QSPI-Zeile der Tabelle oben. Das zeigt, dass das Prinzip funktioniert, aber nicht, was
ein Chip mit eigenem SRAM könnte. Dasselbe Verilog lässt sich vorher auf einem FPGA testen.

## IIoT: welche Leistung man braucht

| Signal | Typische Abtastrate | Was reicht |
|--------|---------------------|------------|
| Prozesswerte (Temperatur, Druck, Durchfluss, Energie) | 1 bis 100 Hz pro Kanal | ein Mikrocontroller; für wenige Kanäle schon der optimierte ESP8266 |
| Vibration, Körperschall | 10 bis 50 kHz | pro einzelnem Messwert nur ein eigener Chip mit SRAM; sonst Merkmale oder Zeitfenster (z. B. ein Spektrum alle 100 ms) |

Energie am Beispiel einer Knopfzelle CR2032 (etwa 2.400 J), ein Schritt pro Sekunde rund um die Uhr:

| Plattform | Energie pro Schritt | Laufzeit, nur Rechnen |
|-----------|--------------------:|----------------------:|
| ESP8266 heute | 21 mJ | etwa 1,3 Tage |
| ESP8266, ternär, optimiert | 2,9 mJ | etwa 9,5 Tage |
| RP2350, Gewichte im RAM | 0,25 mJ | etwa 110 Tage |
| ESP32-S3, Gewichte im RAM | 0,16 mJ | etwa 170 Tage |
| Gewichte aus QSPI-Flash | 0,2 mJ | etwa 140 Tage |
| FPGA iCE40 UP5K, Chip-RAM | 3,8 µJ | rechnerisch etwa 20 Jahre |
| Eigener Chip mit SRAM | 0,3 µJ | Rechnen spielt keine Rolle mehr |

Schlafstrom, Aufwachen, Funk und Selbstentladung sind nicht mitgerechnet; in der Praxis bestimmen
sie oft die Laufzeit.

## Vorgeschlagene Versuche

1. **ESP8266-Sofortmaßnahmen messen:** QIO mit 80 MHz und Rechenschleifen im IRAM, T2 und T3 mit
   dem Benchmark aus Spec 007.
2. **Flash gegen Rechnen messen:** die Board-Mikrobenchmarks aus Spec 011 (zufällige
   32-Byte-Flash-Zugriffe, int8 gegen ternär) um eine Aufteilung der Zeit erweitern.
3. **UltraTiny-Sensor (nur Software):** dieselbe Runtime mit Sensor-Tokens statt Zeichen, auf der
   NodeMCU; Demo mit Vorhersage, Anomalie-Wert und Kompressionsrate. Mögliche offene Daten:
   Numenta Anomaly Benchmark, CWRU-Lagerdaten (Lizenzen prüfen, `DATA_LICENSES.md`).
4. **Virtueller Chip:** Befehlssatz festlegen und in der PC-Runtime bitgenau nachbauen, mit Zählern
   für gelesene Bytes und Rechenschritte. Kennzahlen: Schritte pro Sekunde, Bytes pro Schritt,
   Energie pro Schritt. Erweitert `abschaetzung.py` um echte Zählwerte.
5. **FPGA-Prototyp:** iCE40 UP5K mit offener Toolchain (Yosys, nextpnr), zuerst nur das ternäre
   Matrix-Vektor-Werk, getestet gegen die Golden-Vektoren der PC-Runtime.
6. **Tiny Tapeout:** ein Kernblock daraus als eigener Chip, erst wenn der FPGA-Prototyp läuft.

## Offen und unbelegt

- Aufteilung Flash-Warten gegen Rechnen auf dem ESP8266, Größe der Cache-Zeilen, ob der Flash-Chip
  der NodeMCU QIO mit 80 MHz kann, wie viel IRAM frei ist.
- Leistungsaufnahme von ESP8266, RP2350, ESP32-S3, iCE40 UP5K und QSPI-Flash: Größenordnungen aus
  Datenblättern, nicht gemessen.
- Takte pro ternärem Gewicht auf jedem Mikrocontroller: kein Kernel geschrieben.
- Genauigkeit ternärer rekurrenter Modelle auf Sensordaten: unbekannt. Auf Text nennt Recherche 1
  §3 bei 60K Parametern +5 % (Transformer) bis +28 % (SSM) Fehlerwert.
- Ob bestehende kleine KI-Beschleuniger (Arm Ethos-U, MAX78000, STM32N6 und andere) ternäre,
  rekurrente Modelle mit Wahrscheinlichkeits-Ausgabe schon abdecken: nicht recherchiert, Kandidat
  für einen Deep-Research-Lauf.
- Tiny Tapeout: aktuelle Preise, Geschwindigkeit der Pins, ob es SRAM-Bausteine für die Kacheln
  gibt.
- Die Energiewerte gelten für 45 nm; die für Hobby-Projekte erreichbaren Prozesse (130 nm, 180 nm)
  sind schlechter.

## Quellen

- Messwerte: [`bench/results/baseline.md`](../../bench/results/baseline.md),
  [`specs/005-nodemcu-port/measurements.md`](../../specs/005-nodemcu-port/measurements.md)
- PlatformIO-Board `nodemcuv2` (Flash-Standard DIO, 40 MHz):
  <https://github.com/platformio/platform-espressif8266/blob/develop/boards/nodemcuv2.json>
- M. Horowitz: „Computing's energy problem (and what we can do about it)“, ISSCC 2014
  (Energie pro Operation und Speicherzugriff, 45 nm)
- Datenblätter: Lattice iCE40 UltraPlus, Raspberry Pi RP2350, Espressif ESP32-S3 (Speichergrößen,
  Takt)
- Tiny Tapeout: <https://tinytapeout.com/>, <https://www.tinytapeout.com/runs>,
  [FAQ](https://docs.google.com/document/d/12KPutDPBst7FF0ncB1qyxErDYeATmXoQLGjRq38dfjU/mobilebasic),
  <https://tinytapeout.com/news/wafer-space-partnership/>,
  <https://www.eenewseurope.com/en/tiny-tapeout-sees-industrial-boost-as-it-recovers-from-efabless-closure/>
