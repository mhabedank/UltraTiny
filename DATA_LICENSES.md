# Data Licenses

Every training fact carries a `source` value. Only the sources listed here may be used
(constitution, Principle IV). Data with unclear licensing MUST NOT be used.

| Source prefix | Description | License |
|---------------|-------------|---------|
| `own` | Facts and templates written for this project | MIT (same as the code) |
| `wikidata` | Snapshot of Wikidata statements (`wikidata:<QID>`) | CC0 1.0 |
| `llm` | Questions/paraphrases/off-topic inputs generated with a locally run open-weight LLM (`llm:<model>` per row, e.g. `llm:gpt-oss:120b`, `llm:qwen3.6:35b`); answers are never LLM-generated, they stay curated | Apache 2.0 models only (gpt-oss, Qwen3) |

LLM output is only used for *questions* (training-only augmentation in `training/data/augment/`),
filtered by a judge prompt, the alphabet check and the held-out leak/conflict checks in `datagen`.
