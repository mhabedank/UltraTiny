#!/bin/sh
# Fails if runtime code reads int8 model-image data byte-wise instead of via ut_ld32
# (specs/005-nodemcu-port/contracts/runtime-image-access.md). Image int8 data is reached through
# ut_qmat.w (weights, embeddings); indexing it directly would be a byte load from flash.
src="${1:?usage: image_access_lint.sh <runtime/src>}"
bad=$(grep -nE '(\.|->)w\[|\b(te|pe)\[' "$src"/*.c || true)
if [ -n "$bad" ]; then
    echo "byte-wise read of model-image int8 data (use ut_ld32):"
    echo "$bad"
    exit 1
fi
echo "image access lint: ok"
