# Roadmap: Vom Chemie-Modell zum Wissens-Baukasten

Stand: 23. November 2026. Grundlage: [`research/2026-11-architektur/`](../research/2026-11-architektur/README.md)
und die Fragerunde vom selben Tag.

## Entscheidungen aus der Fragerunde

| Frage | Entscheidung |
|-------|--------------|
| Womit anfangen? | Erst die Domänen-Pipeline (Wissen in Struktur, Netz erkennt nur die Frageart), danach der neue Modellkern |
| Demo-Thema | Chemie. Der Baukasten bleibt themenunabhängig; jede Spec testet das mit einem winzigen zweiten Testthema |
| Hardware | Jeder Schritt läuft auf der NodeMCU (ESP8266) und in der bitgenauen PC-Runtime |
| Antwortstil | Korrekte Fakten vor freier Sprache: lieber Vorlage und ehrliches „Das weiß ich nicht“ |
| Spec 006 | Erst abschließen, dann darauf aufbauen |
| Vergleichsmodell | `chemie-nodemcu` (Spec 005): Demo 96 %, ungesehene Formulierungen 80,9 %, 158 ms, 5,1 Zeichen/s |
| Training | Kleine Vorversuche überall auf CPU, echte Modelle auf dem DGX Spark (🖥️) |
| Kennzahlen | Faktenqualität, Tempo auf dem Board, Ressourcen, Sprachqualität und Kontext |

## Regeln für jeden Schritt

1. **Lauffähig:** Jeder Schritt endet mit einer Firmware, die auf der NodeMCU läuft, und einem
   Modell- bzw. Wissens-Image, das die PC-Runtime bitgenau gleich ausführt (Constitution III).
2. **Demo:** Jeder Schritt hat ein festes Demo-Skript (10 bis 15 Fragen), das auf dem Board neben
   `chemie-nodemcu` läuft. Ausgabe: beide Antworten nebeneinander.
3. **Benchmark:** Jeder Schritt läuft durch denselben Benchmark (Spec 007) und legt sein Ergebnis
   als JSON unter `bench/results/` ab. Der Vergleichsbericht zeigt den Schritt gegen die Baseline
   und gegen den Vorgänger.
4. **Budget-Gate:** RAM-Arena ≤ 35 KB, ≥ 10 % Reserve, Flash-Grenzen laut Constitution I. Wer ein
   Budget reißt, wird nicht gemergt.
5. **Ehrliche Messung:** Vergleiche mit 3 Seeds; eine Verbesserung zählt nur, wenn sie größer ist
   als die vorher festgelegte Rauschschwelle (Methodik aus Recherche 1 und 4).
6. **Themenunabhängig:** Nichts Chemie-Spezifisches in Code oder Formaten. Chemie steckt nur in
   Daten und Konfiguration.

## Kennzahlen (KPIs)

Spec 007 hat Definition, Testmenge und Messverfahren jeder Kennzahl festgelegt ([KPI-Definitionen](007-benchmark-kpi-bericht/contracts/result-format.md#kpi-definitions-implementation-of-spec-fr-009), Rauschschwellen in `bench/suites/*/suite.toml`). Übersicht:

| Gruppe | Kennzahl | Gemessen auf | Richtung |
|--------|----------|--------------|----------|
| Faktenqualität | **F1** richtige Antworten auf ungesehene Formulierungen | PC, Stichprobe Board | ↑ |
| | **F2** Anteil falscher Fakten (Wert genannt, aber falsch) | PC | ↓, Ziel ≤ 1 % |
| | **F3** richtig abgewiesen („weiß ich nicht“ bei unbekanntem Objekt oder fachfremder Frage) | PC | ↑ |
| | **F4** fälschlich abgewiesen | PC | ↓ |
| | **F5** Kurzarbeit-Satz (`kurzarbeit.tsv`) | PC, Board | ↑ |
| | **F6** Abdeckung: Anzahl beantwortbarer Fakten (Objekt × Eigenschaft) | PC | ↑ |
| Tempo | **T1** Zeit bis zum ersten Zeichen | Board | ↓ |
| | **T2** Zeichen pro Sekunde | Board | ↑ |
| | **T3** Zeichen pro Sekunde bei vollem Kontext | Board | ↑ |
| Ressourcen | **R1** RAM: Arena-Spitze und freier Heap nach dem Boot | Board | ↓ / ↑ |
| | **R2** Flash Modell, **R3** Flash Wissen | Build | ↓ |
| | **R4** Bytes pro Fakt (Wissen gesamt / F6) | Build | ↓ |
| Sprache | **S1** Bit pro Zeichen auf festem deutschem Prüftext (nicht trainiert) | PC | ↓ |
| | **S2** nutzbarer Kontext: Merk-Test, bei dem ein früh genanntes Wort später abgefragt wird | PC | ↑ |
| | **S3** Fließtext-Stichprobe: 20 Antworten, von Hand bewertet (Grammatik ok ja/nein) | PC | ↑ |

## Die Schritte

Jeder Schritt nennt unter **Grundlage** die Befunde aus der Recherche, auf die er sich stützt (§ = Nummer des Befunds im jeweiligen Bericht). Eine neue Spec liest diese Stellen vor dem Schreiben.

```text
 007 Benchmark ──┬── 006 abschließen ── 008 Wissens-Compiler ── 009 Fragen verstehen ── 010 Antworten bauen
                 │                                                                         │
                 └── 011 Kern-Labor (PC + Board-Mikrobenchmarks) ── 012 minGRU-Kern ── 013 Flash-Gedächtnis
```

Spec 007 kommt zuerst, weil jeder spätere Fortschritt daran gemessen wird. 006 kann parallel
trainiert werden. Spec 011 kann starten, sobald 007 steht; es ist ein Labor-Schritt, der die
Entscheidungen für 012 und 013 liefert.

### Schritt 1 · Spec 007: Benchmark und KPI-Bericht

**Grundlage:** [01 §8 Methodik](../research/2026-11-architektur/01-performance-boost.md) (Budget zuerst, mehrere Seeds, Rauschschwelle), [04 Offene Fragen](../research/2026-11-architektur/04-architekturen.md#offene-fragen) (S1/S2 als Messgrößen)

- **Ziel:** Fortschritt sichtbar machen. Ein Befehl misst ein Modell (mit oder ohne Wissens-Image)
  auf dem PC, ein zweiter auf dem Board; ein dritter erzeugt den Vergleichsbericht.
- **Inhalt:**
  - Testmengen einfrieren (SHA-256 gepinnt): ungesehene Formulierungen, unbekannte Objekte,
    fachfremde Fragen, `kurzarbeit.tsv`, Prüftext für S1, Merk-Test für S2.
  - `tools/bench.py` (PC), Board-Modus auf Basis von `devlib.py`/`device_smoke.py`.
  - `tools/bench_report.py`: Markdown und HTML, Baseline gegen Schritt, mit Rauschschwelle.
  - Demo-Skript-Runner: dieselben Fragen an zwei Boards bzw. zwei Firmware-Images, Antworten nebeneinander.
- **Baseline:** `chemie-nodemcu` liegt nur auf dem Spark. Die Baseline-Messung wird einmal gefahren
  und als JSON committet, damit Vergleiche ohne das Modell funktionieren.
- **Demo:** Baseline-Bericht für `chemie-nodemcu` und `nodemcu`.
- **Fertig, wenn:** Baseline-JSON im Repo, Bericht reproduzierbar, CI rechnet die PC-Kennzahlen für
  das Repo-Modell.
- **Stand (2026-11-24): erledigt.** Baseline-Bericht: [`bench/results/baseline.md`](../bench/results/baseline.md)
  (auch als HTML). `chemie-nodemcu` auf der Chemie-Suite: F1 38,5 %, F2 17,8 % falsche Fakten,
  F3 62,9 %, F5 37,7 %, F6 1.404 von 2.379 Fakten, S3 100 %; auf dem Board T1 178 ms, T2 4,8 Zeichen/s,
  T3 3,8 Zeichen/s, Arena 35.504 B, Parität 170/170. Die 80,9 % aus Spec 005 stammten aus
  Formulierungen des eigenen Datengenerators und sind mit F1 nicht vergleichbar. Messprotokoll:
  [`specs/007-benchmark-kpi-bericht/measurements.md`](007-benchmark-kpi-bericht/measurements.md).
  Jeder spätere Schritt misst mit `tools/bench.py` und vergleicht mit `tools/bench_report.py` gegen
  diese Baseline.

### Schritt 2 · Spec 006 abschließen: Hybrid-Chemielehrer

**Grundlage:** [01 §6 Wissensgrenze 2 Bit/Parameter](../research/2026-11-architektur/01-performance-boost.md), [02 §5 Vorlage plus Lücken](../research/2026-11-architektur/02-domaenenmodell.md), [02 §6 Faktenauswahl fest programmieren](../research/2026-11-architektur/02-domaenenmodell.md)

- **Ziel:** Die offenen Aufgaben T033 bis T047 erledigen: Kurzerklärungen prüfen, Kurzarbeit
  pinnen, `chemie-hybrid` auf dem Spark trainieren, Parität, Board-Messung.
- **Neu dazu:** Messung zusätzlich mit dem Benchmark aus 007.
- **Demo:** `chemie-hybrid` gegen `chemie-nodemcu`. Erwartung: F2 nahe 0, F1 deutlich höher bei
  gleichem Tempo.
- **Fertig, wenn:** SC-001 bis SC-006 aus Spec 006 gemessen (erreicht oder mit vereinbarter Anpassung).

### Schritt 3 · Spec 008: Wissens-Compiler (themenunabhängig)

**Grundlage:** [02 §1–2 Faktenspeicher und Bytes pro Fakt](../research/2026-11-architektur/02-domaenenmodell.md), [03 §1–3 Regeln am PC ausrechnen](../research/2026-11-architektur/03-baukasten-potenzial.md), [03 §4–6 Wörterbuch und IDs pro Beziehung](../research/2026-11-architektur/03-baukasten-potenzial.md)

- **Ziel:** Aus der Chemie-Faktentabelle wird ein allgemeiner Baukasten: Thema rein, Wissens-Image raus.
- **Inhalt:**
  - Schema-Datei pro Thema: Begriffsklassen, Beziehungen, Datentypen, Kompetenzfragen.
  - Fakten als Tripel; abgeleitete Fakten werden beim Bauen ausgerechnet (beide Richtungen,
    einfache Regeln wie „Gruppe 1 → Alkalimetall“), nicht auf dem Chip.
  - Kompaktes Wissens-Image (Nachfolger von UTFT): gepacktes Wörterbuch, IDs pro Beziehung,
    Index im Flash; Abfrage-Engine in C mit Python-Referenz.
  - Optionaler PC-Schritt: großes LLM schlägt fehlende Fakten vor, ein Mensch prüft sie.
- **Themen-Test:** ein winziges zweites Thema (z. B. 30 Fakten aus einem Spielregelwerk) als
  Testfall, der ohne Codeänderung kompiliert und abfragbar sein muss.
- **Demo:** mehr beantwortbare Fakten (F6) bei weniger Bytes pro Fakt (R4) als 006, gleiche Antworten.

### Schritt 4 · Spec 009: Fragen verstehen

**Grundlage:** [02 §3–5 kleiner Parser, knappe Ausgabesprache, Vorlagen](../research/2026-11-architektur/02-domaenenmodell.md), [03 §9 HDC als unscharfer Index](../research/2026-11-architektur/03-baukasten-potenzial.md)

- **Ziel:** Frageart und Begriffe zuverlässiger erkennen, auch bei neuen Formulierungen, Tippfehlern
  und gebeugten Formen („Natriums“).
- **Inhalt:**
  - Vorlagen werden aus dem Schema des Wissens-Image abgeleitet; das Netz gibt eine knappe
    Abfragesprache aus (kurze Zeichen statt Wörter).
  - Festes Lexikon mit Synonymen und Beugungsformen, unscharfe Suche für Tippfehler.
  - Sicherheitsschwelle: unter der Schwelle antwortet das Board „Das weiß ich nicht“.
  - Vergleich: bisheriges Sprachmodell mit Funktions-Token gegen einen separaten winzigen
    Vorlagen-Klassifikator.
- **Demo:** F1 und F3 rauf, F4 nicht schlechter, gleiches Tempo.

### Schritt 5 · Spec 010: Antworten bauen

**Grundlage:** [02 §5–6](../research/2026-11-architektur/02-domaenenmodell.md); deutsche Grammatik-Vorlagen sind in der Recherche unbelegt ([03 Vorbehalte](../research/2026-11-architektur/03-baukasten-potenzial.md#vorbehalte)), also selbst messen

- **Ziel:** Korrekte deutsche Sätze aus Fakten: Artikel, Fälle, Einheiten, mehrere Fakten in einer
  Antwort, Definitionen aus dem Wörterbuch.
- **Inhalt:** Grammatik-Vorlagen mit Beugungsregeln, themenunabhängig; Sprachmodell nur noch für
  Begrüßung, Smalltalk und Abweisung.
- **Demo:** Antworten auf zusammengesetzte Fragen („Ordnungszahl und Masse von Natrium?“), S3 rauf.

### Schritt 6 · Spec 011: Kern-Labor

**Grundlage:** [04 §1–3 minGRU, RWKV, xLSTM](../research/2026-11-architektur/04-architekturen.md), [04 §5 Kompression als Vorhersage](../research/2026-11-architektur/04-architekturen.md), [01 §3–5 Bit-Tricks und Speicherbandbreite](../research/2026-11-architektur/01-performance-boost.md), [01 §8 Methodik](../research/2026-11-architektur/01-performance-boost.md)

- **Ziel:** Entscheiden, welcher Modellkern den Transformer ersetzt, bevor gebaut wird.
- **Inhalt:**
  - PC: Transformer (heute), minGRU, sLSTM, RWKV-7 mit kleinen Köpfen bei 60K, 200K und 600K
    Parametern, int8, Ganzzahl-Arithmetik simuliert; S1, S2, Zustandsgröße.
  - Board: Mikrobenchmarks für zufällige 32-Byte-Flash-Zugriffe, int8 gegen 2-Bit-Kernel,
    Sigmoid-Tabelle.
  - Kompressions-Hybrid als Vorversuch: PPM/N-Gramm plus kleines RNN plus Mischer.
  - Ternäre Gewichte (BitNet b1.58): minGRU mit 200K und 600K Parametern in int8 gegen ternär
    bei gleichem Flash-Budget (ternär erlaubt etwa 4× so viele Parameter), Training mit
    Quantisierung von Anfang an. Auf dem Board: Rechenroutine nur mit Addieren und Subtrahieren
    gegen die heutige int8-Multiplikation, inklusive Entpacken der Bits. Erwartung laut Recherche
    vorsichtig: bei 60K Parametern +5 % Fehlerwert (Transformer) bis +28 % (SSM), auf dem ESP32-S3
    nur 1,71× schneller als Gleitkomma ([01 §3–4](../research/2026-11-architektur/01-performance-boost.md)).
- **Demo:** Laborbericht mit Empfehlung; Mikrobenchmark-Firmware läuft auf dem Board.

### Schritt 7 · Spec 012: Neuer Kern auf dem Board

**Grundlage:** [04 §1 minGRU](../research/2026-11-architektur/04-architekturen.md), [01 §1 fester Zustand statt KV-Cache](../research/2026-11-architektur/01-performance-boost.md)

- **Ziel:** Der Gewinner aus 011 (Arbeitshypothese: minGRU) ersetzt den Transformer als Sprachteil.
- **Inhalt:** neues Modellformat mit Architektur-Feld, C-Kernel, Parität, Training auf dem Spark.
- **Demo:** gleiche Faktenqualität, Kontext nicht mehr auf 104 Zeichen begrenzt (S2), T3 so schnell
  wie T2, weniger RAM.

### Schritt 8 · Spec 013: Flash-Gedächtnis und Mischer

**Grundlage:** [04 §4 Mischer zwischen Zähl- und Netzmodell](../research/2026-11-architektur/04-architekturen.md), [04 §6 Engram, Tabellen in langsamem Speicher](../research/2026-11-architektur/04-architekturen.md)

- **Ziel:** Die neue Bauart aus Recherche 4: gehashtes N-Gramm-Gedächtnis im Flash plus winziger Mischer.
- **Demo:** besseres S1 bei gleichem RAM; Tempo-Kosten der Flash-Zugriffe gemessen.

## Ideenspeicher (noch nicht eingeplant)

Diese Punkte kommen erst in die Roadmap, wenn ein Schritt sie braucht oder ein Versuch sie stützt:
KV-Cache auf 2 Bit (nur falls der
Transformer bleibt); HDC-Index für unscharfe Begriffssuche; Graph-Einbettungen zum Ergänzen
fehlender Fakten; Tsetlin-Maschine als Vorlagen-Klassifikator; Logikgatter-Netze; frühes Abbrechen.

## Offene Punkte

- **Constitution:** Neue Kerne (012) und das Flash-Gedächtnis (013) ändern Modellformat und
  Rechenwege. Principle II und V verlangen dafür Messungen; die liefert Spec 011.
- **Baseline-Zugang:** Für Board-Vergleiche muss `chemie-nodemcu` einmal vom Spark auf das zweite
  Board oder als Firmware-Image bereitliegen.
- **Zweites Testthema:** Welches Thema als Mini-Test in Spec 008 dient, wird dort entschieden.

## Eine Spec starten

`/speckit-specify` in einer neuen Session, zum Beispiel für Schritt 1:

```text
/speckit-specify Schritt 1 aus specs/ROADMAP.md (Spec 007: Benchmark und KPI-Bericht).
Lies vorher specs/ROADMAP.md (Entscheidungen, Regeln, KPI-Entwurf), die dort unter
„Grundlage“ verlinkten Befunde in research/2026-11-architektur/ und
specs/006-hybrid-chemielehrer/ (vorhandene Testmengen und Messungen).
```
