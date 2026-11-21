# Measurements: 003-chemielehrer

Status 2026-11-21: work on this feature paused in favor of the NodeMCU (ESP8266) target; no
chemistry model was finished on this branch.

## Data (committed)

| Item | Value |
|------|-------|
| Facts | 1,792 (curriculum Q&A 464, reactions 86, persona 28, element profiles 974, formulas 90, refusal rows 150) |
| Train examples (`configs/chemie.toml`) | 61,806 (after held-out leak guard: 61,776) |
| Held-out prompts / demo prompts | 3,104 / 105 |
| LLM augmentation (`training/data/augment/*.tsv`) | generated on the Spark with gemma4:e4b, **not committed** |

## Training runs (interrupted, no model exported)

| Run | Hardware | Reached | Train loss |
|-----|----------|---------|------------|
| `chemie.toml` | container CPU (4 cores) | step 6,300 / 12,000 (2 h limit) | 0.0345 |
| `chemie-spark.toml`, seed 1234 | DGX Spark GB10 (Docker `--runtime=nvidia`) | step 7,500 / 66,000 | 0.0337 |

Spark loss curve (every 100 steps; step 4,700 not recorded):
0 4.5529 · 500 0.7747 · 1000 0.2527 · 1500 0.1559 · 2000 0.1206 · 2500 0.0978 · 3000 0.0798 ·
3500 0.0685 · 4000 0.0604 · 4500 0.0558 · 5000 0.0497 · 5500 0.0449 · 6000 0.0423 ·
6500 0.0382 · 7000 0.0353 · 7500 0.0337

No eval (demo / held-out / refusal) exists yet: the pipeline evaluates only after the last step.

## Spark notes

- Docker GPU: `--gpus all` and CDI fail (stale NVIDIA toolkit file list:
  `libnvidia-egl-wayland.so.1.1.21` listed, 1.1.23 installed, reboot pending);
  `--runtime=nvidia -e NVIDIA_VISIBLE_DEVICES=all` works. `tools/spark/train.sh` auto-detects.
- No GitHub push from the Spark service account: copy results via the Mac (`scp`).
