"""Golden parity vectors (research.md R5) for `utiny-host --golden` and device checks.

Logits are stored as uint32 bit patterns so the comparison is exact.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np

from . import facttable
from .reference import Reference

UT_ANSWER_RESERVE = 32  # runtime/include/utiny_console.h: the console caps questions below this


def make_golden(model_path: Path, prompts: list[str], max_len: int = 200,
                facts_bytes: bytes | None = None) -> dict:  # fmt: skip
    """Golden cases. With a fact table (specs/006), each case that the console can type in full
    also gets `printed`: the exact bytes the console prints (facttable.answer_bytes)."""
    ref = Reference(model_path)
    table = facttable.Table(facts_bytes) if facts_bytes is not None else None
    max_q = ref.cfg.ctx_len - 2 - UT_ANSWER_RESERVE
    cases = []
    for p in prompts:
        r = ref.generate(p, max_len=max_len, record_logits=True)
        case = {
            "prompt": p,
            "max": max_len,
            "prompt_tokens": r["prompt_tokens"],
            "tokens": r["tokens"],
            "text": r["text"],
            "logits_bits": [np.asarray(lg, dtype=np.float32).view(np.uint32).tolist()
                            for lg in r["logits"]],
        }  # fmt: skip
        if table is not None and len(p) <= max_q:
            case["printed"] = facttable.answer_bytes(r["tokens"], ref.m.alphabet, table).decode()
        cases.append(case)
    g = {"format": 1, "model_size": ref.m.size, "cases": cases}
    if facts_bytes is not None:
        g["facts_sha256"] = hashlib.sha256(facts_bytes).hexdigest()
    return g


def write_golden(model_path: Path, prompts: list[str], out: Path, max_len: int = 200,
                 facts_bytes: bytes | None = None) -> dict:  # fmt: skip
    g = make_golden(model_path, prompts, max_len, facts_bytes)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(g, ensure_ascii=False, separators=(",", ":")) + "\n")
    return g
