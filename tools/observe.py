#!/usr/bin/env python3
"""Observability viewer for UltraTiny (specs/002-observability/contracts/observability.md).

Connects to the console, switches on `/trace json`, sends prompts and shows per answer:
the answer with every character coloured by the model's probability (green = sure, red =
unsure), timings, the least certain positions with their alternatives, the stage profile and
the system values from `/stats` (heap, stack, CPU load per core, arena).

    make observe                                         # QEMU + viewer, demo prompts
    uv run python ../tools/observe.py --qemu --demo 5    # same, from training/
    uv run python ../tools/observe.py --port /dev/ttyUSB0 "Wer bist du?"
    uv run python ../tools/observe.py --tcp localhost:5555          # running QEMU
    uv run python ../tools/observe.py --host --demo --log out.jsonl  # PC runtime, no device

Without prompts and without --demo it asks interactively (lines starting with "/" are sent
as console commands). `--log FILE` writes every event as JSON lines.
"""

from __future__ import annotations

import argparse
import contextlib
import json
import os
import shlex
import signal
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from devlib import PROMPT, Device, ExecLink, SerialLink, TcpLink  # noqa: E402

REPO = Path(__file__).resolve().parents[1]
EVENT_PREFIX = "@ut "


# ---------------------------------------------------------------- parsing (pure functions)


def split_events(text: str) -> tuple[str, list[dict]]:
    """Splits console output into human text and the parsed `@ut {...}` events."""
    human, events = [], []
    for line in text.split("\r\n"):
        if line.startswith(EVENT_PREFIX):
            try:
                events.append(json.loads(line[len(EVENT_PREFIX) :]))
            except json.JSONDecodeError:
                human.append(line)
        else:
            human.append(line)
    return "\r\n".join(human), events


def parse_answer(raw: str) -> dict:
    """`raw` = output after the echoed question up to (not incl.) the prompt."""
    text, events = split_events(raw)
    answer = text.split("\r\n", 1)[0]
    tokens = [e for e in events if e.get("type") == "token"]
    summary = next((e for e in events if e.get("type") == "answer"), None)
    return {"answer": answer, "tokens": tokens, "summary": summary, "events": events}


# ---------------------------------------------------------------- rendering


class Style:
    def __init__(self, color: bool):
        self.color = color

    def __call__(self, code: str, s: str) -> str:
        return f"\x1b[{code}m{s}\x1b[0m" if self.color else s

    def prob(self, p: float, s: str) -> str:
        """Red (p=0) -> yellow (0.5) -> green (1)."""
        if not self.color:
            return s
        p = min(max(p, 0.0), 1.0)
        r = 255 if p < 0.5 else int(255 * (1 - p) * 2)
        g = int(255 * p * 2) if p < 0.5 else 255
        return f"\x1b[38;2;{r};{g};60m{s}\x1b[0m"


def show_char(ch: str) -> str:
    return "␣" if ch == " " else ch


def fmt_kb(b: int | None) -> str:
    return "?" if b is None else f"{b / 1024:.1f} KB"


def bar(frac: float, width: int = 24) -> str:
    n = round(frac * width * 2)
    return "█" * (n // 2) + ("▌" if n % 2 else "") + " " * (width - n // 2 - n % 2)


def render_answer(st: Style, res: dict, expected: str | None) -> list[str]:
    out = []
    tok = [t for t in res["tokens"] if not t.get("stop")]
    if tok:
        line = "".join(st.prob(t["p"], t["ch"]) for t in tok)
    else:
        line = res["answer"]
    out.append("  " + line)
    if expected is not None:
        ok = res["answer"] == expected
        out.append(
            "  " + (st("32", "✓ wie erwartet") if ok else st("31", f"✗ erwartet: {expected}"))
        )
    s = res["summary"]
    if not s:
        return out
    out.append(
        st("2", "  ") + f"{s['n']} Zeichen · Ende {s['end']} · Prefill {s['prefill']} Token · "
        f"erstes Zeichen {s['first_ms']:.1f} ms · gesamt {s['total_ms']:.0f} ms · "
        f"{s['cps']:.1f} Zeichen/s · ms/Zeichen Ø {s['ms_avg']:.1f} "
        f"(min {s['ms_min']:.1f}, max {s['ms_max']:.1f})"
    )
    steps = res["tokens"]
    if steps:
        worst = steps[s["p_min_i"]] if 0 <= s["p_min_i"] < len(steps) else None
        txt = f"  Sicherheit: Ø p {s['p_avg']:.3f} · Ø Entropie {s['h_avg']:.3f} bit"
        if worst:
            txt += f" · min p {s['p_min']:.3f} bei '{show_char(worst['ch'])}' (Pos {worst['pos']})"
        txt += f" · Kontext {s['ctx_used']}/{s['ctx_len']}"
        out.append(txt)
        unsure = sorted(steps, key=lambda t: t["p"])[:3]
        unsure = [t for t in unsure if t["p"] < 0.95]
        for t in unsure:
            alts = ", ".join(
                f"'{show_char(c)}' {p:.3f}" for c, p in t["top"] if c != t["ch"] and p >= 0.0005
            )
            out.append(
                "    "
                + st.prob(t["p"], f"'{show_char(t['ch'])}' {t['p']:.3f}")
                + f" an Pos {t['pos']}, H {t['h']:.2f} bit"
                + (f" – Alternativen: {alts}" if alts else "")
            )
    prof = s.get("prof_us") or {}
    total = sum(prof.values())
    if total:
        out.append(f"  Profil ({total / 1000:.1f} ms Rechenzeit):")
        for name, us in sorted(prof.items(), key=lambda kv: -kv[1]):
            frac = us / total
            out.append(
                f"    {name:6s} {st('36', bar(frac))} {frac * 100:5.1f}%  {us / 1000:8.2f} ms"
            )
    return out


def render_sys(sys_ev: dict) -> str:
    """Compact one-line view of a `sys` event; unknown values (null) are left out."""
    g = sys_ev.get
    parts = []
    if g("heap_free") is not None:
        parts.append(
            f"Heap {fmt_kb(g('heap_free'))} frei (min {fmt_kb(g('heap_min'))}, "
            f"Block {fmt_kb(g('heap_largest'))})"
        )
    if g("stack_free") is not None:
        parts.append(f"Stack frei {fmt_kb(g('stack_free'))}")
    cpu = g("cpu_load") or []
    if any(v is not None for v in cpu):
        parts.append("CPU " + " ".join(f"K{i} {v}%" for i, v in enumerate(cpu) if v is not None))
    if g("arena_need") is not None:
        buf = g("arena_buf") or 0
        parts.append(f"Arena {fmt_kb(g('arena_need'))}" + (f"/{fmt_kb(buf)}" if buf else ""))
    if g("uptime_ms") is not None:
        parts.append(f"Laufzeit {g('uptime_ms') / 1000:.0f} s")
    return "  System: " + " · ".join(parts)


# ---------------------------------------------------------------- session


class Session:
    def __init__(self, dev: Device, style: Style, log, stats_each: bool):
        self.dev = dev
        self.st = style
        self.log = log
        self.stats_each = stats_each

    def emit(self, ev: dict, **extra) -> None:
        if self.log:
            self.log.write(json.dumps({**ev, **extra, "ts": round(time.time(), 3)}) + "\n")
            self.log.flush()

    def command(self, cmd: str) -> str:
        raw = self.dev.command(cmd)
        body = raw.split("\r\n", 1)[1] if "\r\n" in raw else ""
        return body[: -len(PROMPT)] if body.endswith(PROMPT) else body

    def stats(self) -> tuple[str, dict | None]:
        text, events = split_events(self.command("/stats"))
        sys_ev = next((e for e in events if e.get("type") == "sys"), None)
        if sys_ev:
            self.emit(sys_ev)
        return text, sys_ev

    def ask(self, prompt: str, expected: str | None = None) -> dict:
        print(self.st("1", f"❯ {prompt}"))
        res = parse_answer(self.dev.ask(prompt))
        for ev in res["events"]:
            self.emit(ev, prompt=prompt)
        rec = {"type": "result", "prompt": prompt, "answer": res["answer"]}
        if expected is not None:
            rec |= {"expected": expected, "match": res["answer"] == expected}
        self.emit(rec)
        for line in render_answer(self.st, res, expected):
            print(line)
        if self.stats_each:
            _, sys_ev = self.stats()
            if sys_ev:
                print(self.st("2", render_sys(sys_ev)))
        print()
        return res


def git_rev() -> str | None:
    try:
        r = subprocess.run(
            ["git", "-C", str(REPO), "rev-parse", "--short", "HEAD"],
            capture_output=True, text=True, timeout=5, check=True,
        )  # fmt: skip
        return r.stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return None


def load_demo(n: int | None) -> list[tuple[str, str | None]]:
    rows = []
    path = REPO / "training/data/demo_prompts.tsv"
    for line in path.read_text(encoding="utf-8").splitlines()[1:]:
        if "\t" in line:
            p, e = line.split("\t", 1)
            rows.append((p, e))
    return rows[:n] if n else rows


def start_qemu(model: Path, port: int) -> subprocess.Popen:
    env = dict(os.environ, UT_QEMU_TCP=str(port))
    return subprocess.Popen(
        [str(REPO / "tools/qemu_run.sh"), str(model)], env=env, start_new_session=True
    )


def connect_qemu(proc: subprocess.Popen, port: int, timeout: float) -> TcpLink:
    end = time.time() + timeout
    while time.time() < end:
        if proc.poll() is not None:
            raise SystemExit(f"qemu_run.sh beendet (Code {proc.returncode})")
        try:
            return TcpLink("localhost", port, connect_timeout=0.5)
        except OSError:
            time.sleep(1)
    raise SystemExit("QEMU nicht erreichbar (Timeout)")


def stop_qemu(proc: subprocess.Popen) -> None:
    if proc.poll() is None:
        with contextlib.suppress(ProcessLookupError):
            os.killpg(proc.pid, signal.SIGTERM)
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            os.killpg(proc.pid, signal.SIGKILL)


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("--port", help="serial port of a real board")
    src.add_argument("--tcp", metavar="HOST:PORT", help="console on TCP (QEMU with UT_QEMU_TCP)")
    src.add_argument("--qemu", action="store_true", help="start QEMU via tools/qemu_run.sh")
    src.add_argument("--host", action="store_true", help="PC runtime: build/utiny-host --console")
    src.add_argument("--exec", metavar="CMD", help="any command with the console on stdin/stdout")
    ap.add_argument("prompts", nargs="*", help="questions to ask")
    demo_help = "use training/data/demo_prompts.tsv (first N) and compare answers"
    ap.add_argument("--demo", nargs="?", const=0, type=int, metavar="N", help=demo_help)
    ap.add_argument("--model", type=Path, default=REPO / "models/starter.utny")
    ap.add_argument("--qemu-port", type=int, default=5555)
    ap.add_argument("--max", type=int, help="send /max N first")
    ap.add_argument("--log", type=Path, help="write all events as JSON lines")
    ap.add_argument("--no-stats", action="store_true", help="no /stats after every answer")
    ap.add_argument("--no-color", action="store_true")
    ap.add_argument("--timeout", type=float, default=300.0, help="seconds per answer")
    a = ap.parse_args()

    color = not a.no_color and sys.stdout.isatty() and "NO_COLOR" not in os.environ
    st = Style(color)
    qemu = None
    boot_wait = True
    try:
        if a.port:
            link, boot_wait = SerialLink(a.port), False
        elif a.tcp:
            host, port = a.tcp.rsplit(":", 1)
            link = TcpLink(host, int(port), connect_timeout=30)
        elif a.qemu:
            qemu = start_qemu(a.model.resolve(), a.qemu_port)
            link = connect_qemu(qemu, a.qemu_port, timeout=1800)
        elif a.host:
            exe = REPO / "build/utiny-host"
            if not exe.exists():
                raise SystemExit("build/utiny-host fehlt: make test-runtime")
            link = ExecLink([str(exe), "--model", str(a.model), "--console"])
        else:
            link = ExecLink(shlex.split(a.exec))
        dev = Device(link=link, timeout=a.timeout)
        if boot_wait:
            banner = dev.read_until(PROMPT, timeout=180)
        else:
            dev.drain(0.3)
            dev.type("\r")
            banner = dev.read_until(PROMPT, timeout=10)
        banner = banner[banner.find("UltraTiny v") :] if "UltraTiny v" in banner else banner
        print(st("2", banner.strip("\r\n> ").replace("\r\n", "\n")))
        if color:
            scale = "".join(st.prob(i / 10, "█") for i in range(11))
            print(st("2", "Farbe = Wahrscheinlichkeit des Zeichens: 0 ") + scale + st("2", " 1"))
        print()

        log = None
        if a.log:
            a.log.parent.mkdir(parents=True, exist_ok=True)
            log = a.log.open("w", encoding="utf-8")
        sess = Session(dev, st, log, stats_each=not a.no_stats)
        source = next(k for k in ("port", "tcp", "qemu", "host", "exec") if getattr(a, k))
        sess.emit(
            {
                "type": "session",
                "source": source,
                "model": str(a.model) if source in ("qemu", "host") else None,
                "git": git_rev(),
                "banner": banner.strip("\r\n> ").split("\r\n"),
            }
        )
        sess.command("/trace json")
        if a.max:
            sess.command(f"/max {a.max}")

        items: list[tuple[str, str | None]] = [(p, None) for p in a.prompts]
        if a.demo is not None:
            items += load_demo(a.demo)
        matches = 0
        if items:
            for p, e in items:
                res = sess.ask(p, e)
                matches += e is not None and res["answer"] == e
            n_exp = sum(e is not None for _, e in items)
            if n_exp:
                print(st("1", f"Demo: {matches}/{n_exp} Antworten wie erwartet"))
        else:
            print("Interaktiv: Frage eingeben (/befehl wird direkt gesendet, leer = Ende).")
            while True:
                try:
                    line = input("frage> ").strip()
                except EOFError:
                    break
                if not line:
                    break
                if line.startswith("/"):
                    text, events = split_events(sess.command(line))
                    for ev in events:
                        sess.emit(ev)
                    print(text.replace("\r\n", "\n"))
                else:
                    sess.ask(line)
        text, _ = sess.stats()
        print(st("1", "/stats"))
        print(text.replace("\r\n", "\n"))
        sess.command("/trace aus")  # leave the console as other tools expect it
        if log:
            log.close()
            print(st("2", f"Log: {a.log}"))
        dev.close()
    except KeyboardInterrupt:
        print("\nabgebrochen")
        return 130
    finally:
        if qemu:
            stop_qemu(qemu)
    return 0


if __name__ == "__main__":
    sys.exit(main())
