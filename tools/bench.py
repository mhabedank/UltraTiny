#!/usr/bin/env python3
"""Benchmark measurement (specs/007-benchmark-kpi-bericht, contracts/cli.md).

Run from training/:

    uv run python ../tools/bench.py pc --suite ../bench/suites/allgemein \
        --model ../models/nodemcu.utny
    uv run python ../tools/bench.py pc ... --check ../bench/results/nodemcu_allgemein_pc.json
    uv run python ../tools/bench.py board --suite ... --model ... --port /dev/ttyUSB0
    uv run python ../tools/bench.py pin --suite ../bench/suites/allgemein   # re-pin after a change

Exit codes: 0 ok, 1 measured but a check failed (--check, parity), 2 usage or input error.
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

from ultratiny.bench import pc
from ultratiny.bench.suite import REPO_ROOT, SuiteError, load_suite, pin_suite

RESULTS = REPO_ROOT / "bench" / "results"


def cmd_pc(a) -> int:
    try:
        suite = load_suite(a.suite)
    except SuiteError as e:
        print(f"bench: {e}", file=sys.stderr)
        return 2
    if a.facts and not Path(a.facts).exists():
        print(f"bench: {a.facts}: knowledge image missing", file=sys.stderr)
        return 2
    only = set(a.only.split(",")) if a.only else None
    t0 = time.time()
    try:
        result = pc.run_pc(
            suite,
            Path(a.model),
            Path(a.facts) if a.facts else None,
            a.label,
            a.jobs,
            only,
            Path(a.train_data) if a.train_data else None,
        )
    except (ValueError, OSError) as e:
        print(f"bench: {e}", file=sys.stderr)
        return 2
    result["env"]["seconds"] = round(time.time() - t0, 1)
    out = Path(a.out) if a.out else pc.default_out(result, RESULTS)
    if a.check:
        ref_path = Path(a.check)
        sheet = pc.sheet_path(ref_path)
        result["kpis"]["S3"] = pc.s3_from_ratings(result, pc.read_ratings(sheet))
        diffs = pc.check(result, pc.read_result(ref_path))
        print("\n".join(pc.summary_lines(result)))
        if diffs:
            print(f"bench --check: {len(diffs)} difference(s) to {ref_path}:")
            print("\n".join("  " + d for d in diffs))
            print("Fix: re-measure and commit the result in the same pull request (spec FR-024).")
            return 1
        print(f"bench --check: OK ({result['env']['seconds']} s)")
        return 0
    result["kpis"]["S3"] = pc.write_sheet(result, pc.sheet_path(out))
    pc.write_result(result, out)
    print("\n".join(pc.summary_lines(result)))
    print(f"bench: wrote {out} ({result['env']['seconds']} s)")
    return 0


def cmd_board(a) -> int:
    from ultratiny.bench import board

    return board.main(a)


def cmd_pin(a) -> int:
    try:
        new = pin_suite(a.suite)
    except (SuiteError, OSError) as e:
        print(f"bench: {e}", file=sys.stderr)
        return 2
    for rel, d in new.items():
        print(f"  {d}  {rel}")
    print("bench: pins updated; bump `version` in suite.toml if results were already compared")
    return 0


def keep_awake() -> None:
    """macOS: keep the Mac awake while this process runs (a sleeping Mac stops reading the serial
    port, so board answers get lost). `caffeinate -w` ends together with this process."""
    if sys.platform == "darwin" and shutil.which("caffeinate"):
        subprocess.Popen(["caffeinate", "-dims", "-w", str(os.getpid())])
        print("bench: caffeinate is keeping the Mac awake during the run", file=sys.stderr)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("pc", help="measure a model on the PC (US1)")
    p.add_argument("--suite", required=True)
    p.add_argument("--model", required=True)
    p.add_argument("--facts", help="knowledge image (.utft)")
    p.add_argument("--label", help="step name for grouping seeds (default: model meta name)")
    p.add_argument("--out")
    p.add_argument("--train-data", help="training data (train.txt) for the overlap report")
    p.add_argument("--jobs", type=int, default=1)
    p.add_argument(
        "--only", help="comma-separated sets (unseen,unknown,offtopic,kurzarbeit,s3,facts,s1,s2)"
    )
    p.add_argument("--check", help="compare with this committed result; exit 1 on any difference")
    p.set_defaults(fn=cmd_pc)
    p = sub.add_parser("board", help="measure on the board or a host console (US4)")
    p.add_argument("--suite", required=True)
    p.add_argument("--model", required=True)
    p.add_argument("--facts")
    p.add_argument("--label")
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--port")
    g.add_argument(
        "--exec", dest="exec_cmd", help='e.g. "../build/utiny-host --model m.utny --console"'
    )
    p.add_argument("--out")
    p.add_argument("--firmware", help="firmware.bin for the budget section")
    p.add_argument("--sample", choices=("all", "parity"), default="all")
    p.add_argument("--timeout", type=float, default=60.0)
    p.set_defaults(fn=cmd_board)
    p = sub.add_parser("pin", help="re-pin all files of a suite")
    p.add_argument("--suite", required=True)
    p.set_defaults(fn=cmd_pin)
    a = ap.parse_args(argv)
    keep_awake()
    return a.fn(a)


if __name__ == "__main__":
    sys.exit(main())
