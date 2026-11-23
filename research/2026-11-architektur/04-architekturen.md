# Recherche 4: Andere und neue Architekturen

Deep-Research-Lauf vom November 2026 (Workflow `deep-research`: 5 Suchwinkel, Quellen abgerufen, jede Aussage von 3 Agenten gegengeprüft, 2 von 3 Widersprüchen streichen sie). Rohdaten: [`raw/04-architekturen.json`](raw/04-architekturen.json).

## Fragestellung

Context: UltraTiny is a ~0.6M-param German character-level transformer (4x128, MQA, int8 weights read from flash, 588 KB) running offline on an ESP8266 (~35 KB RAM arena, no FPU, no SIMD, 160 MHz single core, 4 MB flash read in 32-bit words, ~5 chars/s). Findings so far: (a) recurrent/state-space models (RWKV, Mamba, gated diagonal SSMs) give fixed-size state and beat transformers at ~60K params; (b) knowledge caps at ~2 bits/param, so facts belong in a compiled symbolic store in flash (triples, dictionary dominates cost), reasoning is materialized offline at build time, and a tiny neural part only classifies question->template while a lexicon fills slots and templates generate answers; (c) a terse output DSL beats model size; (d) every established building block (rule engines, dictionary compression, KG embeddings trained with quantization, HDC with associative memory/SDM) has measurable headroom. Question (A): Beyond transformers and Mamba, which other architectures fit this regime and could be better: RWKV-7 and other linear RNNs (xLSTM/mLSTM/sLSTM, minGRU/minLSTM, Griffin/Hawk, RetNet, HGRN), liquid/CfC networks, echo state / reservoir computing, Hopfield and modern Hopfield networks as associative memory, Sparse Distributed Memory, n-gram/ infini-gram / PPM / context-mixing compressors as language models (paq/cmix-style, compression = prediction), weighted finite-state transducers and grammars, Tsetlin machines, HDC/VSA language models, lookup-table networks (LUT-based / LogicNets / differentiable logic gate networks, which are multiplication-free and could suit a no-FPU MCU), binary/ternary networks, kNN-LM / retrieval-based LMs (memory in flash instead of weights), product-key memory layers / memory layers at scale (large flash-resident memory tables with sparse lookup), mixture-of-experts with flash-streamed experts, early-exit / adaptive computation. Give concrete numbers (params, bytes, perplexity or bits-per-char, speed on MCUs) where available. Question (B): From this regime's unusual constraints (flash is huge and cheap relative to RAM, ~100:1; compute without FPU; reads in 32-bit words; tiny RAM; one narrow domain; facts in a symbolic store), which novel or rarely combined architectures are motivated? Examples to evaluate with evidence: flash-resident sparse memory/lookup layers (product keys, hashed n-gram embeddings like Engram/ hash embeddings) where most parameters live in flash and only a few rows are read per token; logic-gate or LUT networks compiled to integer code; a recurrent core plus a pointer/copy head into the symbolic store; compression-model (PPM/context mixing) plus small neural mixer; HDC associative memory as the attention replacement; neural-symbolic decoders constrained by a grammar of the domain DSL. Identify which of these have published evidence, which are open/unexplored (research gaps), and what minimal experiments would test them. Prefer concrete numbers and recent (2023-2026) work.

## Zusammenfassung

Kurzantwort zu (A): Ja, wir sollten vom Transformer weggehen. Belegt sind dafür aber nur rekurrente Kerne. Minimale gegatete RNNs (minGRU/minLSTM) erreichen im Char-Level-LM bei kleinen Modellen praktisch die Transformer-Loss (1,548 bzw. 1,555 gegenüber 1,547; Mamba 1,575). Sie brauchen dabei einen festen Zustand ohne KV-Cache, und ihre Gates hängen nur von der Eingabe ab. RWKV und xLSTM bieten ebenfalls konstanten Speicher. Ihre Matrix-Zustände (RWKV-5/6/7, mLSTM) sind bei d=128 aber so groß, dass sie die 35-KB-Arena gefährden. Für das ESP8266 passen deshalb Vektor-Zustandsmodelle am besten: minGRU/minLSTM, sLSTM, RWKV-4-artig oder RWKV-7 mit kleinem Head. Zu (B): Die stärkste Evidenz spricht für hybride Architekturen. Ein zählbasiertes oder Lookup-Modell (n-gram, ∞-gram, gehashte N-gram-Embeddings) wird mit einem kleinen neuronalen Teil gemischt. Das schlägt neuronale Modelle allein (bis −73 % Perplexity im Bestfall). Ein winziges Gate mit höchstens 2.572 Parametern genügt, und billige Count-Features als Entscheidungsgrundlage reichen dafür. Mit Engram (DeepSeek, 2026) gibt es außerdem einen aktuellen Beleg, dass große, in langsamen Speicher ausgelagerte Hash-Tabellen mit O(1)-Lookup weniger als 3 % Durchsatz kosten. Das ist die direkte Analogie zu unserem Verhältnis Flash:RAM ≈ 100:1. Ein flash-residenter, gehashter Char-N-gram-Speicher plus kleiner rekurrenter Kern plus Mischer ist in genau unserem Regime (MCU, ohne FPU, unter 1M Parameter) unseres Wissens unveröffentlicht. Das ist eine echte Forschungslücke, die wir besetzen könnten. Zu den übrigen Kandidaten aus der Frage hat keine einzige Behauptung die Verifikation überstanden (Tsetlin, LUT- und Logikgatter-Netze, HDC-LMs, Hopfield, ESN, Liquid/CfC, Product-Key-Memory, Flash-MoE, Early-Exit, grammatik-beschränktes Decoding). Für sie liefert diese Runde keine belastbaren Zahlen.

## Befunde

### 1. Minimale gegatete RNNs (minGRU/minLSTM) sind für UltraTiny der naheliegendste Ersatz für den Transformer

**Sicherheit:** medium

Minimale gegatete RNNs (minGRU/minLSTM) sind für UltraTiny der naheliegendste Ersatz für den Transformer. Im Char-Level-LM (Shakespeare, 3 Layer, d=384) erreichen sie praktisch dieselbe Test-Loss wie ein Transformer und etwas bessere als Mamba: minGRU 1,548, minLSTM 1,555, Mamba 1,575, Transformer 1,547. Gates und Kandidatenzustand hängen nur von x_t ab (h_t = (1−z_t)·h_{t−1} + z_t·h~_t mit z_t = σ(Linear(x_t))). Bei der Inferenz ist das eine elementweise Rekurrenz mit festem Vektor-Zustand (d_h Werte pro Layer, ohne KV-Cache), und Training ist per Parallel-Scan möglich. Für das ESP8266 folgt daraus (eigene Ableitung): Es gibt keine h-abhängige Matmul, der Zustand bei 4×128 liegt bei rund 512 Werten, und Sigmoid lässt sich als Integer-LUT umsetzen.

Votes 3-0 und 3-0, Primärquelle (Feng et al. 2024, Bengio Koautor). Einschränkungen: nur ein kleiner Datensatz (ca. 1M Tokens), Werte mit Early Stopping, keine Seeds oder Fehlerbalken, Modell ca. 5M Parameter, also etwa 10× UltraTiny. Der Abstand zu Mamba liegt vermutlich im Rauschen. Die Gates sind zeitinvariant in h, deshalb ist State-Tracking schwächer.

Quellen: <https://arxiv.org/abs/2410.01201>

### 2. RWKV hat konstanten Speicher und konstante Zeit pro Token und ist ausdrucksstark, aber die Zustandsgröße hängt von der Version ab

**Sicherheit:** high

RWKV hat konstanten Speicher und konstante Zeit pro Token und ist ausdrucksstark, aber die Zustandsgröße hängt von der Version ab. RWKV-4 hat einen O(d)-Vektorzustand und erreicht auf enwik8 (12×512) 1,178 bpc. Das ist etwa 0,04 bpc schlechter als ein Transformer (1,137), aber besser als alle effizienten Attention-Varianten (Reformer 1,195, Performer 1,199, Linear Transformer 1,207, AFT 1,209, Synthesizer 1,298). RWKV-7 nutzt eine verallgemeinerte Delta-Regel mit vektorwertigem Gating. Damit kann es nachweislich State-Tracking leisten und alle regulären Sprachen erkennen, was über die TC0-Grenze von Transformern hinausgeht (unter Standard-Komplexitätsvermutungen). Sein Matrix-Zustand (Head 64×64) läge bei d=128 und 4 Layern aber bei etwa 32K Werten: rund 32 KB in int8, rund 128 KB in fp32. Das passt nicht neben den Rest der 35-KB-Arena, solange Head-Größe oder Präzision nicht reduziert werden.

Zwei Primärpaper, alle Votes 3-0. Der enwik8-Vergleich ist nicht kontrolliert (unterschiedliche Regularisierung) und gilt für ca. 40M Parameter. Die Ausdrucksstärke von RWKV-7 ist ein theoretisches Ergebnis darüber, was sich darstellen lässt, keine Garantie, dass es bei 0,6M Parametern auch gelernt wird.

Quellen: <https://arxiv.org/pdf/2305.13048>, <https://arxiv.org/pdf/2503.14456v2>

### 3. xLSTM ist bei rund 400M Parametern Spitzenreiter

**Sicherheit:** medium

xLSTM ist bei rund 400M Parametern Spitzenreiter. Die Erkenntnisse übertragen sich aber nur teilweise auf uns: Für ein MCU passt sLSTM (Vektorzustand), mLSTM eher nicht. Auf 15B SlimPajama-Tokens erreicht xLSTM[1:0] eine Perplexity von 13,43 und xLSTM[7:1] 13,48. Alle Baselines liegen darüber: Mamba 13,70, Llama 14,25, RWKV-5 14,25, HGRN2 14,32, RWKV-6 15,03, RWKV-4 15,62, RetNet 16,23, HGRN 17,59. Die Rechenzeit ist linear, der Speicher konstant, und die Autoren nennen xLSTM ausdrücklich edge-tauglich. Der mLSTM-Zustand (d_head×d_head pro Head) läge bei 4×128 mit einem Head aber bei rund 65K Werten (ca. 256 KB fp32). sLSTM braucht nur wenige KB. Die exponentiellen Gates mit laufendem Max-Stabilisator sind auf einem Chip ohne FPU unhandlich.

Votes 3-0 (für die Edge-Aussage medium). Eine Primärquelle (NeurIPS 2024), alle Baselines selbst trainiert, keine LM-Ergebnisse unter 125M Parametern, keine MCU-Messungen.

Quellen: <https://arxiv.org/pdf/2405.04517>

### 4. Hybride aus Zähl- bzw

**Sicherheit:** high

Hybride aus Zähl- bzw. Retrieval-Modell und neuronalem Modell schlagen das neuronale Modell allein. Das Gate dafür kann winzig sein und mit billigen symbolischen Features auskommen. Die Interpolation eines ∞-gram-LM mit neuronalen LMs senkt die Perplexity um bis zu 73 % (Bestfall GPT-2 small) und verbessert selbst Llama-2 70B noch um 12 %. Ein Gate mit höchstens 2.572 Parametern, das pro Token zwischen einem eingefrorenen 5-gram-KN-LM und einem eingefrorenen LSTM mischt, schlägt das statische Ensemble auf 1B Word (28,70 statt 29,80). Zum Vergleich: n-gram allein 66,96, LSTM allein 33,01. Schon 11 SIMPLE-Features, nämlich die Backoff-Gewichte und diskontierten Wahrscheinlichkeiten des n-gram-Modells plus log(Position), schlagen ein Gate auf dem 1024-dimensionalen Hidden-State (28,88 statt 29,72). Für uns heißt das: Ein PPM- oder n-gram-Modell im Flash, ein kleiner RNN-Kern und ein Mischer mit nur wenigen hundert Parametern sind gut motiviert.

Zwei unabhängige Primärquellen, alle Votes 3-0. Die 73 % sind ein ausgewählter Bestfall: Der Gewinn hängt fast vollständig an In-Domain-Referenzdaten, und die Referenzspeicher umfassen 360B bis 1,4T Tokens. Auf WSJ ist SIMPLE knapp schlechter als HIDDEN. Beide Arbeiten sind wortbasiert und laufen auf GPUs. Positiv für uns: Unsere enge Domäne ist genau der In-Domain-Fall, in dem diese Hybride am meisten gewinnen.

Quellen: <https://arxiv.org/abs/2401.17377>, <https://arxiv.org/pdf/1804.07705v2.pdf>

### 5. Kompression als Vorhersage: Context-Mixing ist auf kleineren Daten gleich gut oder besser als ein neuronales Modell, das neuronale Modell gewinnt erst bei großen Datenmengen, und die besten Systeme sind Hybride

**Sicherheit:** medium

Kompression als Vorhersage: Context-Mixing ist auf kleineren Daten gleich gut oder besser als ein neuronales Modell, das neuronale Modell gewinnt erst bei großen Datenmengen, und die besten Systeme sind Hybride. Auf enwik9 kommt NNCP (Transformer, online trainiert) auf 0,853 bpb gegenüber 0,892 bei CMIX v19. Auf enwik8 (100 MB) liegen beide bei 1,19 bpb, CMIX sogar knapp kleiner. cmix selbst ist ein Hybrid aus 2.090 Einzelmodellen (v20), einem LSTM-Mixer und SSE-Nachkorrektur. Nacrith (SmolLM2-135M plus Token-n-gram plus Context-Mixer) erreicht 0,918 bpb auf alice29 (CMIX v21 1,635, PAQ8px 1,728) und 0,9389 bpb auf enwik8. Es zählt aber die ca. 500 MB Gewichte nicht mit. Für ein Modell mit 0,6M Parametern und wenigen MB In-Domain-Text spricht das für PPM/CM als Basis und das neuronale Netz als Mischer oder Korrektor, nicht umgekehrt.

NNCP/CMIX und cmix-Architektur mit 3-0 bestätigt. Die These, dass Context-Mixing auf kleinen Daten gleichauf ist, stützt sich nur auf zwei Datenpunkte (2-1). Nacrith (2-1) ist ein Preprint eines Einzelautors, die Testdaten stecken vermutlich im Training, und der Vergleich ist nicht gleichwertig. Die Ablation zum Nacrith-n-gram-Skip wurde widerlegt (0-3). Alle Ergebnisse stammen von PC- oder GPU-Systemen, die um Größenordnungen langsamer bzw. größer sind als unser Budget erlaubt.

Quellen: <https://bellard.org/nncp/>, <https://gwern.net/doc/www/www.byronknoll.com/2fcab2e668d671915958f32dc7e5d4607a1bd18b.html>, <https://arxiv.org/html/2602.19626v2>

### 6. Flash-residente Lookup-Speicher sind aktuell belegt

**Sicherheit:** medium

Flash-residente Lookup-Speicher sind aktuell belegt. Das ist die stärkste Motivation für eine neue Architektur in unserem Regime. Engram (DeepSeek/PKU, Jan. 2026) modernisiert gehashte N-gram-Embeddings: O(1)-Lookups anhand der N-gram-Identität, K Hash-Köpfe pro Ordnung gegen Kollisionen, und das Ganze als zweite Sparsity-Achse neben MoE. Optimal ist, etwa 20–25 % des Sparse-Budgets in Engram zu stecken. Im 10B-Regime sinkt die Loss dabei von 1,7248 auf 1,7109, und der Verlauf ist U-förmig. Eine 100B-Parameter-Tabelle im Host-DRAM kostet weniger als 3 % Durchsatz (H800: 4B dense 9.032 → 8.858 tok/s, 8B dense 6.316 → 6.140 tok/s). Übertragen auf uns (eigene Ableitung, ungeprüft): eine gehashte Char-N-gram-Tabelle (n = 2…6) mit z. B. 64K Zeilen × 32 B ≈ 2 MB im Flash. Pro Zeichen würden etwa 4 Ordnungen × 2 Köpfe = 8 Zeilen ≈ 256 B gelesen. Damit landen die meisten Parameter im Flash, während RAM und Rechenzeit pro Token klein bleiben. Die Indizes stehen fest, bevor gerechnet wird, deshalb sind sie vorab bekannt.

Votes 3-0, aber nur eine Primärquelle ohne Replikation, gemessen bei 4B–10B Parametern. Der Gewinn ist klein (ΔLoss ≈ 0,014). Die geringen Offload-Kosten beruhen darauf, dass PCIe-Transfer und GPU-Rechnung überlappen. Das ESP8266 hat einen Kern und einen kleinen Flash-Cache, dort addieren sich zufällige Flash-Lesezugriffe direkt zur Rechenzeit. Die 23 % Vokabularreduktion gilt nur für einen 128k-BPE-Tokenizer und ist für Char-Level irrelevant.

Quellen: <https://arxiv.org/html/2601.07372v1>

### 7. Die Kompressionstricks für RWKV (Low-Rank-SVD, FFN-Sparsity, Embedding-Cache, hierarchischer Head) verkleinern den Speicherbedarf um das 3,4- bis 5-fache bei etwa 1–1,5 Prozentpunkten Verlust auf LAMBADA, zusammen mit INT8 um etwa das 10-fache

**Sicherheit:** medium

Die Kompressionstricks für RWKV (Low-Rank-SVD, FFN-Sparsity, Embedding-Cache, hierarchischer Head) verkleinern den Speicherbedarf um das 3,4- bis 5-fache bei etwa 1–1,5 Prozentpunkten Verlust auf LAMBADA, zusammen mit INT8 um etwa das 10-fache. Gegenüber Transformern mit ähnlicher Genauigkeit brauchen sie 3–4× weniger Speicher, ohne dass deren KV-Cache mitgezählt wird. Für ein Char-Level-Modell mit 0,6M Parametern tragen davon nur Low-Rank und Sparsity bei. Cache und hierarchischer Head helfen nur bei großem Vokabular.

Votes 3-0, eine Primärquelle als Preprint ohne Replikation. Die Modelle haben 100M+ Parameter und zielen auf Smartphones bzw. Raspberry Pi.

Quellen: <https://arxiv.org/html/2412.10856v3>

### 8. Negativbefund: Die gefundene n-gram-Plattform HITgram ist als Evidenz unbrauchbar

**Sicherheit:** high

Negativbefund: Die gefundene n-gram-Plattform HITgram ist als Evidenz unbrauchbar. Ihre Perplexity (bigram 4,1–4,5, trigram 2,0–2,6) ist nur auf dem Satz 'this is a' gemessen. Es gibt keinen Vergleich mit neuronalen Modellen, keine Ergebnisse zu Char-Level, PPM oder MCU, und Hybride aus n-gram und neuronalem Netz werden nur als Zukunftsarbeit genannt.

Votes 3-0. Die Aussage bewertet nur diese eine Quelle, nicht das Forschungsfeld.

Quellen: <https://arxiv.org/pdf/2412.10717>

## Vorbehalte

1) Fast alle Zahlen stammen aus Regimen, die um Größenordnungen größer sind (5M bis 10B Parameter, GPU, Datenmengen von 100 MB bis Billionen Tokens). Unter 1M Parametern, ohne FPU und auf einem MCU hat keine Quelle gemessen. Jede Übertragung auf das ESP8266 ist Extrapolation. 2) Große Lücke in der Abdeckung: Für Tsetlin-Maschinen, LUT- und differenzierbare Logikgatter-Netze (LogicNets, difflogic), binäre und ternäre Netze, HDC/VSA-Sprachmodelle, (moderne) Hopfield-Netze, SDM, Echo State Networks, Liquid/CfC, Griffin/Hawk, RetNet und HGRN im Detail, kNN-LM, Product-Key- und Memory-Layer, Flash-gestreamtes MoE, Early-Exit und grammatik-beschränktes Decoding hat in dieser Runde keine Behauptung die Verifikation überstanden. Ob diese Ansätze besser oder schlechter sind, ist damit offen und nicht widerlegt. Für (B) sind 'Logikgatter-Netze als Integer-Code', 'HDC als Attention-Ersatz' und ein 'Pointer/Copy-Head in den symbolischen Speicher' deshalb unbelegt. 3) Widerlegt (0-3) wurde die Aussage, ∞-gram sage 47 % der Tokens richtig vorher (über 75 % bei n ≥ 16). Ebenfalls widerlegt (1-2) sind die exakten cmix-v20-Größen für enwik8/9. 4) Mehrere Quellen sind Preprints ohne Replikation (Nacrith als Einzelautor, RWKV-Kompression, Engram), und die Votes zu NNCP auf enwik8 und zu Nacrith fielen 2-1 aus. 5) Die Größenangaben für die Zustände (RWKV-7 ca. 32 KB int8, mLSTM ca. 256 KB fp32) haben die Verifier selbst überschlagen. Sie sind nicht aus den Papern übernommen. 6) Dass eine Kombination 'nur wir umsetzen können', lässt sich aus der Recherche nicht beweisen. Belegt ist nur, dass keine geprüfte Quelle die Kombination aus rekurrentem Vektorzustands-Kern, flash-residentem Hash-N-gram-/PPM-Speicher und winzigem Count-Feature-Gate auf einem MCU untersucht.

## Offene Fragen

- Minimal-Experiment 1 (Kern): Auf unserem deutschen Domänenkorpus bei 60K, 200K und 600K Parametern bpc und RAM für Transformer-MQA (Ist-Zustand), minGRU/minLSTM, sLSTM und RWKV-7 mit Head 16–32 vergleichen, int8-quantisiert und in Integer-Arithmetik simuliert. Gemessen werden bpc, Zustand in Byte, Zeichen pro Sekunde auf dem ESP8266. Hält minGRU auch bei unter 1M Parametern mit dem Transformer mit?
- Minimal-Experiment 2 (Flash-Speicher): Ändert sich bpc und Template-Accuracy, wenn man einen kleinen RNN-Kern mit einer gehashten Char-N-gram-Tabelle im Flash (Engram-artig, 0,5–3 MB, K = 2 Hash-Köpfe, n = 2…6) ergänzt, verglichen mit einem gleich großen reinen RNN-Kern? Kosten zufällige 32-Byte-Flash-Reads pro Zeichen auf dem ESP8266 (Cache-Misses) mehr als die eingesparte Matmul-Rechnung? Wie ist die U-Kurve (Anteil Flash- vs. Dense-Parameter) in diesem Regime?
- Minimal-Experiment 3 (Kompressions-Hybrid): Schlägt PPM bzw. ein Char-n-gram-Modell der Ordnung 5–8 aus dem Domänenkorpus im Flash, gemischt mit einem 4×64-RNN über ein Gate mit unter 1K Parametern und Count-Features (Backoff, Ordnung, Entropie), das aktuelle 0,6M-Transformer-Modell bei bpc und Antwortqualität, und das bei weniger RAM?
- Ungeprüft geblieben: Wie schneiden multiplikationsfreie Ansätze (differenzierbare Logikgatter- oder LUT-Netze, Tsetlin, ternäre Gewichte) und HDC-/SDM-Assoziativspeicher bei Char-LM oder Frage→Template-Klassifikation in Zahlen ab, und bringt grammatik-beschränktes Decoding der DSL messbare Fehlerreduktion bei sehr kleinen Modellen? Dafür braucht es eine gezielte Folgerecherche.

## Widerlegte Aussagen

- (0-3) An unbounded-n (infinity-gram) LM with backoff, served from a suffix array rather than precomputed count tables, predicts the next token of human-written text correctly 47% of the time, rising above 75% when the matched context (effective n) is at least 16 tokens. This supports using a flash-resident suffix or n-gram index as a non-parametric predictor. — <https://arxiv.org/abs/2401.17377>
- (0-3) In the ablation on alice29, most of the gain comes from adding a token n-gram model (orders 1-4) with a confidence-based skip, which bypasses the LLM when n-gram entropy is below 1.5 bits: −0.401 bpb, from 1.341 to 0.940. The adaptive bias head adds only −0.017 and the full mixer −0.001. Note the source does not explain how this squares with the large CDF precision gain. — <https://arxiv.org/html/2602.19626v2>
- (1-2) cmix v20 (context-mixing compressor, i.e. a compression-as-prediction LM) compresses enwik8 (100,000,000 bytes) to 14,760,552 bytes, about 1.18 bits per char, and enwik9 to 109,877,715 bytes, about 0.88 bpc. The bpc figures are derived from the listed sizes. This is a state-of-the-art character-level prediction baseline, but one that uses enormous resources. — <https://gwern.net/doc/www/www.byronknoll.com/2fcab2e668d671915958f32dc7e5d4607a1bd18b.html>

## Statistik

```json
{"angles": 5, "sourcesFetched": 21, "claimsExtracted": 105, "claimsVerified": 25, "confirmed": 22, "killed": 3, "unverified": 0, "afterSynthesis": 8, "urlDupes": 0, "budgetDropped": 9, "agentCalls": 103}
```
