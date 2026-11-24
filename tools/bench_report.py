#!/usr/bin/env python3
"""Benchmark comparison report (specs/007-benchmark-kpi-bericht, contracts/cli.md).

    uv run python ../tools/bench_report.py RESULT.json [RESULT.json ...] \
        [--baseline LABEL] [--predecessor LABEL] [--md OUT.md] [--html OUT.html] [--strict]

Results with the same label are seeds of one step; PC and board results of a label are merged.
S3 ratings are read from the rating sheet next to each PC result (<result>.s3.tsv).
Exit codes: 0 ok, 1 with --strict when a budget or parity is broken, 2 input error.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from ultratiny.bench import report
from ultratiny.bench.pc import read_result


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("results", nargs="+")
    ap.add_argument("--baseline")
    ap.add_argument("--predecessor")
    ap.add_argument("--md")
    ap.add_argument("--html")
    ap.add_argument("--strict", action="store_true")
    a = ap.parse_args(argv)
    try:
        results = [(Path(p), read_result(Path(p))) for p in a.results]
        rep = report.build(results, a.baseline, a.predecessor)
    except (OSError, ValueError, KeyError) as e:
        print(f"bench_report: {e}", file=sys.stderr)
        return 2
    md = report.to_markdown(rep)
    if a.md:
        Path(a.md).write_text(md, encoding="utf-8")
    if a.html:
        Path(a.html).write_text(report.to_html(rep), encoding="utf-8")
    if not a.md and not a.html:
        print(md)
    flags = [
        f
        for f, on in (
            ("budget broken", rep["budget_broken"]),
            ("parity broken", rep["parity_broken"]),
        )
        if on
    ]
    print("bench_report: " + (", ".join(flags) if flags else "ok"), file=sys.stderr)
    return 1 if a.strict and flags else 0


if __name__ == "__main__":
    sys.exit(main())
