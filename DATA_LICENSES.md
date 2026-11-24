# Data Licenses

Every training fact carries a `source` value. Only the sources listed here may be used
(constitution, Principle IV). Data with unclear licensing MUST NOT be used.

| Source prefix | Description | License |
|---------------|-------------|---------|
| `own` | Facts and templates written for this project | MIT (same as the code) |
| `computed` | Values computed by deterministic rules in `training/src/ultratiny/factgen.py` / `periodic.py` from other listed sources (atomic structure, ions, ionic formulas, molar masses, bond types) | MIT (same as the code) |
| `wikidata` | Snapshot of Wikidata statements (`wikidata:<QID>`) | CC0 1.0 |
| `llm` | Questions/paraphrases/off-topic inputs generated with a locally run open-weight LLM (`llm:<model>` per row, currently only `llm:gemma4:e4b`; also allowed: `llm:gpt-oss:*`, `llm:qwen3*`); answers are never LLM-generated, they stay curated | Apache 2.0 models only (Gemma 4, gpt-oss, Qwen3); model output carries no further license terms |
| `public-domain` | Evaluation text only (`bench/suites/*/text/s1.txt`, general half): Franz Kafka, *Die Verwandlung* (1915; author died 1924), opening 10,084 characters, Project Gutenberg eBook #22367 (fetched from the gutenberg.pglaf.org mirror, 2026-11-23). Never used for training | Public domain |

LLM output is only used for *questions* (training-only augmentation in `training/data/augment/`),
filtered by a judge prompt, the alphabet check and the held-out leak/conflict checks in `datagen`.

Exception (specs/006-hybrid-chemielehrer, FR-008): `training/data/facts/chemie_kurz.tsv` holds
short (<= 60 characters) versions of the curated `own` explanations, *proposed* by a local LLM
(`tools/shorten_llm.py`, source `llm:<model>`). Each row must pass the automatic check (no new
numbers or formulas, key term present, table facts excluded) and is reviewed by a person
(`reviewed = yes`) before it is used for training. Review of 2026-11-24: 338 rows accepted, 115 flagged rows kept out (`specs/006-hybrid-chemielehrer/kurz-review.tsv`). No fact value comes from an LLM; facts are
answered from the fact table (`own`, `wikidata`, `computed`).

Benchmark data (specs/007-benchmark-kpi-bericht): everything under `bench/` is evaluation-only and
never used for training (the data generators drop benchmark questions). Its questions and topic
texts are proposed by one of the local models listed under `llm` (`llm:<model>` per row in
`bench/suites/*/proposals/`) and spot-checked by the user; expected answers come from the project's
own fact data, never from an LLM. Public-domain texts used as S1 test text are listed below with
work, author and source.

Models trained from this data (`models/*.utny`) are released under MIT, like the code.

## Notes

- The Gemma 4 family (incl. `gemma4:e4b`, run locally via Ollama) is released by Google under
  Apache 2.0. Earlier Gemma generations (1–3) use the Gemma Terms of Use and MUST NOT be used.
- Chemistry facts (`chemie_*.tsv`, `source = own`) are written for this project. The
  Rahmenlehrplan Chemie Berlin-Brandenburg only serves as a topic list (Themenfelder 3.1–3.12);
  no curriculum text is copied.
- Tiny-2.1 inspired the approach; no code or data from it is used.
