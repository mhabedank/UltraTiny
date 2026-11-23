"""Board measurement over the serial console (spec US4, research R8, contracts/cli.md).

Uses only console commands the firmware already has: /info (identity, first-character time),
/trace json (per-step times for T2/T3), /stats (arena and heap as JSON). Never flashes or erases.
The same code runs against `utiny-host --console` (devlib.ExecLink), so CI can test it without a
board.
"""

from __future__ import annotations

import datetime as dt
import json
import platform
import re
import shlex
import statistics
import struct
import sys
import time
from pathlib import Path

from . import RESULT_FORMAT, TOOL_VERSION
from .pc import Progress, default_out, git_commit, write_result
from .scoring import Scorer, kpi, not_measured
from .subject import load_subject
from .suite import REPO_ROOT, Item, Suite, SuiteError, load_suite

TYPED_DELAY = 0.1  # s per character, as tools/device_smoke.py (SC-001 of spec 005)
BANNER = "Sprachmodell offline auf dem Mikrocontroller"
PARITY_SAMPLE = 5


def devlib():
    sys.path.insert(0, str(REPO_ROOT / "tools"))
    import devlib as mod  # noqa: PLC0415

    return mod


def norm_answer(s: str) -> str:
    """CRLF -> LF, trailing spaces removed (the only normalisation before the parity compare)."""
    return "\n".join(line.rstrip() for line in s.replace("\r\n", "\n").split("\n")).strip()


# ---------------------------------------------------------------- console parsing


def parse_info(txt: str) -> dict:
    out: dict = {}
    if m := re.search(r"Parameter: (\d+) \| Datei: (\d+) Bytes \| Arena: (\d+) Bytes", txt):
        out.update(params=int(m.group(1)), size=int(m.group(2)), arena=int(m.group(3)))
    if m := re.search(r"Training: git (\S+), Datum (\S+)", txt):
        out.update(git=m.group(1).rstrip(","), date=m.group(2))
    if m := re.search(r"erstes Zeichen nach (\d+) ms, ([\d.]+) Zeichen/s", txt):
        out.update(first_ms=int(m.group(1)), cps=float(m.group(2)))
    if m := re.search(r"Faktentabelle: ([^\r\n]+)", txt):
        out["facts"] = m.group(1).strip()
        if m2 := re.search(r"data ([0-9a-f]{8})", out["facts"]):
            out["facts_sha4"] = m2.group(1)
    if m := re.search(r"Freier Heap: (\d+)", txt):
        out["free_heap"] = int(m.group(1))
    return out


def parse_ut(txt: str) -> list[dict]:
    out = []
    for line in txt.splitlines():
        line = line.strip()
        if line.startswith("@ut "):
            try:
                out.append(json.loads(line[4:]))
            except json.JSONDecodeError:
                pass
    return out


def split_answer(raw: str) -> tuple[str, list[dict]]:
    """Console output after Enter -> (answer text, @ut records)."""
    text = raw.replace("\r\n", "\n")
    lines = text.split("\n")
    ans = [ln for ln in lines if not ln.startswith("@ut ")]
    return "\n".join(ans).strip(), parse_ut(text)


def step_rates(records: list[dict], ctx_len: int) -> dict:
    """T2 over characters 2..n (no first-character wait), T3 over steps at pos >= 0.9 ctx."""
    steps = [r for r in records if r.get("type") == "token" and not r.get("stop")]
    out: dict = {}
    if len(steps) >= 2:
        us = sum(s["us"] for s in steps[1:])
        if us > 0:
            out["t2"] = (len(steps) - 1) * 1e6 / us
    late = [s for s in steps if s["pos"] >= 0.9 * ctx_len]
    if late:
        us = sum(s["us"] for s in late)
        if us > 0:
            out["t3"] = len(late) * 1e6 / us
            out["t3_steps"] = len(late)
            out["t3_us"] = us
    return out


def facts_sha4(path: Path | None) -> str | None:
    if path is None:
        return None
    data = Path(path).read_bytes()
    return f"{struct.unpack_from('<I', data, 52)[0]:08x}" if len(data) >= 56 else None


# ---------------------------------------------------------------- run


class BoardRun:
    def __init__(self, dev, suite: Suite, subject, log=print, has_reset: bool = False):
        self.dev, self.suite, self.subject, self.log = dev, suite, subject, log
        self.has_reset = has_reset
        self.events: list[dict] = []

    def command(self, cmd: str) -> str:
        return self.dev.command(cmd)

    def recover(self, item_id: str, kind: str, detail: str) -> None:
        self.events.append({"id": item_id, "event": kind, "detail": detail[-200:]})
        self.log(f"bench board: {kind} at {item_id}: {detail[-120:]!r}")
        try:
            if self.has_reset:
                self.dev.reset()
            else:
                self.dev.drain(1.0)
                self.dev.type("\r")
                self.dev.read_until(self.dev_prompt(), timeout=30)
            self.command("/trace json")
        except Exception as e:  # noqa: BLE001 - keep measuring the rest
            self.events.append({"id": item_id, "event": "recover_failed", "detail": str(e)[:200]})

    def dev_prompt(self) -> str:
        return devlib().PROMPT

    def ask(self, it: Item, typed: bool) -> dict:
        rec: dict = {"set": it.set, "id": it.id, "question": it.question, "typed": typed}
        try:
            q = self.subject.console_text(it.question)  # the console would drop the rest
            raw = self.dev.ask(q, TYPED_DELAY if typed else 0.0)
        except TimeoutError as e:
            self.recover(it.id, "hang", str(e))
            rec["error"] = "hang"
            return rec
        if BANNER in raw:
            self.recover(it.id, "reset", raw)
            rec["error"] = "reset"
            return rec
        answer, records = split_answer(raw)
        info = parse_info(self.command("/info"))
        rec.update(answer=answer, first_ms=info.get("first_ms"), cps=info.get("cps"))
        rec.update(step_rates(records, self.subject.ctx_len))
        return rec

    def stats(self) -> dict:
        recs = parse_ut(self.command("/stats"))
        return next((r for r in recs if r.get("type") == "sys"), {})


def sample_items(suite: Suite, mode: str) -> tuple[list[Item], int, set[str]]:
    bs = suite.board_sample
    unseen = suite.sets.get("unseen", [])
    t3_ids = set(bs.get("t3", []))
    items = [it for it in unseen if it.id not in t3_ids][: int(bs.get("unseen", 30))]
    ka = suite.sets.get("kurzarbeit", [])
    n_ka = bs.get("kurzarbeit", "all")
    items += ka if n_ka == "all" else ka[: int(n_ka)]
    items += [it for it in unseen if it.id in t3_ids]
    typed = int(bs.get("typed", 15))
    if mode == "parity":
        items = (items or suite.sets.get("s3", []))[:PARITY_SAMPLE]
        typed = 0
    if not items:  # suites without question sets yet: use the reference facts
        from .pc import fact_items

        items = fact_items(suite)[:PARITY_SAMPLE]
    return items, typed, t3_ids


def identity_problems(info: dict, ident: dict, know_sha4: str | None) -> list[str]:
    probs = []
    for k in ("params", "size"):
        if info.get(k) != ident.get(k):
            probs.append(f"{k}: board {info.get(k)}, model file {ident.get(k)}")
    if ident.get("git") and info.get("git") not in (None, "?") and info["git"] != ident["git"]:
        probs.append(f"git: board {info['git']}, model file {ident['git']}")
    if know_sha4 and info.get("facts_sha4") != know_sha4:
        probs.append(f"fact table: board {info.get('facts', 'none')}, file data {know_sha4}")
    return probs


def run_board(
    suite: Suite,
    model: Path,
    facts: Path | None,
    dev,
    label: str | None,
    mode: str = "all",
    has_reset: bool = False,
    board_name: str = "",
    firmware: Path | None = None,
    log=print,
) -> dict:
    subject = load_subject(model, facts)
    ident = subject.identity()
    run = BoardRun(dev, suite, subject, log, has_reset)
    boot = dev.reset() if has_reset else dev.read_until(devlib().PROMPT, timeout=30)
    run.command("/trace aus")
    info = parse_info(run.command("/info"))
    probs = identity_problems(info, ident, facts_sha4(facts))
    if probs:
        raise SuiteError("board runs a different model or fact table:\n  " + "\n  ".join(probs))
    run.command("/trace json")
    sys_start = run.stats()
    items, n_typed, t3_ids = sample_items(suite, mode)
    scorer = Scorer(suite)
    log(f"bench board: {len(items)} questions ({n_typed} typed), {len(t3_ids)} T3 prompts")
    records = []
    prog = Progress("Board-Fragen", len(items), log)
    for i, it in enumerate(items):
        rec = run.ask(it, typed=False)
        if "answer" in rec:
            pc_answer, _ = subject.answer(it.question)
            rec["parity"] = norm_answer(rec["answer"]) == norm_answer(pc_answer)
            if not rec["parity"]:
                rec["pc_answer"] = pc_answer
            rec["class"] = scorer.score(it, rec["answer"])["class"]
        rec["kind"] = it.kind
        records.append(rec)
        if i < n_typed and it.id not in t3_ids:
            t = run.ask(it, typed=True)
            if t.get("first_ms") is not None:
                rec["first_ms_typed"] = t["first_ms"]
        prog.step()
    sys_end = run.stats()
    run.command("/trace aus")

    def med(xs):
        return round(statistics.median(xs), 1) if xs else None

    typed_ms = [r["first_ms_typed"] for r in records if r.get("first_ms_typed") is not None]
    pasted_ms = [r["first_ms"] for r in records if r.get("first_ms") is not None]
    t2 = [r["t2"] for r in records if "t2" in r]
    t3_steps = sum(r.get("t3_steps", 0) for r in records if r["id"] in t3_ids or not t3_ids)
    t3_us = sum(r.get("t3_us", 0) for r in records if r["id"] in t3_ids or not t3_ids)
    kpis: dict = {}
    if typed_ms or pasted_ms:
        main_ms = typed_ms or pasted_ms
        kpis["T1"] = kpi(
            med(main_ms),
            len(main_ms),
            {
                "typed": {"median": med(typed_ms), "max": max(typed_ms) if typed_ms else None},
                "pasted": {"median": med(pasted_ms), "max": max(pasted_ms) if pasted_ms else None},
                "info_cps_median": med([r["cps"] for r in records if r.get("cps")]),
            },
        )
    else:
        kpis["T1"] = not_measured("no answers")
    kpis["T2"] = kpi(med(t2), len(t2)) if t2 else not_measured("no answers with 2+ characters")
    kpis["T3"] = (
        kpi(round(t3_steps * 1e6 / t3_us, 2), t3_steps)
        if t3_us
        else not_measured("no steps at >= 90 % of the context")
    )
    if "arena_need" in sys_start:
        kpis["R1"] = kpi(
            sys_start["arena_need"],
            None,
            {
                "arena_need": sys_start.get("arena_need"),
                "arena_buf": sys_start.get("arena_buf"),
                "heap_free_boot": sys_start.get("heap_free"),
                "heap_min": sys_end.get("heap_min"),
                "heap_free_end": sys_end.get("heap_free"),
            },
        )
    else:
        kpis["R1"] = not_measured("no /stats JSON")
    for k in ("F1", "F2", "F3", "F4", "F5", "F6", "R2", "R3", "R4", "S1", "S2", "S3"):
        kpis[k] = not_measured("PC KPI")
    fw = Path(firmware).stat().st_size if firmware else None
    complete = not run.events and all("answer" in r for r in records)
    return {
        "format": RESULT_FORMAT,
        "kind": "board",
        "label": label or ident.get("name") or Path(model).stem,
        "complete": complete,
        "suite": suite.info(),
        "model": ident,
        "knowledge": subject.knowledge(),
        "board": {
            "name": board_name,
            "boot": boot.strip().splitlines()[:3] if boot else [],
            "info": {k: v for k, v in info.items() if k != "raw"},
            "firmware_size": fw,
            "mode": mode,
        },
        "env": {
            "commit": git_commit(),
            "date": dt.date.today().isoformat(),
            "host": platform.node(),
            "tool": TOOL_VERSION,
        },
        "overlap": {},
        "kpis": dict(sorted(kpis.items())),
        "items": records,
        "events": run.events,
    }


def main(a) -> int:
    """`tools/bench.py board` (contracts/cli.md)."""
    try:
        suite = load_suite(a.suite)
    except SuiteError as e:
        print(f"bench: {e}", file=sys.stderr)
        return 2
    dl = devlib()
    if a.port:
        dev = dl.Device(a.port, timeout=a.timeout)
        name, has_reset = f"serial {a.port}", True
    else:
        dev = dl.Device(link=dl.ExecLink(shlex.split(a.exec_cmd)), timeout=a.timeout)
        name, has_reset = "host (utiny-host --console)", False
    t0 = time.time()
    try:
        result = run_board(
            suite,
            Path(a.model),
            Path(a.facts) if a.facts else None,
            dev,
            a.label,
            a.sample,
            has_reset,
            name,
            Path(a.firmware) if a.firmware else None,
        )
    except SuiteError as e:
        print(f"bench: {e}", file=sys.stderr)
        return 2
    finally:
        dev.close()
    result["env"]["seconds"] = round(time.time() - t0, 1)
    out = Path(a.out) if a.out else default_out(result, REPO_ROOT / "bench" / "results")
    write_result(result, out)
    bad = [r for r in result["items"] if r.get("parity") is False]
    for k in ("T1", "T2", "T3", "R1"):
        v = result["kpis"][k]
        print(f"  {k}  {v.get('value') if v['status'] == 'measured' else v.get('reason')}")
    print(
        f"bench board: {len(result['items'])} questions, {len(bad)} parity mismatches, "
        f"{len(result['events'])} events -> {out} ({result['env']['seconds']} s)"
    )
    for r in bad[:10]:
        print(f"  parity {r['id']}: board {r['answer']!r} != pc {r.get('pc_answer')!r}")
    return 1 if bad else 0
