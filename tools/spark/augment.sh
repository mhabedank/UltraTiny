#!/usr/bin/env bash
# Generate LLM augmentation data on the DGX Spark with the local Ollama (no Docker needed:
# the generator uses only the Python standard library).
#
#   tools/spark/augment.sh                       # qwen3.6:35b, no thinking, with check prompt
#   JUDGE=none tools/spark/augment.sh            # fastest: skip the check prompt
#   MODEL=gemma4:e4b JUDGE=none tools/spark/augment.sh   # even smaller model
#   MODEL=gpt-oss:120b tools/spark/augment.sh    # best quality, slow
#
# Output: training/data/augment/{paraphrasen,vorlagen,abweisen}.tsv (commit these).
# Interrupted runs resume from training/runs/augment_cache/.
set -euo pipefail

REPO="$(cd "$(dirname "$0")/../.." && pwd)"
HOST="${OLLAMA_HOST_URL:-http://localhost:11434}"
MODEL="${MODEL:-qwen3.6:35b}"
JUDGE="${JUDGE:-$MODEL}"
WORKERS="${WORKERS:-4}"
TASK=("$@")
[ ${#TASK[@]} -eq 0 ] && TASK=(all)

curl -sf "$HOST/api/tags" >/dev/null || { echo "Ollama not reachable at $HOST"; exit 1; }
echo "==> Ollama $HOST, model $MODEL, judge $JUDGE, workers $WORKERS"
echo "    (more parallelism: start ollama with OLLAMA_NUM_PARALLEL=$WORKERS)"
cd "$REPO/training"
if [ "$JUDGE" = "none" ]; then JUDGE_ARGS=(--no-judge); else JUDGE_ARGS=(--judge-model "$JUDGE"); fi
PYTHONUNBUFFERED=1 python3 tools/augment_llm.py --host "$HOST" --model "$MODEL" "${JUDGE_ARGS[@]}" \
    --workers "$WORKERS" "${TASK[@]}"
echo "==> Done. Log: training/runs/augment.log. Check: git diff --stat training/data/augment/"
