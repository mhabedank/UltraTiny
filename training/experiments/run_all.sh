#!/usr/bin/env bash
# Runs the 004 comparison set: two jobs at a time, 2 threads each (4-core container).
# Usage: experiments/run_all.sh <datagen-dir> <out-dir>
set -u
DATA=$1; OUT=$2; mkdir -p "$OUT"
COMMON="--data $DATA --steps 3000 --threads 2"
run() { name=$1; shift; uv run python experiments/qexp.py $COMMON --out "$OUT/$name" "$@" > "$OUT/$name.log" 2>&1; }
run base & run tricks --ema 0.999 --ls 0.1 & wait
run bpe --tok bpe --bpe-vocab 384 --d-ff 344 & run swiglu_rope --ffn swiglu --pos rope --d-ff 256 & wait
run int4ffn --ffn-bits 4 --d-ff 768 --steps 2400 --qat-steps 600 & run cls --cls 1 & wait
