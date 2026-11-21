#!/usr/bin/env bash
# Train on the DGX Spark GPU inside Docker, with several seeds, verify parity, keep the best.
#
#   tools/spark/train.sh                                   # configs/chemie-spark.toml, 3 seeds
#   tools/spark/train.sh configs/chemie-spark.toml 1 2 3 4 # custom config / seeds
#   NAME=chemie tools/spark/train.sh ...                   # target name in models/ (default: chemie)
#
# Result: models/$NAME.utny (+ _golden.json, _eval.json, _run.json) from the best seed, and a
# comparison table. All runs stay in training/runs/<config>-s<seed>/.
set -euo pipefail

REPO="$(cd "$(dirname "$0")/../.." && pwd)"
CONFIG="${1:-configs/chemie-spark.toml}"
shift || true
SEEDS=("$@")
[ ${#SEEDS[@]} -eq 0 ] && SEEDS=(1234 2345 3456)
NAME="${NAME:-chemie}"
IMAGE="${IMAGE:-ultratiny-train:latest}"
RUN=(docker run --rm --gpus all --ipc=host --user "$(id -u):$(id -g)" -e HOME=/tmp
     -v "$REPO:/work" -w /work/training)
TAG="$(basename "$CONFIG" .toml)"

DOCKERFILE="$REPO/training/docker/Dockerfile.spark"
BASE_IMAGE="${BASE_IMAGE:-$(sed -n 's/^ARG BASE_IMAGE=//p' "$DOCKERFILE")}"
if ! docker image inspect "$BASE_IMAGE" >/dev/null 2>&1; then
    echo "==> Pulling base image $BASE_IMAGE (first time only, ~15-20 GB)"
    docker pull "$BASE_IMAGE"     # shows per-layer download progress
fi
echo "==> Building training image ($IMAGE) on $BASE_IMAGE"
docker build --progress=plain --build-arg BASE_IMAGE="$BASE_IMAGE" -t "$IMAGE" \
    -f "$DOCKERFILE" "$REPO/training/docker"

echo "==> GPU check"
"${RUN[@]}" --entrypoint python "$IMAGE" -c \
    "import torch; print('torch', torch.__version__, '| cuda', torch.cuda.is_available(), '|', torch.cuda.get_device_name(0))"

for seed in "${SEEDS[@]}"; do
    out="runs/$TAG-s$seed"
    echo "==> Training $CONFIG seed $seed -> training/$out"
    # The pipeline exits non-zero when eval thresholds fail; keep going and compare afterwards.
    "${RUN[@]}" "$IMAGE" pipeline --config "$CONFIG" --out "$out" --seed "$seed" --device cuda \
        2>&1 | tee "$REPO/training/$out.log" || true
done

echo "==> Parity: C runtime vs. reference golden vectors (bit-exact)"
"${RUN[@]}" --entrypoint bash "$IMAGE" -c "
    set -e
    cmake -S /work/runtime -B /tmp/build -DCMAKE_BUILD_TYPE=Release >/dev/null
    cmake --build /tmp/build -j >/dev/null
    for d in runs/$TAG-s*/; do
        [ -f \$d/model.utny ] || continue
        printf '%s: ' \"\$d\"; /tmp/build/utiny-host --model \$d/model.utny --golden \$d/golden.json
    done"

echo "==> Selecting the best run"
python3 "$REPO/tools/spark/select_best.py" --name "$NAME" "$REPO"/training/runs/"$TAG"-s*/
