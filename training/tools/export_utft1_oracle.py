#!/usr/bin/env python3
"""One-off: freeze every answer of the spec 006 fact table (UTFT v1) as the compat oracle
(specs/008-wissens-compiler/research.md R10, task T001).

    uv run python tools/export_utft1_oracle.py --config configs/chemie-hybrid.toml \
        --out ../topics/chemie/compat/utft1_answers.tsv

Rows: every applicable (letter, key) pair, one not-applicable object per other kind and letter,
one unknown key per letter, one unmapped letter and the missing-table case. Answers are rendered
by `facttable.answer_bytes` from the token sequence <fn> letter key <eos>, exactly as the console
prints them. This tool needs facttable.py and is removed together with UTFT v1 (task T021); the
TSV stays.
"""

from __future__ import annotations

import argparse
import hashlib
import tempfile
from pathlib import Path

from ultratiny import facttable as ft
from ultratiny.alphabet import EOS, Alphabet
from ultratiny.config import load_config
from ultratiny.hybrid import build_facts

UNKNOWN_KEY = "Xyz"
UNMAPPED_LETTER = "X"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--suite", help="also write the image-only bench result of the table (T002)")
    ap.add_argument("--result", help="path of that result JSON")
    a = ap.parse_args()
    cfg = load_config(Path(a.config))
    with tempfile.TemporaryDirectory() as tmp:
        fs, data, _ = build_facts(cfg, Path(tmp))
    table = ft.Table(data)
    assert table.ok
    ab = Alphabet(fn=True)

    def render(letter: str, key: str) -> tuple[str, str]:
        toks = ab.encode("\x01" + letter + key) + [EOS]
        ans = ft.answer_bytes(toks, ab, table).decode("utf-8")
        return table.outcome(letter + key), ans

    rows: list[tuple[str, str, str, str]] = []
    assert UNMAPPED_LETTER not in fs.types
    for code, qt in fs.types.items():
        if qt.reverse_of:
            keys = sorted({v for (k, c), (v, _) in fs.records.items() if c == qt.reverse_of},
                          key=lambda s: s.encode())  # fmt: skip
        else:
            keys = [k for k, o in fs.objects.items() if o.kind in qt.kinds]
            for kind in sorted({o.kind for o in fs.objects.values()} - set(qt.kinds)):
                keys.append(next(k for k, o in fs.objects.items() if o.kind == kind))
        keys.append(UNKNOWN_KEY)
        for key in keys:
            rows.append((code, key, *render(code, key)))
    rows.append((UNMAPPED_LETTER, "Cu", *render(UNMAPPED_LETTER, "Cu")))
    missing = ft.answer_bytes(ab.encode("\x01OCu") + [EOS], ab, ft.Table(None)).decode("utf-8")
    rows.append(("", "", "missing", missing))
    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    sha = hashlib.sha256(data).hexdigest()
    with open(out, "w", encoding="utf-8", newline="\n") as f:
        f.write(f"# UTFT v1 answers, frozen from facts.utft sha256 {sha} ({len(data)} B)\n")
        f.write("letter\tkey\toutcome\tanswer\n")
        for r in rows:
            for c in r:
                assert "\t" not in c and "\n" not in c, r
            f.write("\t".join(r) + "\n")
    counts: dict[str, int] = {}
    for r in rows:
        counts[r[2]] = counts.get(r[2], 0) + 1
    print(f"wrote {out}: {len(rows)} rows {counts}, utft sha256 {sha[:12]}")
    if a.suite and a.result:
        from ultratiny.bench.image import image_result
        from ultratiny.bench.pc import write_result
        from ultratiny.bench.suite import load_suite

        res = image_result(load_suite(a.suite), data, counts["fact"], "facts.utft",
                           "chemie-hybrid-utft1")  # fmt: skip
        write_result(res, Path(a.result))
        k = res["kpis"]
        print(
            f"wrote {a.result}: F7 {k['F7']['value']}, R3 {k['R3']['value']}, R5 {k['R5']['value']}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
