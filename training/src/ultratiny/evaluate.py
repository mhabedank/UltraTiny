"""Evaluation via the quantized reference (research.md R12, spec SC-003/SC-004).

An answer is correct when, after normalization (lower case, punctuation removed,
whitespace collapsed), its edit distance to the expected answer is at most
`max_edit_ratio` (default 0.1) of the expected answer's length.
"""

from __future__ import annotations

import re

from .reference import Reference

_PUNCT = re.compile(r"[.,;:!?\-'\"()/%+=&°]")


def normalize(s: str) -> str:
    return " ".join(_PUNCT.sub(" ", s.lower()).split())


def edit_distance(a: str, b: str) -> int:
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1]


def is_correct(answer: str, expected: str, max_ratio: float = 0.1) -> bool:
    a, e = normalize(answer), normalize(expected)
    return edit_distance(a, e) <= max_ratio * max(1, len(e))


def evaluate(ref: Reference, rows: list[dict], max_ratio: float = 0.1, limit=None) -> dict:
    rows = rows[:limit] if limit else rows
    results = []
    for r in rows:
        out = ref.generate(r["prompt"], max_len=200)["text"]
        results.append({
            "prompt": r["prompt"], "expected": r["expected"], "answer": out,
            "correct": is_correct(out, r["expected"], max_ratio),
        })  # fmt: skip
    n = len(results)
    acc = sum(x["correct"] for x in results) / n if n else 0.0
    return {"n": n, "accuracy": acc, "results": results}
