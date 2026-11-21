#!/usr/bin/env python3
"""Compare training runs (eval.json, budget.json) and copy the best one to models/<name>.*

Score: chemistry held-out accuracy (SC-002) + demo accuracy (SC-001) + 0.5 x refusal rate
(SC-003) - 5 x false-refusal rate (SC-004). Runs that miss the budget are never selected.
Standard library only.

    python3 tools/spark/select_best.py --name chemie training/runs/chemie-spark-s*/
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]


def score(ev: dict) -> tuple[float, dict]:
    demo = ev["demo"]["accuracy"]
    ref = ev.get("refusal", {})
    held = ref.get("chem_heldout", ev["heldout"]["accuracy"])
    m = {"demo": demo, "held": held, "refusal": ref.get("refusal_rate", 0.0),
         "false_ref": ref.get("false_refusal", 0.0)}  # fmt: skip
    return held + demo + 0.5 * m["refusal"] - 5 * m["false_ref"], m


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("runs", nargs="+", type=Path)
    ap.add_argument("--name", default="chemie")
    a = ap.parse_args()
    rows = []
    for d in a.runs:
        try:
            ev = json.loads((d / "eval.json").read_text())
            budget = json.loads((d / "budget.json").read_text())
        except FileNotFoundError:
            print(f"{d}: incomplete, skipped")
            continue
        s, m = score(ev)
        rows.append((s, d, m, budget.get("ok", False)))
    if not rows:
        print("no complete runs")
        return 1
    print(f"{'run':40s} {'demo':>6s} {'held':>6s} {'refus':>6s} {'false':>6s} {'budget':>6s} score")
    for s, d, m, ok in sorted(rows, key=lambda r: -r[0]):
        print(f"{d.name:40s} {m['demo']:6.3f} {m['held']:6.3f} {m['refusal']:6.3f} "
              f"{m['false_ref']:6.3f} {'ok' if ok else 'FAIL':>6s} {s:.3f}")  # fmt: skip
    candidates = [r for r in rows if r[3]]
    if not candidates:
        print("no run within budget")
        return 1
    best = max(candidates, key=lambda r: r[0])[1]
    models = REPO / "models"
    for src, suffix in (("model.utny", ".utny"), ("golden.json", "_golden.json"),
                        ("eval.json", "_eval.json"), ("run.json", "_run.json")):  # fmt: skip
        shutil.copyfile(best / src, models / f"{a.name}{suffix}")
    print(f"best: {best.name} -> models/{a.name}.utny (+ golden, eval, run.json)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
