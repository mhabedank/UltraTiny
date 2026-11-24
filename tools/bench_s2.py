#!/usr/bin/env python3
"""Generate the S2 recall probes of a suite (specs/007-benchmark-kpi-bericht, research R7).

Each probe: filler, "... hieß <word> ...", d characters of filler, "... wieder <word>". The target
word is invented (6-8 letters), so a cheap second occurrence can only come from copying. The control
text is identical except that the first mention is another invented word of the same length.

    uv run python ../tools/bench_s2.py --filler ../bench/suites/allgemein/text/s1.txt \
        --out ../bench/suites/allgemein/text/s2.tsv [--seed 7] [--per 13]
"""

from __future__ import annotations

import argparse
import random
import sys
import tomllib
from pathlib import Path

from ultratiny.alphabet import Alphabet
from ultratiny.bench.lm import clean_text
from ultratiny.bench.suite import parse_s1

DISTANCES = (16, 32, 64, 96, 128, 192, 256, 416)
CONS = "bdfgklmnprstvz"
VOWELS = "aeiou"
LEAD = "Das Ding hieß "
TAIL = " wieder "


def word(rng: random.Random, n: int) -> str:
    s = [rng.choice(CONS).upper()]
    while len(s) < n:
        s.append(rng.choice(VOWELS if s[-1].lower() in CONS else CONS))
    return "".join(s)


def make(filler: str, distances, per: int, seed: int) -> list[dict]:
    rng = random.Random(seed)
    rows = []
    used: set[str] = set()
    for d in distances:
        for _ in range(per):
            n = rng.randint(6, 8)
            while True:
                w, c = word(rng, n), word(rng, n)
                if w != c and w not in used and c not in used and w.lower() not in filler.lower():
                    break
            used |= {w, c}
            pre_start = rng.randrange(0, len(filler) - 40 - d - 40)
            pre = filler[pre_start : pre_start + 40]
            mid_start = rng.randrange(0, len(filler) - d)
            head = pre.strip() + " " + LEAD
            # distance d = characters between the end of the first mention and the second mention
            gap = (", " + filler[mid_start : mid_start + d].strip())[: d - len(TAIL)]
            body = gap.ljust(d - len(TAIL)) + TAIL
            text = head + w + body + w + "."
            ctrl = head + c + body + w + "."
            ts = len(head) + n + len(body)
            assert text[ts : ts + n] == w and len(text) == len(ctrl)
            rows.append(
                {
                    "id": f"s2/{len(rows) + 1:03d}",
                    "distance": d,
                    "target_start": ts,
                    "target_len": n,
                    "text": text,
                    "control": ctrl,
                }
            )
    return rows


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--filler", required=True, help="S1 text; its general half is used as filler")
    ap.add_argument("--out", required=True)
    ap.add_argument("--suite", help="suite.toml with [s2] distances (default: the fixed list)")
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--per", type=int, default=13)
    a = ap.parse_args(argv)
    sec = parse_s1(Path(a.filler).read_text(encoding="utf-8"))
    filler, _ = clean_text(sec.get("general") or " ".join(sec.values()), Alphabet())
    distances = DISTANCES
    if a.suite:
        distances = tuple(
            tomllib.loads(Path(a.suite).read_text(encoding="utf-8"))["s2"]["distances"]
        )
    if len(filler) < max(distances) + 200:
        print("bench_s2: filler text too short", file=sys.stderr)
        return 2
    rows = make(filler, distances, a.per, a.seed)
    with open(a.out, "w", encoding="utf-8", newline="") as f:
        f.write("id\tdistance\ttarget_start\ttarget_len\ttext\tcontrol\n")
        for r in rows:
            f.write(
                f"{r['id']}\t{r['distance']}\t{r['target_start']}\t{r['target_len']}\t"
                f"{r['text']}\t{r['control']}\n"
            )
    print(f"bench_s2: {len(rows)} probes -> {a.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
