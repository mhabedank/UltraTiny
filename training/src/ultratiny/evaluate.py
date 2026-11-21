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


def refusal_metrics(
    demo: dict, heldout: dict, heldout_rows: list[dict], refusal_relation: str = "abweisen"
) -> dict:
    """Split held-out results into chemistry vs. refusal prompts (spec 003 SC-002..SC-004).

    - chem_heldout: accuracy on held-out prompts that are not refusals
    - refusal_rate: share of held-out off-topic prompts answered with the refusal
    - false_refusal: share of demo + chemistry held-out prompts answered with the refusal
    """
    refusal_texts = {r["expected"] for r in heldout_rows if r.get("relation") == refusal_relation}
    if not refusal_texts:
        return {}
    refusal_norm = {normalize(t) for t in refusal_texts}
    chem, refused_ok, n_ref, false_ref, n_chem_all = [], 0, 0, 0, 0
    for row, res in zip(heldout_rows, heldout["results"], strict=True):
        if row.get("relation") == refusal_relation:
            n_ref += 1
            refused_ok += res["correct"]
        else:
            chem.append(res["correct"])
    for res in demo["results"] + [
        r
        for row, r in zip(heldout_rows, heldout["results"], strict=True)
        if row.get("relation") != refusal_relation
    ]:
        n_chem_all += 1
        false_ref += normalize(res["answer"]) in refusal_norm
    return {
        "chem_heldout": sum(chem) / len(chem) if chem else 0.0,
        "n_chem_heldout": len(chem),
        "refusal_rate": refused_ok / n_ref if n_ref else 0.0,
        "n_refusal": n_ref,
        "false_refusal": false_ref / n_chem_all if n_chem_all else 0.0,
    }
