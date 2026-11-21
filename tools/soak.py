#!/usr/bin/env python3
"""Endurance test (SC-005): 100 prompts over >= 1 hour, no reset, stable free heap.

    uv run python ../tools/soak.py --port /dev/ttyUSB0 --count 100 --pause 36
"""

from __future__ import annotations

import argparse
import csv
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from devlib import Device  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", required=True)
    ap.add_argument("--prompts", default=str(Path(__file__).parents[1] / "training/data/demo_prompts.tsv"))
    ap.add_argument("--count", type=int, default=100)
    ap.add_argument("--pause", type=float, default=36.0, help="seconds between prompts")
    a = ap.parse_args()
    with open(a.prompts, encoding="utf-8", newline="") as f:
        prompts = [r["prompt"] for r in csv.DictReader(f, delimiter="\t", quoting=csv.QUOTE_NONE)]
    dev = Device(a.port)
    dev.reset()
    heaps, resets, t0 = [], 0, time.time()
    for i in range(a.count):
        ans = dev.ask(prompts[i % len(prompts)])
        if "UltraTiny v" in ans:
            resets += 1
        heap = dev.info().get("free_heap")
        heaps.append(heap)
        print(f"{i + 1:3d}/{a.count} heap={heap} {ans[:60]!r}")
        time.sleep(a.pause)
    dev.close()
    hours = (time.time() - t0) / 3600
    stable = len(set(h for h in heaps if h is not None)) <= 2
    ok = resets == 0 and stable and hours >= 1.0
    print(f"duration {hours:.2f} h, resets {resets}, heap min/max {min(heaps)}/{max(heaps)}")
    print("PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
