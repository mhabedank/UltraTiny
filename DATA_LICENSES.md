# Data Licenses

Every training fact carries a `source` value. Only the sources listed here may be used
(constitution, Principle IV). Data with unclear licensing MUST NOT be used.

| Source prefix | Description | License |
|---------------|-------------|---------|
| `own` | Facts and templates written for this project | MIT (same as the code) |
| `wikidata` | Snapshot of Wikidata statements (`wikidata:<QID>`) | CC0 1.0 |
| `llm` | Questions/paraphrases/off-topic inputs generated with a locally run open-weight LLM (`llm:<model>` per row, currently only `llm:gemma4:e4b`; also allowed: `llm:gpt-oss:*`, `llm:qwen3*`); answers are never LLM-generated, they stay curated | Apache 2.0 models only (Gemma 4, gpt-oss, Qwen3); model output carries no further license terms |

LLM output is only used for *questions* (training-only augmentation in `training/data/augment/`),
filtered by a judge prompt, the alphabet check and the held-out leak/conflict checks in `datagen`.

Models trained from this data (`models/*.utny`) are released under MIT, like the code.

## Notes

- The Gemma 4 family (incl. `gemma4:e4b`, run locally via Ollama) is released by Google under
  Apache 2.0. Earlier Gemma generations (1–3) use the Gemma Terms of Use and MUST NOT be used.
- Chemistry facts (`chemie_*.tsv`, `source = own`) are written for this project. The
  Rahmenlehrplan Chemie Berlin-Brandenburg only serves as a topic list (Themenfelder 3.1–3.12);
  no curriculum text is copied.
- Tiny-2.1 inspired the approach; no code or data from it is used.
