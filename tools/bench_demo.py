#!/usr/bin/env python3
"""Demo runner (specs/007-benchmark-kpi-bericht FR-022, contracts/cli.md).

    # two boards (or two host consoles)
    uv run python ../tools/bench_demo.py --script ../bench/demo/007.tsv \
        --a /dev/ttyUSB0 --a-label chemie-nodemcu --b /dev/ttyUSB1 --b-label nodemcu --out demo.md
    # one board: run once per firmware image, then merge
    uv run python ../tools/bench_demo.py --script ../bench/demo/007.tsv --single /dev/ttyUSB0 \
        --label chemie-nodemcu --out run_a.json
    uv run python ../tools/bench_demo.py --merge run_a.json run_b.json --out demo.md

The runner never flashes; it asks the questions on whatever is running on the board.
"""

from __future__ import annotations

import argparse
import os
import shlex
import shutil
import subprocess
import sys
from pathlib import Path

from ultratiny.bench import demo
from ultratiny.bench.board import devlib
from ultratiny.bench.suite import SuiteError


def device(port: str | None, cmd: str | None, timeout: float):
    dl = devlib()
    if port:
        return dl.Device(port, timeout=timeout), True
    return dl.Device(link=dl.ExecLink(shlex.split(cmd)), timeout=timeout), False


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
    ap.add_argument("--script")
    ap.add_argument("--a")
    ap.add_argument("--a-exec")
    ap.add_argument("--a-label", default="A")
    ap.add_argument("--b")
    ap.add_argument("--b-exec")
    ap.add_argument("--b-label", default="B")
    ap.add_argument("--single")
    ap.add_argument("--single-exec")
    ap.add_argument("--label", default="A")
    ap.add_argument("--merge", nargs=2)
    ap.add_argument("--out", required=True)
    ap.add_argument("--timeout", type=float, default=60.0)
    a = ap.parse_args(argv)
    keep_awake()
    if a.merge:
        ra, rb = (demo.load_run(Path(p)) for p in a.merge)
        Path(a.out).write_text(demo.merge_markdown(ra, rb), encoding="utf-8")
        print(f"bench_demo: merged -> {a.out}")
        return 0
    if not a.script:
        print("bench_demo: --script is required", file=sys.stderr)
        return 2
    try:
        script = demo.load_script(Path(a.script))
    except (SuiteError, OSError) as e:
        print(f"bench_demo: {e}", file=sys.stderr)
        return 2
    title = Path(a.script).stem
    if a.single or a.single_exec:
        dev, reset = device(a.single, a.single_exec, a.timeout)
        try:
            demo.save_run(demo.run_single(dev, script, a.label, reset), Path(a.out))
        finally:
            dev.close()
        print(f"bench_demo: {len(script)} questions -> {a.out}")
        return 0
    if not (a.a or a.a_exec) or not (a.b or a.b_exec):
        print(
            "bench_demo: give --a/--a-exec and --b/--b-exec, or --single, or --merge",
            file=sys.stderr,
        )
        return 2
    runs = []
    for port, cmd, label in ((a.a, a.a_exec, a.a_label), (a.b, a.b_exec, a.b_label)):
        dev, reset = device(port, cmd, a.timeout)
        try:
            runs.append(demo.run_single(dev, script, label, reset))
        finally:
            dev.close()
    Path(a.out).write_text(demo.merge_markdown(*runs, title=title), encoding="utf-8")
    print(f"bench_demo: {len(script)} questions on two consoles -> {a.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
