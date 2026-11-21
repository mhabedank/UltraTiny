#!/usr/bin/env bash
# Generate LLM augmentation data on the DGX Spark with the local Ollama (no Docker needed:
# the generator uses only the Python standard library).
#
#   tools/spark/augment.sh                       # gpt-oss:120b, all three tasks
#   MODEL=qwen3.6:35b tools/spark/augment.sh     # faster model
#   JUDGE=gpt-oss:120b MODEL=qwen3.6:35b tools/spark/augment.sh paraphrase --n 20
#
# Output: training/data/augment/{paraphrasen,vorlagen,abweisen}.tsv (commit these).
# Interrupted runs resume from training/runs/augment_cache/.
set -euo pipefail

REPO="$(cd "$(dirname "$0")/../.." && pwd)"
HOST="${OLLAMA_HOST_URL:-http://localhost:11434}"
MODEL="${MODEL:-gpt-oss:120b}"
JUDGE="${JUDGE:-$MODEL}"
WORKERS="${WORKERS:-4}"
TASK=("$@")
[ ${#TASK[@]} -eq 0 ] && TASK=(all)

curl -sf "$HOST/api/tags" >/dev/null || { echo "Ollama not reachable at $HOST"; exit 1; }
echo "==> Ollama $HOST, model $MODEL, judge $JUDGE, workers $WORKERS"
echo "    (more parallelism: start ollama with OLLAMA_NUM_PARALLEL=$WORKERS)"
cd "$REPO/training"
python3 tools/augment_llm.py --host "$HOST" --model "$MODEL" --judge-model "$JUDGE" \
    --workers "$WORKERS" "${TASK[@]}"
echo "==> Done. Check with: git diff --stat training/data/augment/"
