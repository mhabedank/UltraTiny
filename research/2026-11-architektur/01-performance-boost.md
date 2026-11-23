# Recherche 1: Größer, schneller, mehr Kontext, mehr Wissen

Deep-Research-Lauf vom November 2026 (Workflow `deep-research`: 5 Suchwinkel, Quellen abgerufen, jede Aussage von 3 Agenten gegengeprüft, 2 von 3 Widersprüchen streichen sie). Rohdaten: [`raw/01-performance-boost.json`](raw/01-performance-boost.json).

## Fragestellung

Context: UltraTiny is a German character-level transformer (4 layers x 128 dim, multi-query attention, ~0.6M params, int8 weights with per-row scales read directly from flash) running fully offline on an ESP8266 NodeMCU (~80 KB RAM, ~35 KB arena, no FPU, 160 MHz, 4 MB flash, weights read in 32-bit words). Current: context 104 chars, int8 KV cache, ~5.1 chars/s, first char after 158 ms, 588 KB model. A hybrid with a fact lookup table (chemistry teacher) is next. Question: Which concepts and technologies could significantly boost this model on such microcontrollers: (1) longer context under ~35 KB RAM (KV cache compression/quantization, sliding window, linear attention, RNN/state-space models like RWKV/Mamba, recurrent memory); (2) faster inference on no-FPU MCUs (integer-only kernels, sub-byte/ternary/binary weights like BitNet b1.58, lookup-table matmul, speculative decoding, early exit, subword vs char tokenization); (3) bigger model within 4 MB flash (2/3/4-bit and ternary quantization, weight sharing, low-rank factorization, mixture-of-experts with flash-streamed experts, codebook/vector quantization); (4) more knowledge (distillation from large LLMs, retrieval from flash-stored indexes/fact tables, knowledge-dense synthetic data, TinyStories-style curricula). Also: a concrete methodology for systematically discovering and evaluating completely new approaches (literature scouting, quick PC-side bit-exact prototyping, ablation, budgets for RAM/flash/latency) that can then be elaborated and built. Prefer TinyML / MCU LLM work (e.g. llama2.c on MCUs, TinyML papers, MCUNet, Edge LLM) with concrete numbers.

## Zusammenfassung

For UltraTiny, the evidence points to four main levers. (1) For longer context, switch to a recurrent or state-space design (RWKV- or Mamba-style, or a gated diagonal SSM). These carry a fixed-size state instead of a KV cache, so RAM stops growing with context. Byte-level models about this size already exist, such as rwkv.cpp's 660K-param test model. MambaLite-Micro shows a pure-C Mamba engine running on MCUs. At ~60K params, a gated SSM beat transformer baselines by more than 20% on byte-level TinyStories. If the transformer stays, 2-bit KV cache with per-channel keys and per-token values (KIVI) is the strongest fallback. (2) For a bigger model in 4 MB flash, ternary or 2-bit weights at 1.67–2 bits per weight fit about 4–5x more parameters in the same flash. A Cortex-M7 at the same 160 MHz already runs an 8.3M-param TinyStories model from 3.62 MB of flash at about 1 tok/s. On MCUs, measured speedups from these formats are modest: 1.71x on ESP32-S3 against FP32. Note that a bigger model usually means slower generation, because every weight is read once per character. (3) For speed, lookup-table matmul (T-MAC) and ternary kernels (bitnet.cpp) remove multiplications and their cost scales with bit-width. But every reported speedup comes from SIMD CPUs, and the reported ~1.7x MCU gain was against FP32, not UltraTiny's int8, so gains on the no-FPU ESP8266 must be measured, not assumed. (4) For more knowledge, models store at most about 2 bits of facts per parameter, so UltraTiny's ceiling is roughly 150 KB of facts. A fact table in flash plus training on narrow, distilled synthetic data (TinyStories-style) gives much more knowledge per byte than a bigger network. For finding new approaches, the evidence supports a budget-first loop: a co-designed engine, constraint-driven search-space ranking (TinyNAS), sweeping depth/width shape before comparing architectures, multi-seed tests against a pre-set noise threshold, and bit-exact PC prototypes measured against RAM, flash and latency budgets.

## Befunde

### 1. For longer context in fixed RAM, recurrent and state-space models are the most promising route

**Sicherheit:** high · **Votum:** 3-0 (all three underlying claims)

For longer context in fixed RAM, recurrent and state-space models are the most promising route. They carry a fixed-size state between steps instead of a KV cache that grows with context, so context length stops costing RAM. Working tiny examples and MCU deployments exist.

- rwkv.cpp ships a 660K-param RWKV model with a 256-symbol byte vocabulary, about UltraTiny's size. It evaluates one char at a time with a fixed-size state buffer (`rwkv_eval(model, prompt[i], state, state, logits)`), and has Q4/Q5/Q8 variants.
- MambaLite-Micro (2025) calls itself the first Mamba deployment on an MCU: a runtime-free C engine fed with weights exported from PyTorch. It ran on ESP32-S3 and STM32H7, cut peak memory by 83% through operator fusion and memory layout, matched PyTorch to about 1.7e-5 numerical error, and matched its classification results 100%.
- At ~60K params on byte-level TinyStories with a 130M-byte training budget, a gated diagonal-SSM block (d=44, 3 layers) beat a routed conv/SSM/attention hybrid by 9.1%. That hybrid beat transformer shapes by 22.2–24.0%, and its router put most of its weight on the recurrent path.
- For UltraTiny, a small SSM or RWKV state (e.g. a few hundred bytes to a few KB per layer at d=128) could give effectively unlimited context within the ~35 KB arena.

Quellen: <https://redirect.github.com/RWKV/rwkv.cpp/blob/a3178b20ea0a1600f4d5d9dc06f67800d8bbb62a/tests/test_tiny_rwkv.c>, <https://arxiv.org/abs/2509.05488v1>, <https://arxiv.org/pdf/2609.29397>

### 2. If UltraTiny keeps attention, quantize the KV cache from int8 to 2 bits: keys per channel (because of outlier channels), values per token, with a small full-precision window for the most recent tokens

**Sicherheit:** medium · **Votum:** 3-0

If UltraTiny keeps attention, quantize the KV cache from int8 to 2 bits: keys per channel (because of outlier channels), values per token, with a small full-precision window for the most recent tokens. This could roughly triple to quadruple the context in the same cache RAM.

- KIVI (ICML 2024) found that key caches have fixed outlier channels, so keys should be quantized per channel and values per token.
- KIVI-2 stays near fp16 quality on Llama and Mistral, with up to a 2-point accuracy drop (Llama-2-7B GSM8K: 13.50 at fp16, 12.74 at 2 bits). Falcon-7B needs 4 bits.
- The te-comp MCU deployment uses a stateful int4 KV cache.
- Rated medium because every result comes from models of 7B parameters or more, or from an 8.3M-param model. Nobody has checked whether a 128-dim char-level model has the same key outlier channels.
- KIVI's residual window (32–128 tokens) and per-group scales could eat most of the savings at a 104-char context. The window should be small, or replaced by grouped quantization at fill time.

Quellen: <https://arxiv.org/html/2402.02750v2>, <https://arxiv.org/pdf/2611.03710>

### 3. Sub-byte weights are the main way to fit a much bigger model in 4 MB flash

**Sicherheit:** high · **Votum:** 3-0 (all)

Sub-byte weights are the main way to fit a much bigger model in 4 MB flash. Ternary packing reaches 1.67 bits per weight (TL2) or 2 bits per weight (4 weights per byte), versus 8 for int8. Accuracy loss is moderate when the model is trained or distilled with quantization in the loop. Low-rank factorization and sparsity add more savings on top.

- bitnet.cpp's TL2 packs 3 ternary weights into a 1-bit sign plus a 4-bit index (27 combinations, 14 after mirror symmetry), which gives 1.67 bits per weight. I2_S uses 2 bits per weight.
- FTerViT packs ternary weights 4 per byte. Distilled from an FP32 teacher, a DeiT-III-S shrank 15.2x to 5.81 MB, with top-1 accuracy falling from 83.08% to 79.64%.
- At 60K params, BitNet-style ternary weights cost +5.3% loss for the best transformer shape, +19.5% for the routed hybrid and +28.1% for the gated SSM (at 130M bytes). This is confounded: the transformers kept 11–22% of their parameters in full precision.
- RWKV-lite cut memory 3.4–5x with low-rank SVD, sparsity predictors, an embedding cache and hierarchical heads, at a cost of 0.9–1.5 points on lambada. INT8 on top gave about 10x in total, but UltraTiny is already int8.
- Reference point: an 8.3M-param GPT-Neo runs on a 160 MHz Cortex-M7 from 3.62 MB of flash with Q4_0 weights.
- Implication for UltraTiny: at about 1.67–2 bits per weight, roughly 3 MB of flash could hold on the order of 10M+ params. Speed, not flash, then becomes the binding limit.

Quellen: <https://arxiv.org/html/2502.11880v1>, <https://arxiv.org/html/2605.21171>, <https://arxiv.org/pdf/2609.29397>, <https://arxiv.org/html/2412.10856v4>, <https://arxiv.org/pdf/2611.03710>

### 4. Lookup-table and ternary kernels remove multiplications, and their cost scales linearly with weight bit-width

**Sicherheit:** medium · **Votum:** 3-0 (all)

Lookup-table and ternary kernels remove multiplications, and their cost scales linearly with weight bit-width. That makes them the right direction for a no-FPU MCU. But every large reported speedup comes from SIMD CPUs, and the only MCU measurement shows a modest gain.

- T-MAC runs low-bit matmul as bit-wise table lookups without dequantizing, from 1 to 4 bits, with cost linear in bit-width. Its kernels are up to 6.6x faster than llama.cpp (3.6x on average), with up to 4x end-to-end throughput.
- bitnet.cpp's I2_S kernel is up to 6.25x faster than FP16, but only up to 2.32x against low-bit baselines.
- Those numbers rely on NEON TBL, AVX2 PSHUFB and FPUs, which the ESP8266 lacks.
- On an ESP32-S3, a packed ternary matmul ran only 1.71x faster than FP32 (804 vs 1376 ms, kernel level, with unoptimized bit-unpacking).
- On the ESP8266, sub-byte weights cut flash words read per weight 4–5x. Whether unpacking or table-lookup overhead uses up that gain against today's int8 path must be benchmarked.
- A practical variant: 4-entry or 16-entry lookup tables of activation partial sums built per input vector, indexed by packed 2-bit or 4-bit weight groups read as 32-bit words.

Quellen: <https://arxiv.org/html/2407.00088v2>, <https://arxiv.org/html/2502.11880v1>, <https://arxiv.org/html/2605.21171>

### 5. Memory bandwidth, not compute, often limits MCU LLM speed, so fewer bytes per weight is the first speed lever

**Sicherheit:** low · **Votum:** 3-0 (scoped claim); generalized version refuted 1-2

Memory bandwidth, not compute, often limits MCU LLM speed, so fewer bytes per weight is the first speed lever. But this was shown on an ESP32-S3 with PSRAM. On the ESP8266, with no SIMD and flash reads through a cache, the bottleneck has to be profiled.

- The esp32-llm README says the second core is unused because the bottleneck is memory bandwidth, not compute.
- The INT8 engine reaches about 12 tok/s against a measured ceiling of about 13.1 tok/s.
- The related claim that this generalizes to all MCU inference was refuted 1-2, so it holds only for that project.
- Single hobby-repo source, so rated low.
- For UltraTiny: profile cycles split between flash/cache wait and multiply-accumulate before choosing between kernel work and weight shrinking.

Quellen: <https://github.com/doryiii/esp32-llm>

### 6. Parameter count limits how much factual knowledge UltraTiny can hold: about 2 bits per parameter at most, kept at int8 and reduced at int4

**Sicherheit:** high · **Votum:** 3-0 (two merged claims)

Parameter count limits how much factual knowledge UltraTiny can hold: about 2 bits per parameter at most, kept at int8 and reduced at int4. That is about 150 KB of facts for 0.6M params. More knowledge should come from retrieval over flash-stored fact tables, not from a bigger network alone.

- Allen-Zhu and Li (ICLR 2025): language models can and only can store 2 bits of knowledge per parameter, even when quantized to int8.
- int4 drops capacity to about 0.7 bits per parameter. At about 100 exposures per fact, capacity falls to about 1 bit per parameter.
- A tiny char-level model also spends capacity on spelling and grammar, so the real fact budget is well below 150 KB.
- 4 MB of flash can hold several MB of compressed fact tables, which is about 20x more than the network could memorize.
- This supports the planned chemistry-teacher hybrid: a keyword or hash index in flash, with retrieved facts fed into the context or copied directly into the output.
- Caution: ternary weights may also lower knowledge capacity (int4 did), so the bigger-but-lower-bit trade-off needs its own measurement.

Quellen: <https://arxiv.org/abs/2404.05405>

### 7. Narrow, vocabulary-restricted synthetic corpora generated by large LLMs let very small models produce fluent, grammatical text, even with a single layer

**Sicherheit:** high · **Votum:** 3-0 (two merged claims)

Narrow, vocabulary-restricted synthetic corpora generated by large LLMs let very small models produce fluent, grammatical text, even with a single layer. A distilled German domain corpus (e.g. chemistry teaching dialogues) is a high-leverage way to make UltraTiny more useful.

- TinyStories, generated by GPT-3.5 and GPT-4 with about 1.5K child-level words, trains models under 10M params, including one-block models, to write fluent multi-paragraph stories with almost perfect grammar.
- llama2.c reproduces this at 260K–15M params.
- FTerViT shows that forward-KL distillation from a full-precision teacher recovers most accuracy for ternary weights. This suggests combining synthetic data with teacher distillation when moving to sub-byte weights.
- Limits: those models used about 50K subword tokens, were evaluated in English, and were scored by GPT-4. One-layer models are weak on consistency, and facts stay weak, which is why the fact table is still needed.

Quellen: <https://arxiv.org/abs/2305.07759>, <https://arxiv.org/html/2605.21171>

### 8. Method for finding new approaches: work budget-first

**Sicherheit:** medium · **Votum:** 3-0 (merged)

Method for finding new approaches: work budget-first. Co-design the engine with the model. Rank candidate design spaces by how much compute they can use within the RAM and flash limits. Sweep depth/width shape before comparing architectures. Use multiple seeds with a noise threshold set in advance, and re-check at more than one training budget.

- MCUNet's TinyEngine, co-designed with the model, used 3.4x less peak memory and ran 1.7–3.3x faster than TF-Lite Micro and CMSIS-NN, leaving room for a bigger model.
- TinyNAS first ranks 108 width × resolution search spaces by the FLOPs distribution of 1,000 sampled networks that fit memory, then searches for the architecture.
- At 60K params, depth/width shape alone moved loss by 22.6% (2.835–3.477 nats/byte), more than any architecture effect measured. The best shape also reversed between training budgets, so comparing architectures at a single fixed shape can give the wrong verdict.
- te-comp shows another route: compile the model into a self-contained C engine (MLIR to C).
- Proposed loop for UltraTiny:
  1. Scout the literature into a candidate list.
  2. Write a PC-side bit-exact C or Python simulator of the ESP8266 integer kernels.
  3. Run a budget gate: RAM ≤35 KB arena, flash ≤ ~3.4 MB, ms per char.
  4. Sweep shapes and run ablations with 3 seeds at 2 training budgets.
  5. Profile on device.
  6. Promote winners to the build.
- Rated medium because TinyNAS was validated on CNNs, and the shape study is a single-author preprint.

Quellen: <https://arxiv.org/pdf/2007.10319v2>, <https://arxiv.org/pdf/2609.29397>, <https://arxiv.org/pdf/2611.03710>

## Vorbehalte

- No source tested a language model on an ESP8266 or any comparable no-FPU MCU with about 80 KB of RAM. The nearest are the ESP32-S3, STM32H7 and Cortex-M7, all with far more RAM, and most of them with an FPU or DSP/SIMD. Every speedup figure (T-MAC 6.6x, bitnet.cpp 6.25x, TinyEngine 1.7–3.3x) comes from SIMD CPUs or Cortex-M with CMSIS, and against FP16, FP32 or interpreter baselines rather than an int8 custom engine. These numbers should not be expected to carry over.
- KIVI and the knowledge-capacity results come from models of millions to billions of parameters. The TinyStories and FTerViT results use subword English or vision models. Extrapolating any of them to a 0.6M-param German char-level model is unverified.
- Several key sources are recent preprints by one author and have not been peer-reviewed: the 60K-param ternary/SSM study (Sept 2026) and te-comp (Oct 2026). FTerViT (2026) has not been replicated.
- MambaLite-Micro's "first" is the authors' own claim. Its tasks were classification (keyword spotting and activity recognition), not text generation.
- The memory-bandwidth argument comes from a hobby repo, and its generalized form was refuted.
- Ternary weights help some architectures less than others. At 60K params, SSMs lost more than transformers under ternary, and that comparison was confounded. Choosing an SSM and ternary weights together may cancel part of each gain.
- A bigger model in flash makes generation proportionally slower on a 160 MHz single core. For example, 8.3M params gives about 1 tok/s on an M7. Bigger and faster pull against each other.
- The research did not cover early exit, speculative decoding, char vs subword tokenization, mixture-of-experts with experts streamed from flash, or vector quantization, so none of these has verified evidence here.
- The field moves fast: several sources are from late 2026.

## Offene Fragen

- On the ESP8266 (no SIMD, flash read through cache in 32-bit words), do 2-bit, ternary or lookup-table kernels actually beat the current int8 multiply-accumulate in ms per char, or does unpacking overhead use up the bandwidth savings? This needs a micro-benchmark on the device.
- Does a 0.6–3M-param German char-level RWKV or gated SSM match or beat the current 4×128 MQA transformer at equal flash and latency, and how large is its state in the ~35 KB arena? Can it be trained stably with int8 or ternary weights?
- Do UltraTiny's key activations have the outlier channels that justify KIVI's per-channel key quantization, and what is the real context gain once scale overhead and any full-precision recent-token window are counted against a 104-char cache?
- What is the best way to plug the flash fact table into a char-level model? Options include retrieved text placed into the context, a copy or pointer mechanism, or direct template output. How much does a German chemistry synthetic corpus distilled from a large LLM improve factual accuracy over the current training data?

## Widerlegte Aussagen

- (1-2) An INT8 llama2.c port (llm8.c) runs a 3.3M-parameter model on ESP32-S3 at about 12 tokens/s, close to the memory-bandwidth limit of 13.1 tok/s. This suggests weight-memory bandwidth, not compute, sets the speed limit for MCU LLM inference. — <https://github.com/doryiii/esp32-llm>

## Statistik

```json
{"angles": 5, "sourcesFetched": 20, "claimsExtracted": 87, "claimsVerified": 25, "confirmed": 24, "killed": 1, "unverified": 0, "afterSynthesis": 8, "urlDupes": 0, "budgetDropped": 10, "agentCalls": 102}
```
