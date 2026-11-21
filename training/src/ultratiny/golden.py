"""Golden parity vectors (research.md R5) for `utiny-host --golden` and device checks.

Logits are stored as uint32 bit patterns so the comparison is exact.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from .reference import Reference


def make_golden(model_path: Path, prompts: list[str], max_len: int = 200) -> dict:
    ref = Reference(model_path)
    cases = []
    for p in prompts:
        r = ref.generate(p, max_len=max_len, record_logits=True)
        cases.append({
            "prompt": p,
            "max": max_len,
            "prompt_tokens": r["prompt_tokens"],
            "tokens": r["tokens"],
            "text": r["text"],
            "logits_bits": [np.asarray(lg, dtype=np.float32).view(np.uint32).tolist()
                            for lg in r["logits"]],
        })  # fmt: skip
    return {"format": 1, "model_size": ref.m.size, "cases": cases}


def write_golden(model_path: Path, prompts: list[str], out: Path, max_len: int = 200) -> dict:
    g = make_golden(model_path, prompts, max_len)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(g, ensure_ascii=False, separators=(",", ":")) + "\n")
    return g
