#!/usr/bin/env python3
"""Build data/demo_chemie.tsv (spec 003 SC-001) deterministically from the chemistry data.

Picks: a fixed set of element/formula questions (exact template answers) plus the first
phrasing of every k-th concept/reaction/persona row, so every Themenfeld is covered.

    uv run python tools/make_demo_chemie.py
"""

from __future__ import annotations

import csv
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FACTS = ROOT / "data" / "facts"

ELEMENT_QUESTIONS = [
    ("element_symbol", "Gold", "Was ist das Symbol von {s}?", "Das Symbol von {s} ist {o}."),
    ("element_symbol", "Natrium", "Welches Symbol hat {s}?", "Das Symbol von {s} ist {o}."),
    ("element_symbol", "Quecksilber", "Welches Element hat das Symbol {o}?",
     "{o} ist das Symbol von {s}."),
    ("element_ordnungszahl", "Eisen", "Welche Ordnungszahl hat {s}?",
     "{s} hat die Ordnungszahl {o}."),
    ("element_ordnungszahl", "Kohlenstoff", "Welches Element hat die Ordnungszahl {o}?",
     "Das Element mit der Ordnungszahl {o} ist {s}."),
    ("element_atommasse", "Sauerstoff", "Welche Atommasse hat {s}?",
     "Die Atommasse von {s} beträgt etwa {o} u."),
    ("element_periode", "Natrium", "In welcher Periode steht {s}?",
     "{s} steht in der {o}. Periode."),
    ("element_gruppe", "Chlor", "In welcher Gruppe steht {s}?", "{s} steht in {o}."),
    ("element_familie", "Neon", "Zu welcher Elementfamilie gehört {s}?",
     "{s} gehört zu den {o}."),
    ("element_kategorie", "Schwefel", "Ist {s} ein Metall oder ein Nichtmetall?",
     "{s} ist ein {o}."),
    ("element_zustand", "Brom", "Welchen Aggregatzustand hat {s} bei Raumtemperatur?",
     "{s} ist bei Raumtemperatur {o}."),
    ("element_siedepunkt", "Sauerstoff", "Bei welcher Temperatur siedet {s}?",
     "{s} siedet bei etwa {o} °C."),
]  # fmt: skip
FORMULA_NAMES = ["Wasser", "Kohlenstoffdioxid", "Natriumchlorid", "Methan", "Ammoniak"]
EVERY = {"chemie_rlp_": 6, "chemie_reaktionen.tsv": 8, "chemie_persona.tsv": 6}


def rows(path: Path) -> list[dict]:
    with path.open(encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f, delimiter="\t", quoting=csv.QUOTE_NONE))


def main() -> int:
    out: list[tuple[str, str]] = []
    elements = {(r["relation"], r["subject"]): r["object"]
                for r in rows(FACTS / "wikidata_elemente_chemie.tsv")}  # fmt: skip
    for rel, s, q, a in ELEMENT_QUESTIONS:
        o = elements.get((rel, s))
        if o is None:
            print(f"skip {rel} {s}: no fact", file=sys.stderr)
            continue
        out.append((q.format(s=s, o=o), a.format(s=s, o=o)))
    formulas = {r["subject"]: r["object"] for r in rows(FACTS / "chemie_verbindungen.tsv")}
    for name in FORMULA_NAMES:
        if name in formulas:
            out.append((f"Welche Formel hat {name}?", f"{name} hat die Formel {formulas[name]}."))
    for pattern, k in EVERY.items():
        for path in sorted(FACTS.glob(pattern + ("*.tsv" if pattern.endswith("_") else ""))):
            for i, r in enumerate(rows(path)):
                if i % k == 0:
                    out.append((r["subject"].split("|")[0], r["object"]))
    target = ROOT / "data" / "demo_chemie.tsv"
    with target.open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f, delimiter="\t", lineterminator="\n", quoting=csv.QUOTE_NONE)
        w.writerow(["prompt", "expected"])
        w.writerows(out)
    print(f"wrote {target} ({len(out)} prompts)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
