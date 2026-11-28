#!/usr/bin/env python3
"""Knowledge image check on the board (specs/008-wissens-compiler FR-014, SC-005).

Sends every golden query case (`ut knowledge cases`) as `/wissen <view> <key>` with `/trace an`,
compares the printed answer byte for byte with the Python reference and reports the lookup time
the console measured (max and median, target <= 50 ms per query).

    uv run python ../tools/device_knowledge.py --port /dev/ttyUSB0 --cases ../models/chemie_cases.tsv
    uv run python ../tools/device_knowledge.py --cases ../models/chemie_cases.tsv \
        --exec "../build/utiny-host --model ../models/nodemcu.utny --facts ../models/chemie.utki --console"

Exit 0 when every case is identical and the slowest lookup is within --max-ms.
"""

from __future__ import annotations

import argparse
import csv
import re
import shlex
import statistics
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from devlib import PROMPT, Device, ExecLink  # noqa: E402

TIMING = re.compile(r"\r\nwissen: (\w+) (\d+) us")


def read_cases(path: Path) -> list[dict[str, str]]:
    with open(path, encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f, delimiter="\t", quoting=csv.QUOTE_NONE))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("--port")
    src.add_argument("--exec", dest="exec_cmd", help="host console command (utiny-host ... --console)")
    ap.add_argument("--cases", required=True)
    ap.add_argument("--max-ms", type=float, default=50.0)
    ap.add_argument("--timeout", type=float, default=30.0)
    a = ap.parse_args()
    cases = read_cases(Path(a.cases))
    if a.exec_cmd:
        dev = Device(link=ExecLink(shlex.split(a.exec_cmd)), timeout=a.timeout)
        dev.read_until(PROMPT)
    else:
        dev = Device(a.port, timeout=a.timeout)
        dev.reset()
    info = dev.info()
    print(f"board: Wissen: {info.get('facts', '?')}")
    dev.command("/trace an")
    fails, times = 0, []
    for i, c in enumerate(cases, 1):
        raw = dev.command(f"/wissen {c['view']} {c['key']}")
        body = raw.split("\r\n", 1)[1] if "\r\n" in raw else raw
        body = body[: -len(PROMPT)] if body.endswith(PROMPT) else body
        m = TIMING.search("\r\n" + body)
        answer = body[: m.start() - 2] if m and m.start() >= 2 else body.split("\r\n")[0]
        outcome = m.group(1) if m else "?"
        if m:
            times.append(int(m.group(2)) / 1000.0)
        if answer != c["answer"] or outcome != c["outcome"]:
            fails += 1
            print(f"case {i} ({c['view']} {c['key']}): got {outcome} {answer!r}, "
                  f"want {c['outcome']} {c['answer']!r}")  # fmt: skip
    dev.command("/trace aus")
    dev.close()
    worst = max(times) if times else float("nan")
    med = statistics.median(times) if times else float("nan")
    print(f"knowledge: {len(cases)} cases, {fails} different; lookup ms median {med:.2f}, "
          f"max {worst:.2f} (target <= {a.max_ms:g})")  # fmt: skip
    return 0 if fails == 0 and times and worst <= a.max_ms else 1


if __name__ == "__main__":
    raise SystemExit(main())
