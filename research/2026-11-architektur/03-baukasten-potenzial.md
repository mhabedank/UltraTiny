# Recherche 3: Themenunabhängiger Baukasten und ungenutztes Potenzial

Deep-Research-Lauf vom November 2026 (Workflow `deep-research`: 5 Suchwinkel, Quellen abgerufen, jede Aussage von 3 Agenten gegengeprüft, 2 von 3 Widersprüchen streichen sie). Rohdaten: [`raw/03-baukasten-potenzial.json`](raw/03-baukasten-potenzial.json).

## Fragestellung

Context: UltraTiny is a ~0.6M-param German character-level transformer (4x128, int8, 588 KB flash) running offline on an ESP8266 (~35 KB RAM arena, no FPU, 160 MHz, 4 MB flash). Goal: a GENERIC, domain-agnostic framework for building tiny domain-specific assistants for ANY topic (chemistry is only one example; others could be biology, history, a product manual, a game rulebook, local transport). Already established from earlier research: invert the design so facts live in a compact symbolic store in flash (triples ~1-11 bytes each, strings dominate; a RAM triple store with BGP queries runs on ESP8266 in <20 ms) and a small neural part only classifies the question into a query template, while slot filling uses a deterministic lexicon and answers come from templates; a terse output DSL improved accuracy ~18 points more than model size did; small models fail at navigating a KG themselves. Two research goals: (A) Fill the gaps not yet covered, each with concrete numbers and MCU feasibility: ontologies/SKOS/frames and how to compile them to compact runtime tables; rule bases/production systems and forward/backward chaining on MCUs (e.g. CLIPS-like, Rete); knowledge graph embeddings (TransE, RotatE, quantized/binary KG embeddings) for link prediction and inferring missing facts; hyperdimensional computing / vector symbolic architectures (binding, bundling, associative memory, on-MCU results, bits per stored fact); Tsetlin machines for text/intent classification on MCUs; case-based reasoning; tiny intent+slot NLU models on MCUs (keyword spotting-sized, bytes and accuracy); template/grammar-based NLG for German; and a domain-agnostic methodology to turn any topic into a schema (competency questions, ontology engineering like NeOn/METHONTOLOGY, automatic schema/KG extraction from text with large LLMs, then compiling down). (B) For each established approach (triple stores/succinct graph encodings, semantic parsing to queries, template classification, slot filling/entity linking, KG embeddings, HDC, Tsetlin machines, rule engines, template NLG), identify where it is known to be NOT at its optimum: documented limitations, open problems, recent improvements, unexploited optimizations, and promising combinations (e.g. HDC as associative fact memory plus symbolic store, learned lexicons, constrained decoding with grammar for tiny models, joint compression of dictionary and structure, distilling an LLM into a template classifier). Assume nothing is at the absolute optimum; look for concrete headroom with evidence (ablations, gaps between theory and practice, recent papers beating older baselines). Prefer concrete numbers and practical architectures.

## Zusammenfassung

For a topic-independent framework of tiny offline assistants, the verified evidence supports the inverted design: facts go in a compiled symbolic store in flash, and the neural network only does classification. The evidence also shows measurable headroom in every established building block. (1) Rule and ontology reasoning: full RETE or Description Logic engines on MCUs top out at a few hundred facts or axioms even with 96-520 KB of SRAM. On a 35 KB ESP8266, reasoning should run offline at build time, using an OWL 2 RL-style rule subset to materialize the inferred facts, and the device should only look them up. (2) Storage: in compressed RDF stores the string dictionary, not the graph structure, is the dominant cost (about 2-5x the structure). Predicate-local IDs (HDT++) and component-specific entropy coding each showed savings of 2x or more over the standard encodings. This makes the dictionary the main compression target for any domain. (3) KG embeddings for inferring missing facts can be shrunk by 32x to about 1000x, provided quantization is trained in rather than applied after training. Naive post-hoc binarization collapses accuracy. (4) Hyperdimensional computing works on MCUs, and its naive implementations waste 50-98% of resources. However, a single bundled vector is a poor large fact store: Sparse Distributed Memory-style associative memories beat it by 15-35x in storage (when the item memory has to be stored) and 37-135x in recall operations. Several research-goal gaps (Tsetlin machines, on-MCU intent and slot NLU, German template NLG, case-based reasoning, SKOS compilation, schema-engineering methodology) produced no surviving verified claims and remain open.

## Befunde

### 1. Running a full rule engine or reasoner on the device does not scale to a 35 KB RAM budget, for any topic

**Sicherheit:** high · **Votum:** 3-0

Running a full rule engine or reasoner on the device does not scale to a 35 KB RAM budget, for any topic. A LiRoT RETE forward-chainer (C, RDFS-Simple rules) held at most 760 facts (ontology + explicit + inferred) on an ESP32 with 520 KB SRAM and 349 on an Arduino Due with 96 KB. Linear scaling suggests roughly 100 facts in about 35 KB before code overhead. The framework should therefore compute the rule closure offline at build time and ship the materialized facts, or precompiled rule tables, in flash.

Bento et al. (ESWC 2022), Table 1: ESP32 509 facts baseline, 760 for LiRoT; Due 240 baseline, 349 for LiRoT; load about 200 ms (ESP32) and 550 ms (Due). The ESP8266 figure is an extrapolation, not a measurement. The limit belongs to this implementation (Sord store, string terms, provenance lists for deletion support), so it is not a law for every RETE engine.

Quellen: <https://2022.eswc-conferences.org/wp-content/uploads/2022/05/paper_39_Bento_et_al.pdf>

### 2. Classic RETE is far from its memory optimum, which shows headroom in rule engines

**Sicherheit:** medium · **Votum:** 2-1

Classic RETE is far from its memory optimum, which shows headroom in rule engines. Two cheap optimizations, merging alpha memories with syntactically similar conditions and interning terms in a hash table, together raise on-device fact capacity by 45-49% at similar execution time. Further gains are plausible from integer IDs, dropping incremental-deletion support, or compiling rules ahead of time.

ESP32: 509 -> 656 (alpha sharing) -> 672 (term index) -> 760 (both, +49%). Due: 240 -> 349 (+45%). On desktop the paper also reports memory savings of up to 32% (RDFS-Simple) and 41% (RDFS-Full), and a 37% time reduction for RDFS-Full. The split vote reflects that 'far from optimum' is an interpretation, and that the paper's own +22% figure is a miscalculation (656/509 is actually +29%).

Quellen: <https://2022.eswc-conferences.org/wp-content/uploads/2022/05/paper_39_Bento_et_al.pdf>

### 3. Full OWL DL reasoning is out of reach on microcontrollers

**Sicherheit:** high · **Votum:** 3-0

Full OWL DL reasoning is out of reach on microcontrollers. The workable path is a restricted ontology profile: OWL 2 RL is defined so that a rule or production system can implement it, and this has been built for embedded hardware. Even then, the best MCU DL result (Tiny-ME 1.3, written in C, ALN(D) logic, Arduino Due with 96 KiB) classified only 67.2% of 1,498 ORE 2014 ontologies, averaging 44.59 KiB of RAM. It handles about 400 axioms without problems and fails with out-of-memory errors 80% of the time at about 500. Reasoning roughly halves the axiom count that fits compared with parsing alone (about 900). For an ESP8266, ontology or frame reasoning must be compiled away offline into flat lookup tables.

Seitz and Schoenfelder (ISWC 2011 workshop): sound and complete DL reasoners are too complex for embedded systems, so they used OWL 2 RL with a rule engine on a 400 MHz, 64 MB board. Bilenchi PhD thesis (2024), Fig. 3.15: 1006/1498 ontologies classified, largest 290 KiB, average 44.59 KiB and peak 94.77 KiB RAM. Stream-based parsing without reasoning processed 99.5% of ontologies, up to 563 MiB. This supports streaming or flash-resident data plus precomputed inferences.

Quellen: <https://link.springer.com/doi/10.1007/978-3-642-25093-4_16>, <https://iris.poliba.it/bitstream/11589/269380/1/36%20ciclo-BILENCHI%20Ivano.pdf>

### 4. In compact RDF/KG stores the string dictionary is the dominant cost, so dictionary compression is where the main storage headroom lies for any domain

**Sicherheit:** high · **Votum:** 3-0

In compact RDF/KG stores the string dictionary is the dominant cost, so dictionary compression is where the main storage headroom lies for any domain. A plain HDT dictionary is 4.5-14.1% of N-Triples size, against 2.09-4.05% for Bitmap Triples (about 2.2-5.3x larger). Bitmap Triples itself (adjacency lists with rank/select bitsequences) is the most compact of the three HDT encodings tested and still allows direct access: Plain 6.9-12%, Compact 2.45-6.16%, Bitmap 2.09-4.05%.

Fernandez et al. 2013, J. Web Semantics, Table 1. Geonames: dictionary 12.54% vs triples 2.91%. DBpedia-en: 14.10% vs 2.66%. Weaker ratios: Wikipedia about 2.2x, Uniprot about 2.7x. Data is from 2013 and uses the uncompressed Plain dictionary; later front-coded and compressed string dictionaries narrow the gap. This matches the earlier project finding that strings dominate triple storage.

Quellen: <https://aic.ai.wu.ac.at/~polleres/publications/fern-etal-2013-HDT-JWS.pdf>

### 5. Standard succinct triple encodings leave structural redundancy unused, and schema-aware re-encoding recovers up to 2x

**Sicherheit:** high · **Votum:** 3-0

Standard succinct triple encodings leave structural redundancy unused, and schema-aware re-encoding recovers up to 2x. HDT++ groups subjects into predicate families and gives each predicate its own local object IDs, since objects almost always belong to a single predicate (mean predicates per object is close to 1). This cut the Triples component from 649 MB to 313 MB (US Census), 242 MB to 132 MB (dbtune), 22.5 MB to 14.2 MB (linkedmdb), and 1839 MB to 1524 MB (dbpedia, about 17%). For a small domain store this suggests per-predicate local ID spaces with fewer bits per object (5 bits down to 2-3 bits in the paper's toy example), which fits the framework's template and slot structure naturally.

Hernandez-Illera, Martinez-Prieto and Fernandez, DCC 2015 short paper, Table 2 and Fig. 3. Caveats: it is a prototype evaluation. k2-triples beat HDT++ on linkedmdb (9.02 MB). The local IDs need an extra PermO permutation, whose cost partly offsets the savings. Small hand-built domain KGs with many shared literals (units, numbers, booleans) may not show the 'one predicate per object' property.

Quellen: <https://aic.ai.wu.ac.at/qadlod/docs/dcc15.pdf>

### 6. Structure-aware compression of the store's components beats generic compressors by a clear margin: HDT-Compress (PPM on the dictionary, separate Huffman codes for the predicate and object ID sequences) reaches 2-4% of N-Triples size

**Sicherheit:** medium · **Votum:** 2-1

Structure-aware compression of the store's components beats generic compressors by a clear margin: HDT-Compress (PPM on the dictionary, separate Huffman codes for the predicate and object ID sequences) reaches 2-4% of N-Triples size. That is 3-4x smaller than Plain HDT and 20-45% better than the best universal compressor (ppmdi). This is component-wise compression rather than true joint compression of dictionary and structure, so joint compression remains unexploited headroom. HDT-Compress is also an exchange format that must be decompressed before queries, so a queryable in-flash variant for MCUs is still an open optimization.

Fernandez et al. 2013, Sec. 5.1. The split vote was about the word 'joint': the paper compresses each structure independently. The results are on web-scale datasets with millions of triples, and on tiny domain KBs PPM has less context to learn from, so the 20-45% gain may shrink.

Quellen: <https://aic.ai.wu.ac.at/~polleres/publications/fern-etal-2013-HDT-JWS.pdf>

### 7. KG embeddings for inferring missing facts can be made MCU-sized, but only if quantization is trained in

**Sicherheit:** medium · **Votum:** 2-1 / 3-0

KG embeddings for inferring missing facts can be made MCU-sized, but only if quantization is trained in. Binarized CP trained with a straight-through estimator reaches MRR 45.0 on WN18RR with 400 bits per entity (D=200), versus 44.0 for float CP with 12,800 bits. Binarizing after training (VQ-CP) collapses to 36.0 (WN18RR) and 8.7 (FB15k-237), against 45.0 and 27.8 for B-CP at the same bit budget. Simply shrinking float dimensions also hurts: CP at D=15 gets 40.0 and 22.0. Gains are dataset-dependent: on FB15k-237 at D=200, B-CP is still behind (27.8 vs 29.0) and only reaches parity at D=300-400.

Kishimoto et al. 2019, Table 4. The float CP baseline is under-tuned: CP-N3 reaches about 0.47-0.48 MRR on WN18RR. VQ-CP is a naive post-training baseline. These are single-paper results on the CP model only. One vote was split over the general 'matches or beats float' wording.

Quellen: <https://arxiv.org/pdf/1902.02970>

### 8. Discrete codebook codes (KD codes) are a stronger compression route for KG embeddings

**Sicherheit:** high · **Votum:** 3-0

Discrete codebook codes (KD codes) are a stronger compression route for KG embeddings. Each entity becomes D codes over K values (default K=32, D=10, i.e. 50 bits or about 6-7 bytes per entity) plus a small decoder, all trained end-to-end. This gives 50-1000x compression with little accuracy loss. RotatE on FB15k: MRR 0.798 vs 0.797 continuous at 495x. TransE even improves (0.477 vs 0.463) at about 43x. WN18 and WN18RR reach about 953x with MRR drops of 0.003 and 0.024. A 2025 follow-up computes about 15.9x for FB15k-237 with 16-bit indices (64 B per entity vs 1 KB in float32). It notes that combining triple-based partitioning with VQ is untested and that results have not been checked at million-entity scale. Storing the codes with only the bits they need (7 bits for K=128) would give about 36x, so even this published example is not at its optimum.

Sachan, ACL 2020, Tables 3, 4 and 6. Sobhi et al., CEUR KG-NeSy 2025, Eq. 4 and conclusion. Caveats: FB15k and WN18 suffer test leakage through inverse relations, and harder benchmarks show larger losses (TuckER on FB15k-237 drops from 0.358 to 0.331). The Bi-LSTM decoder needs O(D) matrix-vector products per lookup, which is costly without an FPU, so a codebook-lookup decoder or integer scoring fits an ESP8266 better. The 15.9x figure is a worked storage calculation, not a measured accuracy result.

Quellen: <https://preview.aclanthology.org/fix_video/2020.acl-main.238.pdf>, <https://ceur-ws.org/Vol-4313/kgnesy-paper3.pdf>

### 9. In binary HDC/VSA, a flat bundled (superposition) vector is a weak fact store, and associative memory is the better architecture

**Sicherheit:** medium · **Votum:** 3-0 / 2-1

In binary HDC/VSA, a flat bundled (superposition) vector is a weak fact store, and associative memory is the better architecture. Binarized MAP-B bundles need m = O(n log(d/δ)) dimensions for membership tests, and their reliability falls exponentially with nesting depth when the result is re-thresholded at every level. Deep compositional fact encodings therefore degrade, unless integer accumulators are kept and thresholding happens only once, or bundles are arranged as balanced trees. With 1,000 or more key-value pairs, a Sparse Distributed Memory needs less memory and fewer operations for the same reliability. On a 1,000-transition benchmark, superposition used 15-35x the storage of the smallest SDM (when the item memory had to be stored) and 37-51x (error rate 10^-1) to 100-135x (error rate 10^-9) the recall operations. SDM recall cost stays roughly constant as the error target tightens.

Clarkson, Ubaru and Yang (Thm. 16, Lemma 17). Teeters, Kleyko, Kanerva and Olshausen, Frontiers in Neuroscience 2023, Sec. 3.3.1 and Discussion. Important exception for MCUs: if the item memory can be regenerated from a seed (no stored bits), binarized superposition becomes the smallest option. The SDM address and counter matrix is large, which matters at 35 KB RAM. The operation counts come from an analytical model. A related claim that HDC per-fact capacity is no better than Bloom filters was refuted 0-3. A promising combination is HDC/SDM as a fuzzy cue-to-entity associative index in front of an exact symbolic store.

Quellen: <https://arxiv.org/abs/2301.10352>, <https://redwood.berkeley.edu/wp-content/uploads/2025/06/teeters2023separating.pdf>

### 10. Naive HDC implementations on MCUs leave large efficiency headroom

**Sicherheit:** medium · **Votum:** 3-0

Naive HDC implementations on MCUs leave large efficiency headroom. On a Cortex-M33, algebraic encoder rewrites in a 10,000-bit Binary Spatter Code pipeline cut codebook memory by 52%, binding operations by 50% and bundling operations by about 98%. The result ran at 0.08-0.27 s per inference with 52-63 KB of flash and 22.25 KB of peak RAM. The domain is image encoding, so it transfers only indirectly to text and fact memory.

HyperCam (arXiv 2501.10547, Jan 2025), STM32U585. Rewrites 1-2 are exact. Rewrites 3-4 (value factoring and sparse bundling via Count Sketch or Bloom filter) are lossy: MNIST 94.60 -> 93.60, Face ID 78.63 -> 72.79, and only 61.40% for the Bloom variant. Single source.

Quellen: <https://arxiv.org/html/2501.10547v1>

## Vorbehalte

- **Coverage is uneven.** No claims survived verification for Tsetlin machines, tiny intent/slot NLU sizes and accuracy on MCUs, German template or grammar NLG, case-based reasoning, SKOS/frame compilation, or the methodology for turning a topic into a schema (competency questions, NeOn/METHONTOLOGY, LLM-based KG extraction). Recommendations in those areas rest on earlier research or general knowledge, not on this verified set.
- **No result was measured on an ESP8266.** All MCU results come from larger boards (Arduino Due 96 KB, ESP32 520 KB, STM32U5 736 KB, XScale 64 MB). The figures for a 35 KB arena are linear extrapolations.
- **The benchmarks are not domain KGs.** Compression results come from web-scale Linked Data (millions of triples, 2013-2015). KGE results come from FB15k/WN18-family benchmarks, some with known test leakage. Small hand-built domain KGs (a few hundred to a few thousand facts, many shared literals) may behave differently, so the gains have to be re-measured per domain.
- **Several baselines are weak or dated.** The CP baseline is under-tuned, HDT is from 2013, and k2-triples and later succinct encodings may beat HDT++. Some "headroom" framings are the claimants' interpretation rather than the authors' statements.
- **One refuted claim.** The claim that k2-triples reach about 14-15 bits per triple was refuted, so no verified sub-byte-per-fact structure figure is available.
- **Split votes.** Findings with 2-1 votes (RETE "far from optimum", "joint" compression, B-CP parity, SDM vs superposition) should be treated as directionally right but overstated in their original wording.

## Offene Fragen

- What is the real per-fact flash cost (dictionary plus structure, bits per triple) of a compiled, queryable store for a typical small domain KG (500-5,000 facts) when predicate-local IDs, front-coded or PPM-like string dictionaries and rank/select structures are combined, and how close does it get to the entropy bound?
- Do inferred missing facts actually help a tiny assistant? Is a quantized or KD-coded KG embedding (integer-only scoring, no Bi-LSTM decoder) worth its flash on small domain KGs, or does offline LLM-assisted completion plus materialization dominate it?
- How do Tsetlin machines, HDC classifiers and tiny int8 networks compare on German intent/template classification and slot filling under a budget of about 35 KB RAM and a few hundred KB flash, including bytes, latency and accuracy across several domains?
- Can a seed-regenerated item memory plus SDM-style associative memory serve as a robust fuzzy entity and alias index (typos, inflection) in front of the exact symbolic store, and at what RAM cost on an ESP8266?

## Widerlegte Aussagen

- (0-3) k2-triples (one k2-tree per predicate, i.e. vertical partitioning, with ID-encoded triples) is the most compact Triples representation tested. On geonames (9.4M triples, 20 predicates) it needs 0.017 GB, about 14-15 bits per triple, against 0.072 GB for MonetDB, 0.344 GB for RDF-3X and 0.569 GB for BitMat. This suggests that the structure part of a symbolic store can drop well below a byte per fact when there are few predicates. — <https://arxiv.org/pdf/1105.4004>
- (0-3) The paper measures only the ID-encoded triples and leaves out the dictionary of URIs and literals. It calls compact dictionaries an open problem, which marks headroom in jointly compressing the dictionary and the structure, since strings dominate store size. — <https://arxiv.org/pdf/1105.4004>
- (0-3) For set membership, the needed MAP-I bundle dimension m grows linearly with the number of stored items n and logarithmically with the universe size d and the inverse failure rate: m = O(n log(d/δ)). An HDC associative fact memory therefore needs about n·log(d/δ) dimensions for n facts. That is no better than classical sketches or Bloom filters, so per-fact capacity is bounded and does not beat symbolic storage. — <https://arxiv.org/abs/2301.10352>

## Statistik

```json
{"angles": 5, "sourcesFetched": 22, "claimsExtracted": 109, "claimsVerified": 25, "confirmed": 22, "killed": 3, "unverified": 0, "afterSynthesis": 10, "urlDupes": 0, "budgetDropped": 8, "agentCalls": 104}
```
