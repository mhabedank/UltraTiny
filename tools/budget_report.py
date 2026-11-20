#!/usr/bin/env python3
"""Budget report (constitution Principle I, data-model.md BudgetReport).

Standard library only, so it also runs inside the ESP-IDF CI container.

    python tools/budget_report.py --model models/starter.utny [--idf-build firmware/build] [--json out.json]

Fails (exit 1) when any budget has less than 10% headroom.
"""

from __future__ import annotations

import argparse
import json
import struct
import subprocess
import sys
from pathlib import Path

MODEL_BUDGET = 2 * 1024 * 1024  # model partition (constitution: <= 2 MB)
ARENA_BUDGET = 128 * 1024  # inference RAM (constitution: <= 128 KB)
FIRMWARE_ARENA = 96 * 1024  # static arena in firmware/main/main.c (UT_ARENA_MAX)
HEADROOM = 0.10
REPO = Path(__file__).resolve().parents[1]


def read_header(path: Path) -> dict:
    data = path.read_bytes()
    if data[:4] != b"UTNY":
        raise SystemExit(f"{path}: not a UTNY model file")
    f = struct.unpack_from("<4s10Hf6I", data, 0)
    keys = ["magic", "version", "header_size", "vocab", "d_model", "n_layers", "n_heads",
            "n_kv_heads", "d_ff", "ctx_len", "flags", "eps", "a_off", "m_off", "t_off",
            "payload", "payload_crc", "n_params"]  # fmt: skip
    h = dict(zip(keys, f, strict=True))
    h["file_bytes"] = len(data)
    return h


def arena_size(h: dict) -> int:
    """Mirror of ut_arena_size() (runtime/src/model.c) and reference.arena_size()."""

    def a16(n: int) -> int:
        return (n + 15) & ~15

    hd = h["d_model"] // h["n_heads"]
    kvd = hd * h["n_kv_heads"]
    lt = h["n_layers"] * h["ctx_len"]
    d, ff = h["d_model"], h["d_ff"]
    s = 2 * a16(lt * kvd) + 2 * a16(4 * lt) + 5 * a16(4 * d) + 2 * a16(4 * kvd)
    s += a16(4 * ff) + a16(4 * h["vocab"]) + a16(4 * h["ctx_len"])
    s += a16(max(d, ff)) + a16(hd)
    return s


def factory_partition_size() -> int:
    for line in (REPO / "firmware/partitions.csv").read_text().splitlines():
        cols = [c.strip() for c in line.split(",")]
        if cols and cols[0] == "factory":
            return int(cols[4], 0)
    raise SystemExit("factory partition not found")


def idf_sizes(build: Path) -> dict:
    out: dict = {}
    bins = sorted(p for p in build.glob("*.bin") if p.name not in ("bootloader.bin",))
    app = [p for p in bins if p.name == "ultratiny.bin"] or bins
    if app:
        out["app_bytes"] = app[0].stat().st_size
    maps = list(build.glob("*.map"))
    if maps:
        try:
            r = subprocess.run(
                [sys.executable, "-m", "esp_idf_size", "--format", "json", str(maps[0])],
                capture_output=True, text=True, timeout=120, check=True,
            )  # fmt: skip
            j = json.loads(r.stdout)
            out["static_dram_bytes"] = j.get("used_dram")
            out["static_dram_total"] = j.get("dram_total")
        except (OSError, subprocess.SubprocessError, ValueError):
            out["static_dram_bytes"] = None  # esp_idf_size not available here
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--model", required=True, type=Path)
    ap.add_argument("--idf-build", type=Path)
    ap.add_argument("--json", type=Path)
    a = ap.parse_args()

    h = read_header(a.model)
    arena = arena_size(h)
    rows = [
        ("model_bytes", h["file_bytes"], MODEL_BUDGET),
        ("arena_bytes", arena, ARENA_BUDGET),
        ("arena_vs_firmware_buffer", arena, FIRMWARE_ARENA),
    ]
    report = {"model": str(a.model), "n_params": h["n_params"]}
    if a.idf_build:
        s = idf_sizes(a.idf_build)
        report.update(s)
        if "app_bytes" in s:
            rows.append(("app_bytes", s["app_bytes"], factory_partition_size()))

    ok = True
    print(f"Budget report for {a.model} ({h['n_params']} parameters)")
    print(f"{'item':28s} {'used':>10s} {'budget':>10s} {'use':>6s}  status")
    for name, used, budget in rows:
        frac = used / budget
        # The arena must merely fit the firmware buffer; real budgets need >= 10% headroom.
        limit = 1.0 if name == "arena_vs_firmware_buffer" else 1 - HEADROOM
        good = frac <= limit
        ok &= good
        report[name] = {"used": used, "budget": budget, "ok": good}
        print(f"{name:28s} {used:10d} {budget:10d} {frac:6.1%}  {'OK' if good else 'FAIL'}")
    if report.get("static_dram_bytes"):
        print(f"static DRAM: {report['static_dram_bytes']} / {report.get('static_dram_total')}")
    report["ok"] = ok
    if a.json:
        a.json.write_text(json.dumps(report, indent=2) + "\n")
    print("OK" if ok else "FAIL: budget headroom below 10% (constitution I)")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
