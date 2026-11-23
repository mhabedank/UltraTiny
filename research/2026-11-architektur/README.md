# Architektur-Recherche November 2026

Vier Deep-Research-Läufe zur Frage, wie UltraTiny deutlich besser werden kann: mehr Kontext, mehr
Tempo, mehr Wissen, und welche Bauart dafür passt. Jede Aussage wurde von drei Agenten
gegengeprüft; was zwei von drei widerlegten, ist gestrichen.

**Wichtigste Einschränkung:** Keine Quelle hat auf einem ESP8266 oder einem vergleichbaren Chip
ohne FPU mit rund 80 KB RAM gemessen. Alle Zahlen stammen von größeren Chips oder Modellen. Sie
sind Hinweise auf Richtungen, keine Zusagen; jede Übertragung muss auf unserem Board gemessen werden.

| Lauf | Thema | Quellen | Geprüft / bestätigt |
|------|-------|---------|---------------------|
| [1](01-performance-boost.md) | Größerer Kontext, mehr Tempo, größeres Modell, mehr Wissen | 20 | 25 / 24 |
| [2](02-domaenenmodell.md) | Domänenmodell: Wissen in Struktur statt in Gewichten | 22 | 25 / 23 |
| [3](03-baukasten-potenzial.md) | Themenunabhängiger Baukasten, ungenutztes Potenzial je Baustein | 22 | 25 / 22 |
| [4](04-architekturen.md) | Andere und neue Architekturen | 21 | 25 / 22 |

Visuelle Übersicht aller vier Läufe (mit Transformer-/Mamba-Erklärung):
[`uebersicht.html`](uebersicht.html), im Browser öffnen.

## Kernaussagen

1. **Wissen gehört nicht in die Gewichte.** Sprachmodelle speichern höchstens etwa 2 Bit Wissen pro
   Parameter, bei 0,6 Mio. Parametern also unter 150 KB. Eine Faktentabelle im Flash fasst ein
   Vielfaches. (Lauf 1, 2)
2. **Das Konzept umdrehen.** Fakten liegen als kompakte Struktur (Tripel, Wörterbuch) im Flash.
   Ein kleines Netz erkennt nur die Frageart (Vorlage), ein festes Lexikon ordnet Begriffe zu, die
   Antwort entsteht aus einer Vorlage. Eine knappe eigene Abfragesprache brachte in einer Studie
   rund 18 Punkte mehr als ein größeres Modell. (Lauf 2)
3. **Am PC denken, auf dem Chip nachschlagen.** Regel-Engines und Ontologie-Reasoner schaffen auf
   Mikrocontrollern nur wenige hundert Fakten. Abgeleitetes Wissen wird deshalb beim Bauen
   ausgerechnet und als fertige Fakten ausgeliefert. Der Aufbau ist themenunabhängig. (Lauf 3)
4. **Kein Baustein arbeitet am Optimum.** Belegte Reserven: Regel-Engine +45–49 % Fakten,
   Wörterbuch 3–4× kleiner, Beziehungs-IDs bis 2× kleiner, Graph-Einbettungen 32× bis über 400×
   kleiner (wenn beim Training quantisiert), HDC bis 98 % weniger Rechenschritte. (Lauf 3)
5. **Weg vom Transformer.** minGRU/minLSTM erreichen im Zeichenmodell praktisch Transformer-Niveau
   mit festem Zustand von etwa 512 Werten; RWKV-4 und sLSTM passen ebenfalls. RWKV-7 und mLSTM
   haben zu große Matrix-Zustände für 35 KB. (Lauf 1, 4)
6. **Neue Bauart, bisher unerforscht:** kleiner rekurrenter Kern im RAM, gehashtes
   N-Gramm-Gedächtnis im Flash, winziger Mischer (unter 1 000 Parameter). Mischformen aus zählendem
   und neuronalem Modell schlagen das Netz allein, am stärksten bei Daten zum Thema. Keine geprüfte
   Quelle hat diese Kombination auf einem Mikrocontroller untersucht. (Lauf 4)
7. **Kleinere Hebel:** 2-Bit- oder ternäre Gewichte für mehr Parameter im Flash; KV-Cache auf
   2 Bit, falls der Transformer bleibt. Tempo-Gewinne durch Bit-Tricks sind auf dem ESP8266 erst
   zu messen. (Lauf 1)

## Offen und unbelegt

Zu diesen Richtungen hat keine Aussage die Gegenprüfung überstanden; sie sind offen, nicht
widerlegt: Tsetlin-Maschinen, Logikgatter- und LUT-Netze, HDC-Sprachmodelle, Hopfield-Netze,
Reservoir Computing, Liquid-Netze, Product-Key-Speicher, Experten aus dem Flash, frühes Abbrechen,
grammatik-beschränkte Ausgabe, Absichtserkennung auf Mikrocontrollern, deutsche Antworten aus
Grammatiken, fallbasiertes Schließen, Methoden zum Entwurf eines Domänenschemas.

## Vorgeschlagene erste Versuche (aus allen Läufen)

1. Kern-Vergleich: Transformer gegen minGRU, sLSTM, RWKV-7 (kleine Köpfe) bei 60K/200K/600K
   Parametern; Bit pro Zeichen, Zustand in Byte, Zeichen pro Sekunde.
2. Flash-Gedächtnis: kleiner Kern mit und ohne gehashte N-Gramm-Tabelle; Flash-Zugriffszeit messen.
3. Kompressions-Hybrid: PPM/N-Gramm im Flash plus kleines RNN plus Mischer gegen das heutige Modell.
4. Vorlagen-Pipeline: Kompetenzfragen sammeln, Vorlagen ableiten, Faktentabelle kompilieren,
   Vorlagen-Erkennung mit winzigem Netz testen (Ziel über 90 %).
5. Kernel-Mikrobenchmark auf dem Board: int8 gegen 2-Bit/ternär/Lookup-Table.
