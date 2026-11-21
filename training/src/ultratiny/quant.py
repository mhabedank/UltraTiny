"""Shared quantization rules (contracts/model-format.md "Quantization rules").

All arithmetic is float32 and mirrors runtime/src/mathx.c operation by operation:

    amax  = max |x|
    scale = amax / 127          (1.0 if amax == 0)
    v     = x / scale
    q     = sign(v) * floor(|v| + 0.5)   clamped to [-127, 127]

floor(|v| + 0.5) is evaluated in float32 (not Python's round-half-even), exactly like C's
`floorf(fabsf(v) + 0.5f)`.
"""

from __future__ import annotations

import numpy as np

F32 = np.float32
Q_MAX = F32(127.0)
HALF = F32(0.5)


def round_half_away(v: np.ndarray) -> np.ndarray:
    v = np.asarray(v, dtype=np.float32)
    mag = np.floor(np.abs(v) + HALF).astype(np.float32)
    return np.where(v < 0, -mag, mag).astype(np.float32)


def quantize_vector(x: np.ndarray) -> tuple[np.ndarray, np.float32]:
    """Per-vector absmax int8 quantization of activations."""
    x = np.asarray(x, dtype=np.float32)
    amax = F32(np.max(np.abs(x))) if x.size else F32(0.0)
    if amax == 0:
        return np.zeros(x.shape, dtype=np.int8), F32(1.0)
    scale = F32(amax / Q_MAX)
    q = np.clip(round_half_away(x / scale), -127, 127).astype(np.int8)
    return q, scale


def quantize_rows(w: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Per-row absmax int8 quantization of a weight matrix [rows, cols]."""
    w = np.asarray(w, dtype=np.float32)
    amax = np.max(np.abs(w), axis=1).astype(np.float32)
    scale = np.where(amax == 0, F32(1.0), amax / Q_MAX).astype(np.float32)
    q = np.clip(round_half_away(w / scale[:, None]), -127, 127).astype(np.int8)
    return q, scale


def dequantize_rows(q: np.ndarray, scale: np.ndarray) -> np.ndarray:
    return (q.astype(np.float32) * scale[:, None]).astype(np.float32)
