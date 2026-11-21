#!/usr/bin/env bash
# Python venv with CUDA PyTorch in the home directory - for training on the DGX Spark without
# Docker and without sudo (UT_NO_DOCKER=1 tools/spark/train.sh).
#
#   tools/spark/setup_venv.sh                       # default index: CUDA 13.0 wheels (aarch64)
#   TORCH_INDEX=https://download.pytorch.org/whl/cu128 tools/spark/setup_venv.sh
set -euo pipefail

VENV="${UT_VENV:-$HOME/.venvs/ultratiny}"
TORCH_INDEX="${TORCH_INDEX:-https://download.pytorch.org/whl/cu130}"

echo "==> Creating venv $VENV"
if ! python3 -m venv "$VENV" 2>/dev/null; then
    # Ubuntu without python3-venv (needs sudo): use uv instead (user install, no sudo):
    #   curl -LsSf https://astral.sh/uv/install.sh | sh
    command -v uv >/dev/null || { echo "python3-venv missing and no uv. Install uv:"; \
        echo "  curl -LsSf https://astral.sh/uv/install.sh | sh"; exit 1; }
    uv venv --seed "$VENV"
fi
"$VENV/bin/python" -m pip install --upgrade pip
echo "==> Installing PyTorch with CUDA from $TORCH_INDEX (~2-3 GB, shows progress)"
"$VENV/bin/pip" install torch --index-url "$TORCH_INDEX"
"$VENV/bin/pip" install "numpy>=2.0,<3" "tomli-w>=1.0"
echo "==> GPU check"
"$VENV/bin/python" -c "import torch; print('torch', torch.__version__, '| cuda', torch.cuda.is_available()); print(torch.cuda.get_device_name(0))"
echo "==> Done. Train with: UT_NO_DOCKER=1 tools/spark/train.sh"
