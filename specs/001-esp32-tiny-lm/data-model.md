# Data Model: Tiny Language Model Demo on a Classic ESP32

## Fact

A single piece of knowledge the model must recall.

| Field | Type | Rules |
|-------|------|-------|
| `id` | string | unique, stable (`<topic>/<n>`) |
| `topic` | string | one of the configured topics |
| `relation` | string | key into the template catalog (e.g. `hauptstadt_von`) |
| `subject` | string | German, only alphabet characters |
| `object` | string | German, only alphabet characters |
| `source` | string | `wikidata:<QID>` or `own` — must map to an entry in `DATA_LICENSES.md` |

Validation: every character of `subject`/`object` must be in the Alphabet; answer length (after
template expansion) ≤ 200 characters (FR-006).

## QuestionTemplate / AnswerTemplate

| Field | Type | Rules |
|-------|------|-------|
| `relation` | string | matches `Fact.relation` |
| `text` | string | contains `{subject}` and/or `{object}` placeholders |
| `split` | enum `train` \| `heldout` | held-out templates never appear in training (SC-004) |

Each relation has ≥ 8 question templates (≥ 2 held out) and ≥ 1 answer template.
A question template may carry its own `answer` template (used for reverse questions such as
"Von welchem Land ist {object} die Hauptstadt?"); otherwise the relation's answers are used.

Exception — free relations (`free = true`, e.g. `frei` for questions about the device itself):
`Fact.subject` holds ≥ 2 question phrasings separated by `|` (the last one is held out) and
`Fact.object` is the literal answer. The ≥ 8-template rule does not apply to them.

## TrainingExample

`<bos> question <sep> answer <eos>`, encoded as Alphabet token IDs; total length ≤ `ctx` (256).
Loss is computed on `answer <eos>` only.

## Alphabet

Ordered list of symbols; index = token ID. IDs 0–4 are reserved:
`0 <pad>, 1 <bos>, 2 <sep>, 3 <eos>, 4 <unk>`. Remaining entries are Unicode code points
(≤ 91 entries, vocab ≤ 96). Stored inside the Model File so device and reference always agree.

## ModelConfig

| Field | v1 value | Notes |
|-------|----------|-------|
| `vocab_size` | ≤ 96 | from Alphabet |
| `d_model` | 128 | |
| `n_layers` | 4 | |
| `n_heads` | 4 | query heads |
| `n_kv_heads` | 1 | MQA |
| `head_dim` | 32 | `d_model / n_heads` |
| `d_ff` | 384 | |
| `ctx_len` | 256 | |
| `norm_eps` | 1e-5 | RMSNorm |

## ModelFile (UTNY v1)

Self-describing binary; full layout in [contracts/model-format.md](contracts/model-format.md).
Relationships: produced by `export` from a Checkpoint; consumed by the Runtime (device + host) and
the Reference. Validation at load: magic, format version, header CRC, payload CRC, dimension
sanity, arena size ≤ budget.

## RunMetadata

Saved next to each checkpoint and embedded (as a short string) in the Model File:
config, seed, data hash (SHA-256 of generated dataset), git commit, device (`mps`/`cpu`),
training wall time, eval results.

## Session (device runtime state)

| Field | Description |
|-------|-------------|
| `pos` | next position in the KV cache (0 … `ctx_len`) |
| `kv` | int8 K/V cache + scales (static arena) |
| `input_len` | characters typed in the current line |
| `mode` | `greedy` (default) or `sample` with `seed`, `temperature` |
| `state` | see state machine |

### State machine

```text
BOOT ──model invalid──▶ HALT_ERROR   (prints error, stays responsive to /help, no reboot loop)
  │
  └─model ok──▶ READY ──char──▶ TYPING ──Enter──▶ GENERATING ──<eos> / max len──▶ READY
                  ▲  ▲             │  │                │
                  │  └─Enter(empty)┘  └─Backspace: pos-1 (stay TYPING)
                  │                                    │
                  └──────────────Ctrl-C (abort)────────┘
```

- On READY: `pos = 0`, feed `<bos>` (pos = 1).
- In TYPING: each accepted char is fed immediately (incremental prefill); if `pos` would exceed
  `ctx_len − 1 − min_answer_reserve` (reserve 32), further input is rejected with a message.
- In GENERATING: input other than Ctrl-C is discarded; generation stops at `<eos>`,
  `max_answer_len` (default 200), or a full context.

## EvalSet

| Field | Description |
|-------|-------------|
| `kind` | `demo` (SC-003) or `heldout` (SC-004) or `parity` (SC-006) |
| `prompt` | question text |
| `expected` | expected answer (demo/heldout) |
| `tokens`, `logits` | per-step golden outputs (parity only) |

## BudgetReport

| Field | Budget | Source |
|-------|--------|--------|
| `model_bytes` | ≤ 2 MB (−10% headroom) | model header |
| `arena_bytes` | ≤ 128 KB (−10% headroom) | `utiny_arena_size()` |
| `app_bytes` | ≤ factory partition (−10%) | `idf.py size` |
| `static_dram_bytes` | reported | `idf.py size` |
| `chars_per_s`, `first_char_ms` | ≥ 10 / ≤ 1000 | on-device `/info` (manual, pre-release) |
