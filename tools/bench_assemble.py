#!/usr/bin/env python3
"""Assemble a suite's test sets and S1 text from the LLM proposals (specs/007 T019/T026).

Deterministic (fixed seed): the same proposals always give the same files, so the sets can be
rebuilt and reviewed. Expected answers come from the proposal's (property, object), which the
request fixed; the LLM only wrote the question text.

    uv run python ../tools/bench_assemble.py --suite ../bench/suites/chemie \
        --general <public-domain text> --general-source "Franz Kafka, Die Verwandlung (1915), ..."

Writes sets/unseen.tsv (fact questions, shuffled; the 10 longest are the T3 prompts and come
last), sets/unknown.tsv, sets/offtopic.tsv, sets/s3.tsv (20 prompts; fact-like prompts are
dropped and the rest is filled from unused off-topic proposals) and text/s1.txt (topic half from
the text proposals, general half from --general). Prints the T3 ids for suite.toml.
"""

from __future__ import annotations

import argparse
import random
import sys
from pathlib import Path

from ultratiny.bench.suite import load_suite, norm_q, read_tsv

S3_N = 20
T3_N = 10
HALF = 10_000


def training_text() -> str:
    root = Path(__file__).resolve().parents[1] / "training" / "data"
    return " ".join(
        " ".join(p.read_text(encoding="utf-8", errors="replace").split())
        for p in sorted(root.rglob("*"))
        if p.is_file() and p.suffix in (".tsv", ".toml", ".txt")
    )


def write(path: Path, rows: list[tuple]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="") as f:
        f.write("id\tgrade\tkind\tquestion\texpected\n")
        for r in rows:
            f.write("\t".join(r) + "\n")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--suite", required=True)
    ap.add_argument("--general", required=True, help="general half of S1 (prepared text)")
    ap.add_argument("--general-source", required=True)
    ap.add_argument("--seed", type=int, default=7)
    a = ap.parse_args(argv)
    d = Path(a.suite)
    suite = load_suite(d, allow_unpinned=True)
    prop_dir = d / "proposals"
    rng = random.Random(a.seed)
    names = {f.object_name.lower() for f in suite.facts.values()}
    names |= {o.lower() for o, _ in suite.facts if len(o) > 2}

    # unseen: every proposal whose (property, object) has a fact; T3 = the 10 longest questions
    qs = [
        r
        for r in read_tsv(prop_dir / "questions.tsv")
        if (r["object"], r["property"]) in suite.facts
    ]
    qs.sort(key=lambda r: (r["property"], r["object"], r["question"]))
    t3 = sorted(qs, key=lambda r: (-len(r["question"]), r["question"]))[:T3_N]
    rest = [r for r in qs if r not in t3]
    rng.shuffle(rest)
    unseen = []
    for i, r in enumerate(rest + t3, 1):
        unseen.append(
            (f"un/{i:03d}", "-", "fact", r["question"], f"{r['property']}: {r['object']}")
        )
    t3_ids = [u[0] for u in unseen[len(rest) :]]
    write(d / "sets" / "unseen.tsv", unseen)

    unk = [r["question"] for r in read_tsv(prop_dir / "unknown.tsv")]
    write(
        d / "sets" / "unknown.tsv",
        [(f"uk/{i:03d}", "-", "unknown", q, "") for i, q in enumerate(unk, 1)],
    )

    s3 = [r["question"] for r in read_tsv(prop_dir / "s3.tsv")]
    s3 = [q for q in s3 if not any(n in norm_q(q).split() for n in names)]  # no fact questions
    off = [r["question"] for r in read_tsv(prop_dir / "offtopic.tsv")]
    used = {norm_q(q) for q in s3}
    off = [q for q in off if norm_q(q) not in used]
    fill = max(0, S3_N - len(s3))
    s3 = s3 + off[len(off) - fill :] if fill else s3[:S3_N]
    off = off[: len(off) - fill] if fill else off
    write(
        d / "sets" / "offtopic.tsv",
        [(f"ot/{i:03d}", "-", "refuse", q, "") for i, q in enumerate(off, 1)],
    )
    write(
        d / "sets" / "s3.tsv", [(f"s3/{i:03d}", "-", "explain", q, "") for i, q in enumerate(s3, 1)]
    )

    train = training_text()
    topic, n, skipped = [], 0, 0
    for r in read_tsv(prop_dir / "text.tsv"):
        if n >= HALF:
            break
        para = " ".join(r["text"].split())
        if any(para[i : i + 40] in train for i in range(0, max(1, len(para) - 39), 10)):
            skipped += 1  # shares a 40-character span with training data (research R6)
            continue
        topic.append(para)
        n += len(r["text"]) + 1
    general = " ".join(Path(a.general).read_text(encoding="utf-8").split())
    s1 = (
        f"# S1 test text of suite {suite.name} (specs/007 research R6). Evaluation only.\n"
        f"# Topic half: paragraphs proposed by a local LLM (proposals/text.tsv), reviewed.\n"
        f"# General half: {a.general_source} (public domain).\n"
        "# topic\n" + "\n".join(topic) + "\n# general\n" + general + "\n"
    )
    (d / "text").mkdir(exist_ok=True)
    (d / "text" / "s1.txt").write_text(s1, encoding="utf-8")
    print(
        f"bench_assemble: {suite.name}: unseen {len(unseen)} (T3 {len(t3_ids)}), unknown "
        f"{len(unk)}, offtopic {len(off)}, s3 {len(s3)}, S1 topic {n} + general "
        f"{len(general)} characters, {skipped} paragraph(s) skipped for training overlap"
    )
    print("t3 = [" + ", ".join(f'"{i}"' for i in t3_ids) + "]")
    if len(s3) < S3_N:
        print(f"bench_assemble: only {len(s3)} S3 prompts", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
