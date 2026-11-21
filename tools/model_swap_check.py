#!/usr/bin/env python3
"""User Story 3 on the board: swap models without rebuilding firmware; corrupt model is
rejected without a reboot loop.

    uv run python ../tools/model_swap_check.py --port /dev/ttyUSB0 \
        --model-a ../models/starter.utny --model-b runs/v1/model.utny

Flashes via `make flash-model` (needs ESP-IDF's parttool.py on PATH).
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from devlib import Device  # noqa: E402

REPO = Path(__file__).resolve().parents[1]


def flash(port: str, model: Path) -> None:
    subprocess.run(["make", "-C", str(REPO), "flash-model", f"PORT={port}", f"MODEL={model}"],
                   check=True)  # fmt: skip


def banner(port: str) -> str:
    dev = Device(port)
    try:
        return dev.reset()
    finally:
        dev.close()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", required=True)
    ap.add_argument("--model-a", required=True, type=Path)
    ap.add_argument("--model-b", required=True, type=Path)
    a = ap.parse_args()
    ok = True
    for m in (a.model_a, a.model_b):
        flash(a.port, m)
        b = banner(a.port)
        good = "Modell:" in b and "FEHLER" not in b
        ok &= good
        print(f"{'OK ' if good else 'BAD'} {m}: {b.strip().splitlines()[1] if good else b!r}")

    data = bytearray(a.model_a.read_bytes())
    data[len(data) // 2] ^= 0xFF  # corrupt payload, keeps magic so flash-model accepts it
    with tempfile.NamedTemporaryFile(suffix=".utny", delete=False) as f:
        f.write(data)
    flash(a.port, Path(f.name))
    dev = Device(a.port)
    b = dev.reset()
    good = "FEHLER: Modell ung" in b
    time.sleep(30)
    later = dev.drain(1.0)
    no_loop = "UltraTiny v" not in later  # no second boot banner
    info = dev.command("/info")
    dev.close()
    print(f"{'OK ' if good else 'BAD'} corrupt model rejected: {b.strip()!r}")
    print(f"{'OK ' if no_loop else 'BAD'} no reboot loop within 30 s")
    print(f"{'OK ' if 'Modellfehler' in info else 'BAD'} /info in HALT_ERROR")
    ok &= good and no_loop and "Modellfehler" in info
    flash(a.port, a.model_a)  # restore
    print("PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
