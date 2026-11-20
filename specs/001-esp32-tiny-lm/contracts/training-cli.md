# Contract: Training & Export CLI (`training/`)

Run with `uv run ut <command>` from `training/`. Every command is deterministic given `--seed`
and writes `run.json` metadata into its output directory.

| Command | Input | Output |
|---------|-------|--------|
| `ut datagen --config cfg.toml --out data/gen/` | `data/facts/*.tsv`, `data/templates/*.toml` | `train.txt`, `heldout.jsonl`, `demo.jsonl`, `dataset.sha256` |
| `ut train --config cfg.toml --data data/gen/ --out runs/<name>/` | generated data | `ckpt.pt`, `run.json`, loss log |
| `ut export --ckpt runs/<name>/ckpt.pt --out runs/<name>/model.utny` | checkpoint | UTNY v1 file ([model-format](model-format.md)) |
| `ut eval --model runs/<name>/model.utny --data data/gen/` | model file | `eval.json` (SC-003/SC-004 scores via the quantized reference) |
| `ut golden --model … --prompts … --out golden.json` | model file | parity vectors for `utiny-host --golden` and device tests |
| `ut pipeline --config cfg.toml --out runs/<name>/` | all of the above | full run; exit ≠ 0 if eval or budget check fails |

Options common to all: `--seed N` (default 1234), `--device auto|mps|cpu` (default `auto`:
MPS if available, else CPU).

Configs:

- `configs/v1.toml` — release model (R1 sizes)
- `configs/tiny-test.toml` — d=32, 1 layer, ctx 64; trains in < 1 min on CPU for CI
