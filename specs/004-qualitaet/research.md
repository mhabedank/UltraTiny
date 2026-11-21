# Research: Tricks für mehr Modellqualität auf dem klassischen ESP32

**Status**: Recherche, nichts davon ist umgesetzt. Format (UTNY v1), Runtime und Firmware bleiben
unverändert. Was umgesetzt wird, entscheidet der Nutzer.

**Datum**: 2026-11-21 · **Basis**: Chemielehrer (`specs/003-chemielehrer`), d_model 192,
6 Schichten, ReLU-FFN, int8, ~1,75 Mio. Parameter, ≈ 1,78 MB Modelldatei.

## 0. Der Kern: was auf diesem Chip wirklich der Engpass ist

Pro erzeugtem Zeichen wird **jedes Gewicht einmal aus dem Flash gelesen** (≈ 1,78 MB pro Token).
Der Flash-Cache des ESP32 ist 32 KB groß, kann also fast nichts davon behalten. Die Firmware läuft
schon mit QIO und 80 MHz (`firmware/sdkconfig.defaults`); das ist die schnellste Flash-Einstellung,
die der klassische ESP32 kann. Damit gilt grob:

```
Zeichen/s  ≈  Flash-Durchsatz  /  (Bytes pro Token / Zeichen pro Token)
```

Der Plan von 003 schätzt 11–20 Zeichen/s. Die Rechenarbeit (≈ 1,75 Mio. int8-MACs pro Token)
passt in diese Zeit hinein.

**Konsequenz**: Der „Quake-Trick" für uns ist nicht schnellere Mathematik, sondern **weniger Bytes
pro erzeugtem Zeichen**. Jeder Faktor, den wir dort sparen, kann direkt in ein größeres Modell
fließen, also in mehr Qualität. Bei gleich vielen Zeichen pro Sekunde passt dann ein entsprechend
größeres Modell. Wo das Modell über 2 MB wachsen soll, braucht es eine Änderung der Verfassung:
der Flash hat 4 MB, die App belegt ~0,2 MB, realistisch also ~3 MB fürs Modell. Oder es braucht
eine Kompression, siehe T3.

Die Layer-Bilanz zeigt, wo die Bytes liegen. Pro Schicht sind es 283.008 Gewichte:

| Teil | Bytes/Schicht | Anteil |
|------|---------------|--------|
| Attention (Wq, Wk, Wv, Wo) | 86.016 | 30 % |
| FFN W1 (hoch) | 98.304 | 35 % |
| FFN W2 (runter) | 98.304 | 35 % |

**Zum Fast-Inverse-Square-Root-Vergleich**: Der Trick stammt aus *Quake III* (1999), nicht aus Doom.
Solche Bit-Tricks gibt es auch für `exp` (Schraudolph 1999). Hier bringen sie aber wenig:
RMSNorm und Softmax liegen deutlich unter 5 % der Laufzeit. Mehr dazu in T10.

---

## T1. Spekulatives Dekodieren mit Antwort-Trie: k Zeichen pro Flash-Durchlauf

- **Decision**: Stärkster Kandidat. Ein billiger „Entwurf" schlägt die nächsten k Zeichen vor.
  Das große Modell prüft alle k Positionen **in einem einzigen Durchlauf durch die Gewichte**.
  Pro geladener Gewichtszeile wird also gegen k Aktivierungsvektoren gerechnet statt gegen einen.
  Akzeptiert wird das längste Präfix, das Greedy auch erzeugt hätte, plus ein Zeichen vom Modell.
  Entwurfsquellen, die praktisch nichts kosten:
  1. **Trie der bekannten Antworten.** Es gibt nur ~2.100 verschiedene Antworten. „Das Symbol von "
     ist nach zwei Zeichen fast sicher.
  2. **Prompt-Lookup.** Antworten wiederholen Wörter aus der Frage: „Welche Ordnungszahl hat
     **Eisen**?" → „**Eisen** hat die Ordnungszahl 26."
  3. **N-Gramm-Tabelle** über die Trainingsantworten (wenige KB).
- **Rationale**:
  - Das Ergebnis ist **identisch zu Greedy**, also verlustfrei. Es ist nur schneller.
  - Bei Integer-Matmuls bleibt es bit-exakt, wenn der Verify-Pfad pro Position dieselbe
    Rechenreihenfolge hat. Die Parität ist damit testbar wie heute.
  - Literatur: Leviathan et al. 2023 (*Fast Inference from Transformers via Speculative
    Decoding*, arXiv:2211.17192) und Saxena 2023 (*Prompt Lookup Decoding*) berichten
    2–3× Beschleunigung auf GPUs. Dort ist ebenfalls die Speicherbandbreite der Engpass, genau wie
    hier.
  - Bei unseren formelhaften, geschlossenen Antworten sind höhere Akzeptanzraten plausibel als bei
    offenem Text.
  - Derselbe Mechanismus macht den **Prefill** billig: Die ganze Frage (~40 Zeichen) läuft in
    einem Durchlauf. Die Zeit bis zum ersten Zeichen sinkt grob um den Faktor der Promptlänge.
- **Kosten**:
  - Flash: Trie bzw. N-Gramme ≈ 50–100 KB.
  - RAM: k Aktivierungssätze. Bei k = 8 sind das ~8 × (d + d_ff) × 4 B ≈ 23 KB.
  - Rechenzeit: k-fach pro Durchlauf. Das ist nur so lange gratis, wie der Flash bremst und nicht
    die CPU (siehe T4/T5).
- **Format**: Kein Format-Bump nötig, wenn der Trie eine eigene Partition oder Datei bekommt.
  Neue Runtime-Funktion `ut_feed_many()`.
- **Risiko**: Mittel. Abgelehnte Entwürfe müssen den KV-Cache zurückspulen; `ut_rewind` gibt es
  schon. Welcher Gewinn real ist, hängt von der Akzeptanzrate ab, und die ist messbar, ohne
  etwas zu bauen (Python-Simulation).
- **Alternatives**: Self-Speculation mit den ersten Schichten als Entwurf (LayerSkip, Elhoushi et
  al. 2024, arXiv:2404.16710) braucht keinen Trie, hat aber schlechtere Entwürfe. Ein eigenes
  kleines Draft-Modell kostet Flash.

## T2. ReLU-Sparsity: Nullen aus dem Flash gar nicht erst lesen („LLM in a flash" im Kleinen)

- **Decision**: Nach `ReLU(W1·x)` ist ein Großteil der d_ff = 512 Neuronen exakt 0. Speichert man
  **W2 spaltenweise pro Neuron** (192 Bytes am Stück), überspringt man für jedes Null-Neuron
  dessen Spalte. Die Bytes werden dann nie gelesen.
- **Rationale**:
  - Das ist verlustfrei und bit-exakt: Ein Neuron mit Aktivierung 0 trägt im int32-Akkumulator
    exakt 0 bei.
  - Apple (*LLM in a flash*, Alizadeh et al. 2023, arXiv:2312.11514) berichtet bei ReLU-Modellen
    > 90 % FFN-Sparsity und lädt nur noch einen Bruchteil der FFN-Gewichte. *ReLU Strikes Back*
    (Mirzadeh et al. 2023, arXiv:2310.04564) zeigt, dass sich ReLU-Sparsity gezielt erhalten bzw.
    erhöhen lässt.
  - W2 sind ≈ 33 % aller Bytes. Bei 80 % Sparsity spart man ≈ 26 % pro Token, bei 90 % ≈ 30 %.
    Das entspricht ~1,4× Tempo bzw. ~40 % mehr Modell bei gleicher Geschwindigkeit.
  - **Ausbaustufe**: Ein kleiner Low-Rank-Prädiktor sagt voraus, welche Neuronen feuern. Dann
    lassen sich auch Zeilen von W1 überspringen (Deja Vu, Liu et al. 2023, arXiv:2310.17157).
    Das ist nicht mehr verlustfrei.
  - **Hot/Cold-Neuronen** (PowerInfer, Song et al. 2023, arXiv:2312.12456): Wenige Neuronen
    feuern fast immer. Deren Spalten legt man ins freie SRAM, siehe T6.
- **Kosten**: kein Flash; RAM null. Gather-Zugriffe auf 192-Byte-Spalten sind ok, weil die
  Cache-Zeile 32 B hat.
- **Format**: W2 transponiert speichern bedeutet Format-Bump v2, weil sich das Layout ändert.
  Mathematisch ändert sich nichts.
- **Risiko**: Niedrig. Die erste Frage lässt sich ohne Bau beantworten: Wie hoch ist die Sparsity
  im heutigen Modell wirklich? Ein Python-Hook auf die vorhandene Referenz genügt.
  **Zielkonflikt**: SwiGLU (in der Literatur für kleine Modelle besser, MobileLLM) zerstört diese
  Sparsity. Bei uns spricht der Flash-Engpass für ReLU (oder ReLU²).
- **Interaktion mit T1**: Beim Batch-Verify zählt die Vereinigung der aktiven Neuronen über alle
  k Positionen. Die Ersparnis sinkt mit k.

## T3. Weniger Bits pro Gewicht: int4 mit Codebuch, oder ternär (1,58 Bit)

- **Decision**: Für die FFN (70 % der Bytes) gibt es zwei Wege:
  - **4-Bit-Indizes in ein 16er-Codebuch pro Matrix** (nicht-uniforme Stufen per k-Means)
  - **ternäre Gewichte {−1, 0, +1}**
  Die Attention bleibt int8.
- **Rationale**:
  - **Codebuch-int4**: Doppelt so viele FFN-Parameter im gleichen Flash, gleich viele Bytes pro
    Token. Nicht-uniforme Stufen liegen bei gleicher Bitzahl genauer als uniformes int4.
    Literatur: Deep Compression, Han et al. 2016, arXiv:1510.00149; SqueezeLLM.
    - Dequantisierung: Ein Byte enthält zwei Indizes. Eine 256-Einträge-Tabelle liefert
      (w_a, w_b) als gepacktes Paar, also 1 Load für 2 Gewichte.
    - Die Verfassung erlaubt ≤ 8 Bit, daher keine Änderung nötig.
  - **Ternär**: Man packt 5 Trits in ein Byte (3⁵ = 243 ≤ 256), also 1,6 Bit/Gewicht. Das sind
    **5× mehr Parameter** als int8 bei gleichem Flash.
    - Die Matvec braucht **keine Multiplikation** mehr, nur Addieren und Subtrahieren. Noch
      schneller wird es per Lookup-Tabelle: Für je 4–5 Aktivierungen werden alle Vorzeichen-
      kombinationen vorab summiert, das Gewichtsbyte ist dann direkt der Tabellenindex. Das ist der
      Kniff von T-MAC (Wei et al. 2024, arXiv:2407.00088) und den llama.cpp-Formaten TQ1_0/TQ2_0.
    - BitNet b1.58 (Ma et al. 2024, arXiv:2402.17764) erreicht ab ~3 B Parametern FP16-Niveau.
      Bei **winzigen** Modellen ist die Lücke aber deutlich. Ob 5× Parameter die Lücke bei uns
      überkompensieren, ist offen.
- **Kosten**:
  - Codebuch: 16 Floats pro Matrix, vernachlässigbar.
  - Ternär: Skalen pro Gruppe; Training von Anfang an mit QAT (Straight-Through-Estimator), was
    das Training auf dem Spark ~1,5× langsamer macht.
- **Format**: Format-Bump v2 (neuer Matrix-Typ).
- **Risiko**:
  - Codebuch-int4: niedrig bis mittel. QAT ist schon im Code angelegt (`fq_rows`).
  - Ternär: hoch für die Qualität, hoher Gewinn bei Flash und Tempo.

## T4. Assembler: MAC16-Einheit, Zero-Overhead-Loops, Kernel im IRAM

- **Decision**: Erst relevant, **sobald T1–T3 den Flash-Engpass verschoben haben** und die CPU
  limitiert. Dann wird der innere Dot-Product-Kern von Hand in Xtensa-Assembler geschrieben.
- **Rationale**:
  - Der LX6 hat **Hardware-Schleifen** (`LOOP`, ohne Sprung-Overhead) und die **MAC16-Option**
    (16×16-Multiply-Accumulate in einen 40-Bit-Akku, mit gleichzeitigem Laden des nächsten
    Operanden).
  - Espressifs `esp-dsp` nutzt das für `dsps_dotprod_s16_ae32`. Laut Benchmark-Seite braucht das
    447 Zyklen für 256 Elemente, also **~1,7 Zyklen/MAC**.
  - Heutiger C-Code mit Byte-Loads und Sign-Extension liegt geschätzt bei 3–5 Zyklen/MAC.
  - Der Kern gehört ins **IRAM** (`IRAM_ATTR`), damit Code-Fetches nicht mit dem
    Gewichts-Streaming um den Flash-Cache konkurrieren.
  - Gewichte werden **32-bitweise geladen** (4 int8 auf einmal) und per Shift zerlegt, statt
    4 einzelne Byte-Loads zu machen.
- **Kosten**: kein Flash; einige hundert Bytes IRAM.
- **Format**: keine Änderung.
- **Parität**: Integer-Akkumulation ist reihenfolgeunabhängig, bleibt also bit-exakt.
- **Risiko**: Mittel. Assembler-Wartung; der Host-Build braucht weiter den C-Pfad als Referenz.

## T5. SWAR: zwei int8-Produkte mit einer 32-Bit-Multiplikation

- **Decision**: Das ist der Trick am nächsten am Quake-Spirit. Zwei Aktivierungen und zwei
  Gewichte werden so in je ein 32-Bit-Wort gepackt, dass **eine** Multiplikation im mittleren
  Bitfeld direkt `x0·w0 + x1·w1` liefert:
  ```
  (x0 + x1·2^16) · (w1 + w0·2^16) = x0·w1 + (x0·w0 + x1·w1)·2^16 + x1·w0·2^32
  ```
  Vorzeichen und Überträge löst man mit einem Offset (unsigned-Bias) und Schutzbits.
- **Rationale**:
  - Halbiert die Zahl der Multiplikationen.
  - HiKonv (Liu et al. 2021/22, arXiv:2112.13972, arXiv:2208.00763) zeigt das systematisch auf
    normalen CPUs ohne SIMD: Eine 32-Bit-Multiplikation liefert dort fünf 8-Bit- oder dreizehn
    4-Bit-Operationen; berichtet sind 2–3× schnellere Low-Bit-Faltungen.
  - Für 4-Bit-Gewichte (T3) wird es noch attraktiver.
- **Kosten**: keine. Das Gewichts-Layout lässt sich vorab schon gepackt im Export erzeugen.
- **Risiko**: Mittel. Überlauf-Logik muss exakt sein; das ist bit-exakt prüfbar. Gewinn nur, wenn
  die CPU limitiert, also nach T1–T3. Konkurriert mit MAC16 (T4); was schneller ist, entscheidet
  ein Messlauf.

## T6. SRAM als Gewichts-Cache: die heißesten Bytes nie aus dem Flash holen

- **Decision**: Der freie Teil des 520-KB-SRAM wird mit Gewichten gefüllt, die pro Token gelesen
  würden. Nach Firmware und 96-KB-Arena bleiben grob 150–250 KB; das ist zu messen.
  Kandidaten in absteigendem Nutzen:
  1. Hot-Neuron-Spalten von W2 (T2)
  2. Embedding/Head (~18 KB)
  3. komplette erste Schicht(en) (je ~283 KB, passt also nur teilweise)
- **Rationale**:
  - Jedes Byte im SRAM ist ein Byte weniger Flash-Verkehr pro Token. Bei 200 KB sind das ≈ 11 %
    schneller bzw. 11 % mehr Modell.
  - **IRAM-Hack**: Ungenutztes Instruktions-RAM kann Daten halten, wenn man nur 32-Bit-
    ausgerichtet liest (`l32i`). Das passt genau zu T4/T5, die ohnehin 32-bitweise laden.
    Das holt weitere zig KB heraus.
  - Die Verfassung verlangt Lesen aus dem Flash nur „where possible". Ein Teil-Cache im RAM ist
    eine erlaubte Optimierung, solange die Arena-Grenze gilt.
- **Kosten**: RAM. Das Kopieren beim Boot dauert < 100 ms.
- **Format**: keine Änderung.
- **Risiko**: Niedrig. Der freie RAM muss am Board gemessen werden.

## T7. „RAM-Swap" richtig herum: DMA-Doppelpuffer statt Cache-XIP

- **Decision**: Gewichte werden blockweise per SPI-DMA aus dem Flash in zwei SRAM-Puffer gelesen
  (`esp_flash_read`). Während Block n+1 lädt, rechnet die CPU auf Block n.
- **Rationale**:
  - Der Cache holt 32-Byte-Zeilen einzeln und **blockiert** die CPU bei jedem Miss.
  - DMA liest große zusammenhängende Blöcke nahe am Roh-Durchsatz des Busses (QIO 80 MHz =
    40 MB/s theoretisch) **und parallel zur Rechnung**.
  - Im besten Fall verschwindet die Rechenzeit komplett hinter dem Laden.
- **Risiko**: **Hoch, erst messen.** Beim klassischen ESP32 sperrt ein SPI1-Flash-Zugriff den
  Flash-Cache für beide Kerne. Der ganze Rechenpfad müsste dann im IRAM/DRAM laufen.
  Ob das unterm Strich schneller ist als XIP, zeigt nur ein Mikrobenchmark am Board.
- **Nicht sinnvoll**: Den KV-Cache oder Aktivierungen in den Flash „auslagern". Schreiben bzw.
  Löschen dauert Millisekunden und nutzt den Flash ab. RAM ist hier nicht der Engpass.

## T8. Zweiter Kern

- **Decision**: Nur in zwei Formen sinnvoll:
  - **(a)** Matvec-Zeilen aufteilen, sobald die CPU limitiert (nach T1–T5)
  - **(b)** Kern 1 als **Entpacker**: Er dekomprimiert entropiekodierte Gewichte (Huffman/tANS)
    in einen SRAM-Ringpuffer, während Kern 0 rechnet.
- **Rationale**:
  - int8-Gewichte sind ~gaußverteilt; ihre Entropie liegt bei ~5–6 Bit. Eine verlustfreie
    Kompression spart also ~25–35 % der Flash-Bytes (Deep Compression nutzt Huffman genau so).
  - Tabellen-ANS dekodiert mit wenigen Zyklen pro Symbol; bei 240 MHz sind ~30 Mio. Symbole/s
    denkbar. Das läge in der Größenordnung des Flash-Durchsatzes.
- **Risiko**: Hoch (komplex, Synchronisation). (b) lohnt nur, wenn T7 klappt.
  Laut TRM hat jede CPU eine eigene Cache-Einheit, beide teilen aber den SPI-Bus. Ohne Messung
  lässt sich nicht sagen, ob zwei Kerne mehr Flash-Durchsatz bekommen.

## T9. Geschlossene Welt ausnutzen: Antwort-Trie, Kurzschluss, Antwort-ID

- **Decision**: Der Chemielehrer kennt eine feste Menge von ~2.100 Antworten. Daraus folgen drei
  Tricks:
  1. **Constrained Decoding**: Das Modell darf nur Zeichen wählen, die im Trie weitergehen.
     Damit sind **Tippfehler unmöglich**, das bekannte Problem bei seltenen Freitext-Antworten.
  2. **Kurzschluss**: Ist das Präfix im Trie eindeutig, wird der Rest der Antwort **ohne Modell**
     ausgegeben, sofort. Weil danach nichts mehr generiert wird, muss der KV-Cache nicht
     nachgeführt werden.
  3. **Konfidenzschwelle**: Ist die mittlere Log-Wahrscheinlichkeit zu niedrig, kommt die
     Abweisung. Das hilft gegen Halluzination bei fachfremden Fragen.
- **Rationale**:
  - Hebt die Demo- und Held-out-Treffer dort, wo heute Tippfehler das Edit-Distanz-Kriterium
    reißen. Das Modell muss nur noch den **richtigen Ast** wählen, nicht jeden Buchstaben richtig
    schreiben.
  - Kombiniert mit T1 ist der Trie gleichzeitig der Entwurf.
  - Literatur: Hokamp & Liu 2017 (lexikalisch beschränktes Dekodieren); kNN-/Retrieval-Ansätze
    (Khandelwal et al. 2020).
- **Kosten**: Trie ≈ 50–100 KB Flash. Das passt heute nicht in die 1,8-MB-Grenze; das Modell
  müsste um ~5 % schrumpfen (z. B. d_ff 512 → 480), oder die Grenze steigt.
- **Format**: Eigene Datei/Partition, kein Bump. Runtime: Logit-Maske im Sampler.
- **Risiko**: Niedrig. **Grenze**: Das Modell kann dann nichts Neues mehr formulieren. Für einen
  Lehrer mit festem Stoff ist das gewollt, für offene Fragen nicht.

## T10. Fast-Math à la Quake: Schraudolph-`exp`, Inverse-Square-Root

- **Decision**: Nur der Vollständigkeit halber, **niedrige Priorität**.
- **Rationale**:
  - Schraudolph (1999, *A Fast, Compact Approximation of the Exponential Function*) baut `exp`
    durch direktes Schreiben des IEEE-Exponenten in einer Multiply-Add-Operation. Das ist der
    Bruder des Quake-III-Tricks `0x5f3759df` für 1/√x.
  - Beides ist mit NumPy-`view` bit-exakt nachbildbar, die Parität bleibt also haltbar.
  - Aber: Softmax über ≤ 192 Positionen × 6 Köpfe × 6 Schichten und 13 RMSNorms pro Token sind
    gegenüber 1,75 Mio. MACs und 1,78 MB Flash fast nichts. Der Gewinn liegt geschätzt **< 3 %**.
  - Alternativ hat die LX6-FPU Seed-Befehle für Kehrwert und Wurzel (`RECIP0.S`, `RSQRT0.S`) plus
    Newton-Schritt. Das ist dieselbe Idee in Hardware.
- **Alternatives**: Softmax per 256-Einträge-`exp`-Tabelle über quantisierte Scores ist bit-exakt
  und billig, bringt aber ebenso wenig.

## T11. Ergänzend auf der Trainingsseite (ohne Chip-Tricks)

Diese Hebel verbessern die Qualität bei gleichem Byte-Budget und kombinieren sich mit T1–T9:

| Trick | Erwartung | Quelle |
|-------|-----------|--------|
| Sequence-Level-Distillation: großes LLM auf dem Spark erzeugt viele Umformulierungen und saubere Antworten | größter Hebel für Held-out (Generalisierung kommt bei uns aus Datenvielfalt) | Kim & Rush 2016, arXiv:1606.07947; TinyStories |
| Logit-Distillation von einem großen UltraTiny-Lehrer (z. B. 8 × 384) | +einige pp, kostet nur Trainingszeit | Hinton et al. 2015 |
| Deep-and-thin statt breit, Embedding-Sharing, GQA | MobileLLM: bei < 1 B Parametern ist Tiefe wichtiger als Breite | Liu et al. 2024, arXiv:2402.14905 |
| Block-weises Layer-Sharing (gleiche Schicht 2× hintereinander) | +Tiefe ohne Flash, aber **doppelte Flash-Lesungen**: passt nur mit T1/T6 | MobileLLM, ALBERT |
| EMA / Checkpoint-Averaging, QAT immer | +0,5–2 pp, null Kosten auf dem Chip | Wortsman et al. 2022 |
| Subword-Tokens (Silben/BPE, 256–512 Tokens) | 2–3 Zeichen/Token: Tempo-Faktor wie T1, aber größerer Head (V × d pro Token) | — |

---

## Empfehlung (priorisiert nach Gewinn ÷ Aufwand)

| Rang | Trick | Gewinn | Aufwand | Format-Bump | Messbar vor dem Bau? |
|------|-------|--------|---------|-------------|----------------------|
| 1 | **T1 Spekulatives Dekodieren + Batch-Prefill** | 2–3× Tempo (geschätzt), verlustfrei; deutlich kürzere Zeit bis zum ersten Zeichen | mittel | nein | ja, Akzeptanzrate in Python simulieren |
| 2 | **T9 Antwort-Trie (Constraint + Kurzschluss)** | keine Tippfehler mehr, schneller, zusammen mit T1 nutzbar | niedrig | nein | ja, Python-Eval auf bestehendem Modell |
| 3 | **T2 ReLU-Sparsity in W2** (+ T6 Hot-Neuronen im SRAM) | −25–30 % Bytes/Token, bit-exakt | niedrig–mittel | ja (v2) | ja, Sparsity im heutigen Modell zählen |
| 4 | T3 Codebuch-int4 für FFN | 2× FFN-Parameter im gleichen Flash | mittel | ja (v2) | nur mit Training |
| 5 | T4/T5 Assembler-Kern (MAC16 / SWAR) | 2–3× Rechentempo; wichtig, sobald 1–3 greifen | mittel | nein | Mikrobenchmark am Board |
| 6 | T6 SRAM/IRAM-Gewichts-Cache | ~10 % | niedrig | nein | freien RAM messen |
| 7 | T3 ternär, T7 DMA, T8 Entpacker-Kern | potenziell groß, hohes Risiko | hoch | teils | Board-Benchmarks nötig |
| — | T10 Fast-Math | < 3 % | niedrig | nein | — |

**Wie das zusammen Qualität ergibt**: T1 + T2 + T6 zusammen könnten die Bytes pro *Zeichen* grob
um den Faktor 3–4 senken. Bei gleichen ≥ 10 Zeichen/s ließe sich das Modell dann von 1,75 Mio.
auf ~5 Mio. Parameter vergrößern.

Mit T3 (int4 bzw. Codebuch) passt das sogar in ~3 MB Flash. Dafür bräuchte es eine
Verfassungsänderung (Modellgrenze 2 MB → 3 MB). Alternativ ternär in unter 2 MB, mit dem
Qualitätsrisiko aus T3. T9 räumt parallel die Tippfehler ab, T11 (Distillation) die
Generalisierung.

**Vorschlag fürs nächste Feature (005)**: Drei Messungen ohne Umbau, jeweils Python auf dem
bestehenden Modell:

1. Akzeptanzrate von Trie-, Prompt- und N-Gramm-Entwürfen (T1)
2. ReLU-Sparsity und Hot-Neuronen pro Schicht (T2/T6)
3. Demo- und Held-out-Treffer mit Trie-Constraint (T9)

Dazu kommt ein kleiner Board-Benchmark: Flash-MB/s über XIP und freier SRAM. Danach steht fest,
welcher Gewinn real ist und welche Modellgröße das ESP32 bei 10 Zeichen/s tragen kann.

## Offene Punkte / Unsicherheiten

- Der effektive Flash-Durchsatz über den Cache ist **nicht gemessen**. Alle Tempo-Faktoren
  oben sind relativ.
- Die Sparsity des heutigen Modells ist unbekannt. Kleine Modelle mit Dropout sind oft weniger
  sparse als große.
- Literaturwerte stammen fast alle von GPUs/CPUs mit großen Modellen. Die Übertragbarkeit auf
  1–5 Mio. Parameter ist plausibel, aber unbewiesen.
- Ternäre Gewichte bei winzigen Modellen sind in der Literatur kaum untersucht.
- Ob sich MAC16 für int8 lohnt, ist offen: Es arbeitet auf 16-Bit-Hälften, also müssen
  Bytes erst entpackt werden.
- Der Experiment-Harness, der anfangs begonnen wurde, ist auf Wunsch entfernt worden. Es gibt
  dazu keine Messergebnisse; er liegt nur noch in der Git-Historie (Commit `f3a5aae`).

## Quellen

- Alizadeh et al. 2023, *LLM in a flash*: https://arxiv.org/abs/2312.11514
- Mirzadeh et al. 2023, *ReLU Strikes Back*: https://arxiv.org/abs/2310.04564
- Liu et al. 2023, *Deja Vu*: https://arxiv.org/abs/2310.17157
- Song et al. 2023, *PowerInfer*: https://arxiv.org/abs/2312.12456
- Leviathan et al. 2023, *Speculative Decoding*: https://arxiv.org/abs/2211.17192
- Elhoushi et al. 2024, *LayerSkip*: https://arxiv.org/abs/2404.16710
- Liu et al., *HiKonv*: https://arxiv.org/abs/2112.13972, https://arxiv.org/abs/2208.00763
- Wei et al. 2024, *T-MAC*: https://arxiv.org/abs/2407.00088
- Ma et al. 2024, *BitNet b1.58*: https://arxiv.org/abs/2402.17764
- Han et al. 2016, *Deep Compression*: https://arxiv.org/abs/1510.00149
- Liu et al. 2024, *MobileLLM*: https://arxiv.org/abs/2402.14905
- Kim & Rush 2016, *Sequence-Level Knowledge Distillation*: https://arxiv.org/abs/1606.07947
- Espressif esp-dsp Benchmarks: https://docs.espressif.com/projects/esp-dsp/en/latest/esp32/esp-dsp-benchmarks.html
- esp-dsp Issue zu `dsps_dotprod_s16_ae32` (447 Zyklen / 256): https://github.com/espressif/esp-dsp/issues/97
- ESP-IDF Speed Optimization (QIO/80 MHz, Flash-Cache): https://docs.espressif.com/projects/esp-idf/en/stable/esp32/api-guides/performance/speed.html
- Schraudolph 1999, *A Fast, Compact Approximation of the Exponential Function*, Neural Computation 11(4)
