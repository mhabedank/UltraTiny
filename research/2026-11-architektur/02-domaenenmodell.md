# Recherche 2: Domänenmodell mit strukturiertem Wissen

Deep-Research-Lauf vom November 2026 (Workflow `deep-research`: 5 Suchwinkel, Quellen abgerufen, jede Aussage von 3 Agenten gegengeprüft, 2 von 3 Widersprüchen streichen sie). Rohdaten: [`raw/02-domaenenmodell.json`](raw/02-domaenenmodell.json).

## Fragestellung

Context: UltraTiny is a ~0.6M-param German character-level transformer (4x128, int8, 588 KB flash) running offline on an ESP8266 (~35 KB RAM arena, no FPU, 160 MHz, 4 MB flash). Next step is a domain-specific "chemistry teacher" hybrid with a fact lookup table. Prior research found: parametric knowledge caps at ~2 bits/param, so a 0.6M model holds <150 KB of facts; flash-stored fact tables hold ~20x more. Question: For a DOMAIN-SPECIFIC assistant (e.g. school chemistry) on such a tiny device, how can we invert the design: instead of a general language model that also memorizes facts, use structured knowledge representations plus a minimal language component? Research: (1) knowledge representations that store relations/definitions/concepts compactly instead of in weights: knowledge graphs/triples, ontologies (OWL, SKOS), frames, concept maps, typed fact tables, domain-specific languages (DSLs) for a domain, rule bases/production systems, and how compact they get (bytes per fact, succinct/compressed graph encodings on MCUs); (2) neuro-symbolic and hybrid architectures where a tiny neural model only parses the question and verbalizes answers while a symbolic store/reasoner provides facts: semantic parsing to queries, knowledge-graph question answering (KGQA) with small models, template/grammar-based natural language generation, retrieval-augmented or KG-augmented tiny LMs, pointer/copy mechanisms, tool-calling small models; (3) alternative learning methods that need few weights or no gradient training: knowledge graph embeddings (TransE, RotatE, compact/quantized), hyperdimensional computing / vector symbolic architectures on MCUs, Tsetlin machines, case-based reasoning, rule induction / inductive logic programming, decision trees/expert systems, classic intent+slot NLU (e.g. Rasa/Snips-style, on-device keyword spotting style intent models on MCUs); (4) how domain-specific vs general training changes required model size and quality (domain-specific small LMs, distillation of a narrow domain, controlled vocabulary/controlled natural language), and evidence that structured knowledge + small model beats a bigger pure LM on a narrow domain; (5) concrete examples or numbers for MCU-sized or offline embedded expert/QA systems; (6) chemistry-specific structured resources that could be compiled down (periodic table data, reaction rules, ontologies like ChEBI) and a method for systematically turning a domain into a schema (domain modeling, competency questions, ontology engineering methodology) that could then be built and evaluated. Prefer concrete numbers (parameters, bytes, accuracy) and practical architectures.

## Zusammenfassung

The verified evidence supports flipping the design. The facts live in a compact symbolic store in flash. A tiny neural part only maps the question onto a query or template and turns the result into a sentence. The store is practical on the target MCU: a RAM-resident RDF triple store with SPARQL-like pattern queries already runs on the ESP8266 and answers all 14 LUBM benchmark queries in under 20 ms. A minimal MSP430 triple store needs about 1.5 KB of code and 14 bytes of static RAM. Structured facts are cheap: the triple structure takes about 1-4 bytes per fact compressed, or about 11 bytes as plain 3-integer IDs. The string dictionary (names, definitions) dominates the real footprint, and Huffman coding cuts that by about 30-35%. On the language side, narrow-schema semantic parsing does not need a big model. T5-small (60M) matches T5-base (220M). Designing the output vocabulary well adds about 17-18 accuracy points, far more than adding parameters. The task can be reduced further to classifying the question into one of a fixed set of query templates and filling slots separately. The bottleneck then moves from the neural model to slot filling, meaning entity and relation linking. That points to a deterministic lexicon or retriever rather than a learned model for that step. Small LMs (0.5B-8B) fail when they have to navigate a knowledge graph themselves; replacing that step with a lightweight retriever helps. No verified evidence yet shows this pipeline working with a model as small as 0.6M parameters, or with chemistry-specific resources.

## Befunde

### 1. A symbolic fact store with pattern queries is feasible and fast on the ESP8266 itself, with a very small code and RAM cost

**Sicherheit:** high · **Votum:** 3-0, 3-0, 3-0

A symbolic fact store with pattern queries is feasible and fast on the ESP8266 itself, with a very small code and RAM cost. µRDF runs RAM-resident on the ESP8266 and supports BGP queries (basic graph patterns, SPARQL-like), insertion and removal. All 14 LUBM queries, including the join-heavy Q9, finish in under 20 ms including EXI encoding. The Wiselib TupleStore offers insert, delete and wildcard query in about 1.5-1.6 KB ROM and 14 bytes static RAM on MSP430/TelosB. With a dictionary and a Huffman codec it needs about 6-13 KB ROM, depending on the platform.

Unanimous 3-0 votes; primary sources. The µRDF benchmarks only go up to about 10k triples, need a bound subject or object in each query, support only 32-64 distinct predicates and do no OWL reasoning. The 64 KB RAM in those tests is more than UltraTiny's ~35 KB arena, so for a larger fact base the store would have to be read from flash rather than held in RAM. The TupleStore RAM figure covers static overhead only; tuple storage is extra (2.5 KB for 76 tuples plus a dictionary in their energy test).

Quellen: <https://vcharpenay.github.io/publications/2017-eswc.pdf>, <https://arxiv.org/pdf/1402.7228>

### 2. Structured facts cost only a few bytes each; the strings cost the most

**Sicherheit:** high · **Votum:** 3-0 (k2, dictionary caveat, Bitmap Triples, BMatrix, Huffman); 2-1 (HDT 15x, DBpedia ID size)

Structured facts cost only a few bytes each; the strings cost the most. Plain dictionary encoding stores a triple as 3 integer IDs, about 11 bytes (DBpedia: 34 GB of string triples become a 2.6 GB ID collection for 232M triples). k2-tree structures shrink the ID structure to about 1.1-3.7 bytes per triple (geonames 1.8, uniprot 1.1, dbpedia 3.7). BMatrix is a further 10% smaller than k2-triples and 40-50% smaller than RDFCSA, and still answers all triple patterns. HDT's Bitmap Triples puts the triple structure at about 2-4% of the N-Triples size with direct access, and the whole HDT file is more than 15x smaller than N-Triples. None of these figures include the term dictionary, which usually dominates. Element-wise Huffman coding of the strings reliably saves about 30-35% with a 416-byte code tree. For UltraTiny this means flash will be dominated by labels and definition text, not by relations. Rough estimate (not from the sources): a few thousand chemistry triples at about 11 bytes each fit in tens of KB before any compression.

Multiple primary papers. Votes are 3-0, except the HDT >15x claim and the DBpedia 34 GB to 2.6 GB claim, which are 2-1. All compression ratios were measured on graphs with millions of triples. Small graphs with many predicates compress worse (dbpedia, with ~40k predicates, is the worst case at ~3.7 B/triple). The k2/BMatrix ratios are not MCU-tested.

Quellen: <https://arxiv.org/pdf/1105.4004>, <https://arxiv.org/pdf/2002.11622>, <https://aic.ai.wu.ac.at/~polleres/publications/fern-etal-2013-HDT-JWS.pdf>, <https://arxiv.org/pdf/1402.7228>

### 3. On a narrow schema, the neural parser that turns questions into queries can be small and needs little in-domain data; extra parameters bring little

**Sicherheit:** medium · **Votum:** 3-0 (x4)

On a narrow schema, the neural parser that turns questions into queries can be small and needs little in-domain data; extra parameters bring little. With gold entities and relations given, T5-small (60M) reaches F1 0.90/0.92 on LC-QuAD 1.0/2.0 for SPARQL generation, matching T5-base (220M; 0.91/0.91), whose extra parameters the authors say go unused. On a narrow organizational KG, 53 training pairs were enough for BART-Base (139M) to get 12.9 of 16 test queries right, and BART-Large 13.3. On open-domain Wikidata (QALD10), the same small models essentially failed: the best produced 104 parsable queries out of 394, with no correct answers. Small parsers work when the schema is narrow and entity-to-ID mappings are clear, which is exactly the setting of a school-chemistry domain.

3-0 votes on primary papers. Limits: the 60M results assume entities and relations are already linked. The 53-example result comes from a single 2024 arXiv paper with GPT-generated data, possible paraphrase leakage between training and test, and only 16 test items. All models are 100-1000x larger than 0.6M parameters, so carrying this down to UltraTiny's scale is an extrapolation. A broader claim that sub-1B seq2seq models generally translate NL to SPARQL was refuted 0-3.

Quellen: <https://arxiv.org/pdf/2204.12793>, <https://arxiv.org/html/2405.17076v1>

### 4. How the output language is designed matters more than model size, which is directly relevant to defining a compact query DSL

**Sicherheit:** medium · **Votum:** 3-0, 3-0

How the output language is designed matters more than model size, which is directly relevant to defining a compact query DSL. Replacing SPARQL keywords with single-character tokens raised exact match on masked GrailQA query skeletons by about 17-18 points: fine-tuned T5-Small went from 74.08% to 92.13%. T5-Small then nearly matched T5-Base (92.13% vs 92.61%). For UltraTiny this suggests defining a terse custom query or command DSL as the model's output, not a verbose query language or free text.

3-0 votes but a single short paper and one dataset. Entities and relations were masked, so the scores measure query structure, not end-to-end answers. The gain probably comes partly from how the T5 subword tokenizer handles special characters, which may not carry over to a character-level model. Small and Base were nearly equal even with the original vocabulary.

Quellen: <https://arxiv.org/pdf/2305.15108>

### 5. Question answering over a knowledge graph can be cut down to choosing a template plus filling slots

**Sicherheit:** medium · **Votum:** 3-0 (x4)

Question answering over a knowledge graph can be cut down to choosing a template plus filling slots. The neural part only has to classify the question into one of a fixed set of query templates with slots. QUINT learns such templates automatically from question-answer pairs alone, by aligning dependency parses with triple-pattern queries. A Tree-LSTM classifier (444-dim input, 150-dim memory, 7 epochs, about 4.9k questions) picks the right template among 38 in 82.8% of cases (94.5% when its top two guesses count) on LC-QuAD, and 61.8% (78.6% top two) on QALD-7. End-to-end macro F, however, is only about 0.42. Component scores of about 0.22-0.26 F1 for class, predicate and entity linking indicate that slot filling, not template choice, is the bottleneck. For a domain device, a small intent classifier plus a deterministic domain lexicon (element names, formulas, synonyms) for slot filling looks like the right split.

3-0 votes; primary papers. The 2020 template paper is a preprint, and it never tests slot filling with correct (gold) slots, so 'slot filling is the bottleneck' is inferred, not measured. Slot filling used off-the-shelf DBpedia tools that would be replaced here by a closed domain lexicon. A claim that a compact template set covers a benchmark (1,296 templates for WebQuestions) was refuted 0-3, so there is no verified figure for how many templates a domain needs.

Quellen: <https://arxiv.org/pdf/2004.13843>, <https://www.ccs.neu.edu/home/mirek/papers/2017-WWW-QUINT.pdf>

### 6. Small LMs should not navigate the knowledge graph themselves; a symbolic or lightweight retrieval module should pick the relevant facts

**Sicherheit:** medium · **Votum:** 3-0 (x3)

Small LMs should not navigate the knowledge graph themselves; a symbolic or lightweight retrieval module should pick the relevant facts. Small LMs (0.5B-8B) gain nothing from Think-on-Graph, where the LM walks the graph itself: mean EM is 0.217 vs 0.219 for chain-of-thought on CWQ, and 0.464 vs 0.456 on WebQSP. GPT-4.1 does improve with it (0.457 to 0.540). When GPT-4.1 does the exploration for them, the small LMs gain +0.159 (CWQ) and +0.238 (WebQSP) EM, which locates the failure in exploration. Replacing that exploration step with zero-shot dense retrievers (GTR, SentenceBERT) helps; for example Gemma2-2B on WebQSP goes from 0.382 to 0.511. BM25 gives mixed results. Applied to UltraTiny: fact selection should be deterministic (template, lookup or index), and the neural part should only phrase the result as a sentence.

3-0 votes but a single, recent (Sept 2025), non-peer-reviewed preprint. SentenceBERT hurts the smallest model (Qwen2-0.5B). The GPT-4.1 condition is an upper bound, not something deployable. Models are about 1000x larger than UltraTiny.

Quellen: <https://arxiv.org/html/2509.07399v1>

## Vorbehalte

Coverage is uneven. Surviving claims address only parts (1) and (2) of the research question and touch (4) indirectly. None of the verified claims cover OWL/SKOS/frames/DSL design, rule bases, knowledge graph embeddings (TransE/RotatE), hyperdimensional computing, Tsetlin machines, case-based reasoning or ILP. They also do not cover MCU intent-and-slot models, template or grammar-based NLG, copy or pointer mechanisms, domain-specific small-LM scaling, chemistry resources (ChEBI, periodic table data, reaction rules) or ontology-engineering methods such as competency questions. Those design directions are therefore unverified here, not refuted. Every neural result uses models of 60M parameters or more (most 0.5B-8B), 100-10,000x larger than UltraTiny's 0.6M. Whether a 0.6M char-level model can reliably do template classification and slot extraction is an extrapolation. Compression ratios (k2, HDT, BMatrix) were measured on million-to-billion-triple web graphs. A school-chemistry KB with a few thousand facts will be dominated by its string dictionary and per-structure overhead, so absolute flash needs must be measured directly. The ESP8266 store results come from a 2017 two-page demo paper with ≤10k triples held in 64 KB RAM, more than UltraTiny's ~35 KB arena. Several key sources are arXiv preprints (2004.13843, 2405.17076, 2509.07399, 1402.7228). Causal statements ('slot filling is the bottleneck', 'extra parameters unused') are the authors' interpretations. Two claims were refuted: the general 'sub-1B seq2seq does NL-to-SPARQL' framing and the QUINT template-count figures.

## Offene Fragen

- Can a ~0.6M-param char-level model (or a much smaller intent classifier, e.g. keyword-spotting-sized) classify German chemistry questions into a fixed set of templates with >90% accuracy, and how many templates does a school-chemistry curriculum need?
- What is the actual flash footprint of a school-chemistry KB (e.g. 118 elements × properties, a few hundred compounds, reaction classes, definitions) once dictionary strings and definitions are included and stored with Huffman/prefix coding plus a flash-resident triple index?
- Does template- or grammar-based German answer generation from retrieved facts beat a neural verbalizer at this scale, and how much of UltraTiny's 588 KB could be freed for facts if the LM only handles parsing and light phrasing?
- Which unverified approaches (hyperdimensional computing, Tsetlin machines, quantized KG embeddings, rule/production systems derived from ontologies like ChEBI via competency questions) give measurable gains on an MCU for this task? This needs a targeted follow-up search.

## Widerlegte Aussagen

- (0-3) After fine-tuning, seq2seq models with fewer than 1B parameters (T5, BART, M2M100, NLLB families; 60M to 783M params) can translate natural-language questions into SPARQL queries over a knowledge graph. This supports a 'small model parses the question, KG supplies the facts' architecture, although all the models tested are about 100 to 1000 times larger than a 0.6M MCU model. — <https://arxiv.org/html/2405.17076v1>
- (0-3) A compact set of templates covers a QA benchmark: 3,778 WebQuestions training questions produced 1,296 distinct templates, and 641 Free917 training questions produced 284. — <https://www.ccs.neu.edu/home/mirek/papers/2017-WWW-QUINT.pdf>

## Statistik

```json
{"angles": 5, "sourcesFetched": 22, "claimsExtracted": 100, "claimsVerified": 25, "confirmed": 23, "killed": 2, "unverified": 0, "afterSynthesis": 6, "urlDupes": 0, "budgetDropped": 8, "agentCalls": 104}
```
