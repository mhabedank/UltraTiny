#!/usr/bin/env python3
"""Budget report (constitution Principle I, data-model.md BudgetReport).

Standard library only, so it also runs inside the ESP-IDF CI container.

    python tools/budget_report.py --model models/nodemcu.utny [--board nodemcu|esp32]
        [--pio-build firmware-nodemcu/.pio/build/nodemcuv2] [--idf-build firmware/build]
        [--facts models/chemie.utki]
        [--json out.json]

Board profiles: specs/005-nodemcu-port/data-model.md "Board budget profile" and
contracts/budget-report.md. Default board: nodemcu (constitution v2.0.0); esp32 is legacy.
Fails (exit 1) when any budget has less than 10% headroom, the model's arena does not fit the
firmware's arena buffer, or (nodemcu) firmware area + model area exceed the mapped flash window.
"""

from __future__ import annotations

import argparse
import json
import struct
import subprocess
import sys
from pathlib import Path

HEADROOM = 0.10

# data-model.md "Board budget profile". nodemcu: keep in sync with firmware-nodemcu/include/layout.h
# and ld/eagle.flash.4m.ultratiny.ld; esp32: firmware/partitions.csv and firmware/main/main.c.
PROFILES: dict[str, dict] = {
    "nodemcu": {
        "model_max": 0xA8000,  # model area 0x58000-0xFFFFF (672 KB)
        "arena_max": 40 * 1024,  # constitution v2.0.0 default
        "firmware_arena": 36 * 1024,  # UT_ARENA_MAX in firmware-nodemcu/include/layout.h
        "firmware_max": 0x58000,  # firmware area 0x0-0x57FFF (352 KB)
        "mapped_window": 1024 * 1024,  # ESP8266 maps only the first 1 MB of flash
        "dram_total": 80 * 1024,
        "facts_max": 0x10000,  # fact table area 0x100000-0x10FFFF (specs/006), outside the window
    },
    "esp32": {
        "model_max": 2 * 1024 * 1024,  # model partition
        "arena_max": 128 * 1024,
        "firmware_arena": 96 * 1024,  # UT_ARENA_MAX in firmware/main/main.c
        "firmware_max": None,  # factory partition, read from firmware/partitions.csv
        "mapped_window": None,
        "dram_total": None,
        "facts_max": None,
    },
}
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


def elf_dram_bytes(elf: Path) -> int | None:
    """Static DRAM of an ESP8266 ELF: .data + .rodata + .bss (all placed in DRAM by the
    Arduino core's linker script). Parses the ELF32 section headers with the stdlib only."""
    try:
        d = elf.read_bytes()
    except OSError:
        return None
    if d[:4] != b"\x7fELF" or d[4] != 1:
        return None
    e_shoff, = struct.unpack_from("<I", d, 0x20)
    e_shentsize, e_shnum, e_shstrndx = struct.unpack_from("<HHH", d, 0x2E)
    sh = [struct.unpack_from("<IIIIII", d, e_shoff + i * e_shentsize) for i in range(e_shnum)]
    str_off = sh[e_shstrndx][4]

    def name(off: int) -> str:
        end = d.index(b"\0", str_off + off)
        return d[str_off + off : end].decode()

    return sum(s[5] for s in sh if name(s[0]) in (".data", ".rodata", ".bss"))


def pio_sizes(build: Path) -> dict:
    out: dict = {}
    fw = build / "firmware.bin"
    if fw.exists():
        out["app_bytes"] = fw.stat().st_size
    dram = elf_dram_bytes(build / "firmware.elf")
    if dram is not None:
        out["static_dram_bytes"] = dram
        out["static_dram_total"] = PROFILES["nodemcu"]["dram_total"]
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--model", required=True, type=Path)
    ap.add_argument("--board", choices=sorted(PROFILES), default="nodemcu")
    ap.add_argument("--pio-build", type=Path, help="PlatformIO build dir (nodemcu firmware)")
    ap.add_argument("--idf-build", type=Path, help="ESP-IDF build dir (legacy esp32 firmware)")
    ap.add_argument("--facts", type=Path, help="UTKI knowledge image (specs/006, specs/008)")
    ap.add_argument("--json", type=Path)
    a = ap.parse_args()
    prof = PROFILES[a.board]

    h = read_header(a.model)
    arena = arena_size(h)
    rows = [
        ("model_bytes", h["file_bytes"], prof["model_max"]),
        ("arena_bytes", arena, prof["arena_max"]),
        ("arena_vs_firmware_buffer", arena, prof["firmware_arena"]),
    ]
    report = {"board": a.board, "model": str(a.model), "n_params": h["n_params"]}
    if a.pio_build:
        s = pio_sizes(a.pio_build)
        report.update(s)
        if "app_bytes" in s:
            rows.append(("app_bytes", s["app_bytes"], prof["firmware_max"]))
    if a.idf_build:
        s = idf_sizes(a.idf_build)
        report.update(s)
        if "app_bytes" in s:
            rows.append(("app_bytes", s["app_bytes"], factory_partition_size()))
    if a.facts:
        if not prof["facts_max"]:
            raise SystemExit(f"board {a.board} has no knowledge image area")
        if a.facts.read_bytes()[:4] != b"UTKI":
            raise SystemExit(f"{a.facts}: not a UTKI knowledge image")
        report["facts"] = str(a.facts)
        rows.append(("facts_bytes", a.facts.stat().st_size, prof["facts_max"]))
    if prof["mapped_window"]:
        areas = prof["firmware_max"] + prof["model_max"]
        rows.append(("mapped_window", areas, prof["mapped_window"]))

    ok = True
    print(f"Budget report for {a.model} ({h['n_params']} parameters), board {a.board}")
    print(f"{'item':28s} {'used':>10s} {'budget':>10s} {'use':>6s}  status")
    for name, used, budget in rows:
        frac = used / budget
        # The arena must merely fit the firmware buffer and the two flash areas must fit the
        # mapped window; real budgets need >= 10% headroom.
        exact = name in ("arena_vs_firmware_buffer", "mapped_window")
        limit = 1.0 if exact else 1 - HEADROOM
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
