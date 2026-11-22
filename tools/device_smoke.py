#!/usr/bin/env python3
"""On-device smoke test for User Story 1 (SC-001, SC-002, SC-003).

Types demo prompts at human speed (100 ms per character, SC-001 measures the first answer
character after Enter), checks answers and the /info timings. One extra prompt is sent at once
("paste") and its latency is reported separately (informational).

    uv run python ../tools/device_smoke.py --port /dev/ttyUSB0 [--board nodemcu|esp32]
        [--prompts data/demo_prompts.tsv]

Thresholds per board: nodemcu (default, specs/005-nodemcu-port SC-003) first character <= 2000 ms
and >= 5 chars/s; esp32 (legacy, spec 001) <= 1000 ms and >= 10 chars/s.
"""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from devlib import Device  # noqa: E402

LIMITS = {"nodemcu": (2000, 5.0), "esp32": (1000, 10.0)}  # (first char ms, chars/s)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", required=True)
    ap.add_argument("--board", choices=sorted(LIMITS), default="nodemcu")
    ap.add_argument("--prompts", default=str(Path(__file__).parents[1] / "training/data/demo_prompts.tsv"))
    ap.add_argument("-n", type=int, default=5)
    ap.add_argument("--char-delay", type=float, default=0.1)
    a = ap.parse_args()
    max_ms, min_cps = LIMITS[a.board]

    sys.path.insert(0, str(Path(__file__).parents[1] / "training/src"))
    from ultratiny.evaluate import is_correct

    with open(a.prompts, encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f, delimiter="\t", quoting=csv.QUOTE_NONE))[: a.n]
    dev = Device(a.port)
    banner = dev.reset()
    print(banner.strip())
    ok = "Funk: aus" in banner and "Format v1" in banner
    dev.command("/modus gierig")
    worst_ms, slowest = 0, 1e9
    for r in rows:
        ans = dev.ask(r["prompt"], a.char_delay)
        info = dev.info()
        good = is_correct(ans, r["expected"])
        ok &= good
        worst_ms = max(worst_ms, info.get("first_char_ms", 10**9))
        slowest = min(slowest, info.get("chars_per_s", 0.0))
        print(f"{'OK ' if good else 'BAD'} {r['prompt']!r} -> {ans!r} "
              f"({info.get('first_char_ms')} ms, {info.get('chars_per_s')} Z/s)")  # fmt: skip
    print(f"first char (typed): worst {worst_ms} ms (<= {max_ms}) "
          f"{'OK' if worst_ms <= max_ms else 'FAIL'}")  # fmt: skip
    print(f"speed: slowest {slowest} chars/s (>= {min_cps}) "
          f"{'OK' if slowest >= min_cps else 'FAIL'}")  # fmt: skip
    ok &= worst_ms <= max_ms and slowest >= min_cps
    dev.ask(rows[0]["prompt"], 0.0)
    paste = dev.info()
    print(f"(info) pasted prompt: first char after {paste.get('first_char_ms')} ms")
    dev.close()
    print("PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
