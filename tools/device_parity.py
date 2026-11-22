#!/usr/bin/env python3
"""On-device parity check (SC-006): the board's greedy answers must equal the reference text
in golden.json byte for byte. For hybrid models (specs/006) the golden case's `printed` field
(the answer the console prints, incl. fact-table lookups) is compared instead of `text`.

    uv run python ../tools/device_parity.py --port /dev/ttyUSB0 \
        --golden ../models/nodemcu_golden.json
    uv run python ../tools/device_parity.py --tcp localhost:5555 --golden ...  # QEMU
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from devlib import PROMPT, Device, TcpLink  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("--port")
    src.add_argument("--tcp", metavar="HOST:PORT")
    ap.add_argument("--golden", required=True)
    ap.add_argument("--char-delay", type=float, default=0.02)
    # The NodeMCU feeds one typed character per ~0.1 s and answers at ~5-10 chars/s, so allow
    # generous time per answer (specs/005-nodemcu-port).
    ap.add_argument("--timeout", type=float, default=180.0, help="seconds per answer")
    a = ap.parse_args()
    cases = json.loads(Path(a.golden).read_text(encoding="utf-8"))["cases"]
    if a.tcp:
        host, port = a.tcp.rsplit(":", 1)
        dev = Device(link=TcpLink(host, int(port), connect_timeout=30))
        dev.drain(1.0)
        dev.type("\r")
        dev.read_until(PROMPT, timeout=120)
    else:
        dev = Device(a.port, timeout=a.timeout)
        dev.reset()
    dev.command("/trace aus")  # plain answers (specs/002-observability)
    dev.command("/modus gierig")
    fails = 0
    for i, c in enumerate(cases):
        dev.command(f"/max {c['max']}")
        got = dev.ask(c["prompt"], a.char_delay)
        want = c.get("printed", c["text"])
        if got != want:
            fails += 1
            print(f"MISMATCH case {i}: {c['prompt']!r}\n  board: {got!r}\n  ref:   {want!r}")
    dev.close()
    print(f"device parity: {len(cases)} cases, {fails} mismatches")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
