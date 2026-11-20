#!/usr/bin/env python3
"""On-device parity check (SC-006): the board's greedy answers must equal the reference text
in golden.json byte for byte.

    uv run python ../tools/device_parity.py --port /dev/ttyUSB0 --golden ../models/starter_golden.json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from devlib import Device  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", required=True)
    ap.add_argument("--golden", required=True)
    ap.add_argument("--char-delay", type=float, default=0.02)
    a = ap.parse_args()
    cases = json.loads(Path(a.golden).read_text(encoding="utf-8"))["cases"]
    dev = Device(a.port)
    dev.reset()
    dev.command("/modus gierig")
    fails = 0
    for i, c in enumerate(cases):
        dev.command(f"/max {c['max']}")
        got = dev.ask(c["prompt"], a.char_delay)
        if got != c["text"]:
            fails += 1
            print(f"MISMATCH case {i}: {c['prompt']!r}\n  board: {got!r}\n  ref:   {c['text']!r}")
    dev.close()
    print(f"device parity: {len(cases)} cases, {fails} mismatches")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
