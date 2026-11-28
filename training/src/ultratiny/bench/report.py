"""Comparison report: verdicts, budget, changed answers; Markdown and HTML (research R9, R10).

Results with the same `label` are seeds of one step; PC and board results of a label are merged
(board KPIs T1-T3 and R1 come from the board result). The first label is the baseline unless one
is named. A change counts as better or worse only when it exceeds the KPI's noise threshold from the
suite and, with several seeds, twice the larger seed spread (spec FR-018).
"""

from __future__ import annotations

import datetime as dt
import html
import importlib.util
import statistics
from dataclasses import dataclass, field
from pathlib import Path

from .pc import read_ratings, s3_from_ratings, sheet_path
from .suite import KPI_IDS, REPO_ROOT

UP = {"F1", "F3", "F5", "F6", "F7", "T2", "T3", "S2", "S3"}  # larger is better; others: smaller
GROUPS = {
    "F": "Faktenqualität",
    "T": "Tempo",
    "R": "Ressourcen",
    "S": "Sprache",
}
NAMES = {
    "F1": "richtig, ungesehene Formulierungen (%)",
    "F2": "falsche Fakten (%)",
    "F3": "richtig abgewiesen (%)",
    "F4": "fälschlich abgewiesen (%)",
    "F5": "Kurzarbeit (%)",
    "F6": "beantwortbare Fakten",
    "F7": "beantwortbare Fakten im Wissens-Image",
    "T1": "erstes Zeichen, getippt (ms)",
    "T2": "Zeichen/s",
    "T3": "Zeichen/s bei vollem Kontext",
    "R1": "Arena (B)",
    "R2": "Flash Modell (B)",
    "R3": "Flash Wissen (B)",
    "R4": "Bytes pro Fakt",
    "R5": "Bytes pro Fakt im Wissens-Image",
    "S1": "Bit pro Zeichen",
    "S2": "nutzbarer Kontext (Zeichen)",
    "S3": "Grammatik ok (%)",
}
# test sets each KPI reads: a different version makes the KPI "not comparable" (FR-004)
KPI_SETS = {
    "F1": ("unseen",),
    "F2": ("unseen", "kurzarbeit"),
    "F3": ("unknown", "offtopic"),
    "F4": ("unseen",),
    "F5": ("kurzarbeit",),
    "F6": ("facts",),
    "R4": ("facts",),
    "S1": ("s1",),
    "S2": ("s2",),
    "S3": ("s3",),
}
BOARD_KPIS = ("T1", "T2", "T3", "R1")
ROADMAP_ARENA_MAX = 35 * 1024  # specs/ROADMAP.md rule 4


def budget_profile() -> tuple[dict, float]:
    spec = importlib.util.spec_from_file_location(
        "budget_report", REPO_ROOT / "tools" / "budget_report.py"
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.PROFILES["nodemcu"], mod.HEADROOM


# ---------------------------------------------------------------- model


@dataclass
class Step:
    label: str
    pc: list[dict] = field(default_factory=list)
    board: list[dict] = field(default_factory=list)

    @property
    def suite(self) -> dict:
        r = (self.pc or self.board)[0]
        return r["suite"]

    def results_for(self, k: str) -> list[dict]:
        if k in BOARD_KPIS:
            return self.board
        return self.pc or self.board

    def values(self, k: str) -> tuple[list[float], str]:
        vals, status = [], "not_measured"
        for r in self.results_for(k):
            v = r["kpis"].get(k, {})
            if v.get("status") == "not_applicable":
                return [], "not_applicable"
            if v.get("status") == "measured" and isinstance(v.get("value"), (int, float)):
                vals.append(float(v["value"]))
                status = "measured"
        return vals, status

    def stat(self, k: str) -> tuple[float | None, float | None, int, str]:
        vals, status = self.values(k)
        if not vals:
            return None, None, 0, status
        mean = statistics.fmean(vals)
        spread = statistics.stdev(vals) if len(vals) >= 2 else None
        return mean, spread, len(vals), status

    def first(self) -> dict:
        return (self.pc or self.board)[0]

    def parity_broken(self) -> bool:
        return any(any(i.get("parity") is False for i in r["items"]) for r in self.board)

    def incomplete(self) -> bool:
        return any(not r.get("complete", True) for r in self.pc + self.board)


def load_steps(results: list[tuple[Path, dict]]) -> list[Step]:
    steps: dict[str, Step] = {}
    for path, r in results:
        r = dict(r)
        sheet = sheet_path(path)
        if r.get("kind") == "pc" and sheet.exists():
            kp = dict(r["kpis"])
            kp["S3"] = s3_from_ratings(r, read_ratings(sheet))
            r["kpis"] = kp
        st = steps.setdefault(r["label"], Step(r["label"]))
        (st.board if r.get("kind") == "board" else st.pc).append(r)
    return list(steps.values())


def threshold(suite_thresholds: dict, k: str, base: float | None) -> tuple[float, str]:
    """Absolute threshold and its display text (FR-018)."""
    t = suite_thresholds.get(k, 0.0)
    if isinstance(t, str):
        s = t.strip()
        if s == "exact":
            return 0.0, "exakt"
        if s.endswith("%"):
            rel = float(s[:-1]) / 100.0
            return abs(base or 0.0) * rel, s
        if s.endswith("step"):
            return float(s.split()[0]), s
        return float(s), s
    return float(t), f"{t:g}"


def s2_steps(step: Step, value: float | None) -> float | None:
    if value is None:
        return None
    dists = sorted(int(d) for d in step.suite.get("s2_distances", []))
    return float(dists.index(int(value))) if int(value) in dists else None


def comparable(a: Step, b: Step, k: str) -> bool:
    if k not in KPI_SETS:
        return True
    sa, sb = a.suite, b.suite
    if sa.get("name") != sb.get("name"):
        return False
    va, vb = sa.get("sets", {}), sb.get("sets", {})
    return all(va.get(s) == vb.get(s) for s in KPI_SETS[k])


def verdict(base: Step, step: Step, k: str) -> tuple[str, float | None, str]:
    """(verdict, delta, threshold text)."""
    ma, sa, na, sta = base.stat(k)
    mb, sb, nb, stb = step.stat(k)
    if "not_applicable" in (sta, stb):
        return "nicht anwendbar", None, ""
    if ma is None or mb is None:
        return "nicht gemessen", None, ""
    if not comparable(base, step, k):
        return "nicht vergleichbar", None, ""
    thr, thr_txt = threshold(step.suite.get("thresholds") or {}, k, ma)
    delta = mb - ma
    if k == "S2":
        ia, ib = s2_steps(base, ma), s2_steps(step, mb)
        size = abs(ib - ia) if ia is not None and ib is not None else abs(delta)
    else:
        size = abs(delta)
    if thr_txt == "exakt":
        changed = delta != 0
    else:
        changed = size > thr
        spreads = [s for s in (sa, sb) if s is not None]
        if spreads and (na >= 2 or nb >= 2):
            changed = changed and abs(delta) > 2 * max(spreads)
    if not changed:
        return "unverändert", delta, thr_txt
    better = (delta > 0) == (k in UP)
    return ("besser" if better else "schlechter"), delta, thr_txt


# ---------------------------------------------------------------- budget


def budget_rows(step: Step) -> list[dict]:
    prof, head = budget_profile()
    keep = 1.0 - head
    r = step.first()
    model = r.get("model") or {}
    rows = []

    def row(name, value, limit, note=""):
        if value is None:
            rows.append({"name": name, "value": None, "limit": limit, "ok": None, "note": note})
        else:
            rows.append(
                {"name": name, "value": value, "limit": limit, "ok": value <= limit, "note": note}
            )

    row("Modell (Flash)", model.get("size"), int(prof["model_max"] * keep), "Modellbereich − 10 %")
    arena_limit = int(min(ROADMAP_ARENA_MAX, prof["arena_max"] * keep, prof["firmware_arena"]))
    board_arena = None
    for b in step.board:
        board_arena = (b["kpis"].get("R1", {}).get("detail") or {}).get("arena_need")
    row(
        "Arena (RAM)",
        board_arena if board_arena is not None else model.get("arena"),
        arena_limit,
        "≤ 35 KB und ≥ 10 % Reserve",
    )
    know = r.get("knowledge")
    if know:
        row(
            "Wissen (Flash)",
            know.get("size"),
            int(prof["facts_max"] * keep),
            "Faktenbereich − 10 %",
        )
    fw = None
    for b in step.board:
        fw = (b.get("board") or {}).get("firmware_size") or fw
    if fw is not None:
        row("Firmware", fw, int(prof["firmware_max"] * keep), "Firmwarebereich − 10 %")
    return rows


# ---------------------------------------------------------------- report model


def build(
    results: list[tuple[Path, dict]], baseline: str | None = None, predecessor: str | None = None
) -> dict:
    steps = load_steps(results)
    if not steps:
        raise ValueError("no results")
    order = [s.label for s in steps]
    base_label = baseline or order[0]
    by = {s.label: s for s in steps}
    if base_label not in by:
        raise ValueError(f"baseline label {base_label!r} not in the results")
    if predecessor and predecessor not in by:
        raise ValueError(f"predecessor label {predecessor!r} not in the results")
    base = by[base_label]
    others = [s for s in steps if s.label != base_label]
    rows = []
    for k in KPI_IDS:
        row = {"kpi": k, "name": NAMES[k], "up": k in UP, "cells": {}}
        for s in steps:
            mean, spread, n, status = s.stat(k)
            row["cells"][s.label] = {"mean": mean, "spread": spread, "n": n, "status": status}
        row["vs_base"] = {s.label: verdict(base, s, k) for s in others}
        if predecessor:
            pred = by[predecessor]
            row["vs_pred"] = {
                s.label: verdict(pred, s, k) for s in others if s.label != predecessor
            }
        rows.append(row)
    summary = {}
    for s in others:
        counts = {"besser": 0, "schlechter": 0, "unverändert": 0}
        for row in rows:
            v = row["vs_base"][s.label][0]
            if v in counts:
                counts[v] += 1
        if s.suite.get("name") != base.suite.get("name"):
            counts["note"] = "andere Suite, nur Ressourcen vergleichbar"
        summary[s.label] = counts
    budgets = {s.label: budget_rows(s) for s in steps}
    changed = {s.label: changed_answers(base, s) for s in others}
    return {
        "labels": order,
        "baseline": base_label,
        "predecessor": predecessor,
        "steps": {
            s.label: {
                "suite": s.suite.get("name"),
                "suite_version": s.suite.get("version"),
                "seeds": max(len(s.pc), 1),
                "board": bool(s.board),
                "incomplete": s.incomplete(),
                "parity_broken": s.parity_broken(),
                "overlap": s.first().get("overlap", {}),
                "model": (s.first().get("model") or {}).get("sha256", "")[:12],
                "date": (s.first().get("env") or {}).get("date"),
            }
            for s in steps
        },
        "rows": rows,
        "summary": summary,
        "budget": budgets,
        "budget_broken": any(r["ok"] is False for b in budgets.values() for r in b),
        "parity_broken": any(s.parity_broken() for s in steps),
        "changed": changed,
        "curves": {
            s.label: (s.first()["kpis"].get("S2", {}).get("detail") or {}).get("curve", {})
            for s in steps
        },
        "by_type": {
            s.label: (s.first()["kpis"].get("F1", {}).get("detail") or {}).get("by_type", {})
            for s in steps
        },
    }


def changed_answers(base: Step, step: Step) -> list[dict]:
    if not (base.pc and step.pc) or base.suite.get("name") != step.suite.get("name"):
        return []
    a = {(i["set"], i["id"]): i for i in base.pc[0]["items"]}
    out = []
    for i in step.pc[0]["items"]:
        o = a.get((i["set"], i["id"]))
        if o is not None and o["class"] != i["class"]:
            out.append(
                {
                    "set": i["set"],
                    "id": i["id"],
                    "question": i["question"],
                    "before": o["class"],
                    "after": i["class"],
                    "answer_before": o["answer"],
                    "answer_after": i["answer"],
                }
            )
    return out


# ---------------------------------------------------------------- rendering helpers


def fmt(v: float | None, k: str) -> str:
    if v is None:
        return "–"
    if k in ("S1",):
        return f"{v:.3f}"
    if k in ("T2", "T3") or k.startswith("F") and k != "F6":
        return f"{v:.1f}"
    if abs(v - round(v)) < 1e-9:
        return f"{int(round(v)):,}".replace(",", ".")
    return f"{v:.1f}"


def cell_text(c: dict, k: str) -> str:
    st = c["status"]
    if st == "not_applicable":
        return "n. a."
    if c["mean"] is None:
        return "nicht gemessen"
    t = fmt(c["mean"], k)
    if c["spread"] is not None:
        t += f" ± {fmt(c['spread'], k)}"
    return t


def delta_text(v: tuple[str, float | None, str], k: str) -> str:
    verdict_, delta, _thr = v
    if delta is None:
        return verdict_
    sign = "+" if delta > 0 else ""
    return f"{sign}{fmt(delta, k)} ({verdict_})"


CLASS_DE = {
    "correct": "richtig",
    "wrong_fact": "falscher Fakt",
    "refused": "abgewiesen",
    "no_answer": "keine Antwort",
}


# ---------------------------------------------------------------- Markdown


def to_markdown(rep: dict, generated: str | None = None) -> str:
    gen = generated or dt.datetime.now().strftime("%Y-%m-%d %H:%M")
    L = rep["labels"]
    out = ["# Benchmark-Bericht", "", f"_erzeugt {gen}_", ""]
    out.append("| Schritt | Rolle | Suite | Seeds | Board | Datum | Modell |")
    out.append("|---|---|---|---|---|---|---|")
    for lab in L:
        s = rep["steps"][lab]
        role = (
            "Baseline"
            if lab == rep["baseline"]
            else ("Vorgänger" if lab == rep["predecessor"] else "Schritt")
        )
        out.append(
            f"| {lab} | {role} | {s['suite']} v{s['suite_version']} | {s['seeds']} | "
            f"{'ja' if s['board'] else 'nein'} | {s['date']} | `{s['model']}` |"
        )
    out += ["", "## Zusammenfassung", ""]
    if rep["budget_broken"]:
        out.append("- **budget broken**: mindestens ein Budget ist gerissen (siehe Budget).")
    if rep["parity_broken"]:
        out.append("- **parity broken**: Board und PC antworten unterschiedlich.")
    for lab, c in rep["summary"].items():
        out.append(
            f"- {lab} gegen {rep['baseline']}: {c['besser']} besser, {c['schlechter']} schlechter, "
            f"{c['unverändert']} unverändert" + (f" ({c['note']})" if c.get("note") else "")
        )
    if not rep["summary"]:
        out.append("- nur ein Schritt, kein Vergleich")
    out += ["", "## Kennzahlen", ""]
    head = (
        "| Gruppe | KPI | Richtung | "
        + " | ".join(L)
        + " | "
        + " | ".join(f"Δ {lab} zu {rep['baseline']}" for lab in L if lab != rep["baseline"])
    )
    if rep["predecessor"]:
        head += " | " + " | ".join(
            f"Δ {lab} zu {rep['predecessor']}"
            for lab in L
            if lab not in (rep["baseline"], rep["predecessor"])
        )
    head += " | Schwelle |"
    cols = head.count("|") - 1
    out += [head, "|" + "---|" * cols]
    for row in rep["rows"]:
        k = row["kpi"]
        cells = [cell_text(row["cells"][lab], k) for lab in L]
        deltas = [delta_text(row["vs_base"][lab], k) for lab in L if lab != rep["baseline"]]
        if rep["predecessor"]:
            deltas += [delta_text(v, k) for v in row.get("vs_pred", {}).values()]
        thr = next((v[2] for v in row["vs_base"].values() if v[2]), "")
        out.append(
            f"| {GROUPS[k[0]]} | **{k}** {row['name']} | {'↑' if row['up'] else '↓'} | "
            + " | ".join(cells + deltas)
            + f" | {thr} |"
        )
    out += ["", "## Budget", ""]
    out += [
        "| Schritt | Posten | Wert (B) | Grenze (B) | Status | Regel |",
        "|---|---|---|---|---|---|",
    ]
    for lab in L:
        for b in rep["budget"][lab]:
            st = "nicht gemessen" if b["ok"] is None else ("ok" if b["ok"] else "**gerissen**")
            out.append(
                f"| {lab} | {b['name']} | {fmt(b['value'], 'R2')} | {fmt(b['limit'], 'R2')} | "
                f"{st} | {b['note']} |"
            )
    if any(rep["changed"].values()):
        out += ["", "## Geänderte Antworten", ""]
        for lab, items in rep["changed"].items():
            if not items:
                continue
            out += [f"### {lab} gegen {rep['baseline']} ({len(items)})", ""]
            out += [
                "| Menge | ID | Frage | vorher | nachher | Antwort nachher |",
                "|---|---|---|---|---|---|",
            ]
            for i in items:
                out.append(
                    f"| {i['set']} | {i['id']} | {md_esc(i['question'])} | "
                    f"{CLASS_DE[i['before']]} | {CLASS_DE[i['after']]} | "
                    f"{md_esc(i['answer_after'])} |"
                )
    notes = []
    for lab in L:
        s = rep["steps"][lab]
        if s["incomplete"]:
            notes.append(f"- {lab}: unvollständiger Lauf (Teilmenge oder Board-Ausfälle).")
        ov = {k: v for k, v in s["overlap"].items() if v not in (0, "unknown")}
        if ov:
            notes.append(f"- {lab}: Testfragen in den Trainingsdaten gefunden: {ov}.")
    if notes:
        out += ["", "## Hinweise", ""] + notes
    return "\n".join(out) + "\n"


def md_esc(s: str) -> str:
    return s.replace("|", "\\|").replace("\n", " ")


# ---------------------------------------------------------------- HTML

CSS = """
:root{--bg:#fbfaf7;--fg:#1d1d1b;--muted:#6b6a65;--line:#e4e1d8;--card:#ffffff;
--good:#1f7a4d;--bad:#b3261e;--accent:#3b5bdb;--c0:#3b5bdb;--c1:#d9480f;--c2:#2b8a3e;--c3:#862e9c}
@media (prefers-color-scheme:dark){:root{--bg:#161614;--fg:#ecebe6;--muted:#a3a29b;--line:#34332f;
--card:#1f1f1c;--good:#69db9a;--bad:#ff8a80;--accent:#91a7ff;--c0:#91a7ff;--c1:#ffa94d;--c2:#8ce99a;
--c3:#e599f7}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--fg);
font:15px/1.5 system-ui,-apple-system,"Segoe UI",sans-serif}
main{max-width:1100px;margin:0 auto;padding:24px 16px 64px}h1{font-size:26px;margin:0 0 4px}
h2{font-size:19px;margin:32px 0 8px}.muted{color:var(--muted)}
.wrap{overflow-x:auto;border:1px solid var(--line);border-radius:8px;background:var(--card)}
table{border-collapse:collapse;width:100%;font-variant-numeric:tabular-nums}
th,td{padding:6px 10px;border-bottom:1px solid var(--line);text-align:left;vertical-align:top}
th{font-weight:600;font-size:13px;color:var(--muted)}td.n{text-align:right;white-space:nowrap}
.besser{color:var(--good);font-weight:600}.schlechter{color:var(--bad);font-weight:600}
.flag{display:inline-block;padding:2px 8px;border-radius:99px;border:1px solid var(--bad);
color:var(--bad);font-weight:600;margin-right:8px}.ok{color:var(--good)}.broken{color:var(--bad);font-weight:600}
svg text{fill:var(--muted);font-size:11px}svg .grid{stroke:var(--line)}
.legend span{margin-right:14px}
.sw{display:inline-block;width:10px;height:10px;border-radius:2px;margin-right:4px}
details{margin:8px 0}summary{cursor:pointer}
"""


def e(s) -> str:
    return html.escape(str(s))


def svg_curve(curves: dict[str, dict]) -> str:
    labs = [lab for lab, c in curves.items() if c]
    if not labs:
        return ""
    dists = sorted({int(d) for lab in labs for d in curves[lab]})
    w, h, pad = 640, 220, 40
    xs = {d: pad + i * (w - 2 * pad) / max(1, len(dists) - 1) for i, d in enumerate(dists)}

    def y(v):
        return h - pad - v * (h - 2 * pad)

    parts = [f'<svg viewBox="0 0 {w} {h}" width="100%" role="img" aria-label="S2-Kurve">']
    for v in (0, 0.5, 0.8, 1.0):
        parts.append(
            f'<line class="grid" x1="{pad}" x2="{w - pad}" y1="{y(v):.1f}" y2="{y(v):.1f}"/>'
        )
        parts.append(f'<text x="4" y="{y(v) + 4:.1f}">{int(v * 100)} %</text>')
    for d in dists:
        parts.append(f'<text x="{xs[d] - 8:.1f}" y="{h - 12}">{d}</text>')
    for i, lab in enumerate(labs):
        pts = " ".join(
            f"{xs[int(d)]:.1f},{y(v):.1f}"
            for d, v in sorted(curves[lab].items(), key=lambda t: int(t[0]))
        )
        parts.append(
            f'<polyline fill="none" stroke="var(--c{i % 4})" stroke-width="2" points="{pts}"/>'
        )
    parts.append("</svg>")
    legend = "".join(
        f'<span><i class="sw" style="background:var(--c{i % 4})"></i>{e(lab)}</span>'
        for i, lab in enumerate(labs)
    )
    return "".join(parts) + f'<div class="legend muted">{legend}</div>'


def svg_bars(by_type: dict[str, dict]) -> str:
    labs = [lab for lab, d in by_type.items() if d]
    if not labs:
        return ""
    types = sorted({t for lab in labs for t in by_type[lab]})
    bh, gap, left, w = 9, 6, 210, 640
    h = len(types) * (len(labs) * bh + gap) + 20
    parts = [f'<svg viewBox="0 0 {w} {h}" width="100%" role="img" aria-label="F1 je Frageart">']
    yv = 10
    for t in types:
        parts.append(f'<text x="0" y="{yv + bh}">{e(t)}</text>')
        for i, lab in enumerate(labs):
            v = by_type[lab].get(t)
            if v is not None:
                bw = (w - left - 40) * v / 100.0
                parts.append(
                    f'<rect x="{left}" y="{yv}" width="{bw:.1f}" height="{bh - 1}" rx="2" '
                    f'fill="var(--c{i % 4})"><title>{e(lab)}: {v} %</title></rect>'
                )
            yv += bh
        yv += gap
    parts.append("</svg>")
    return "".join(parts)


def to_html(rep: dict, generated: str | None = None) -> str:
    gen = generated or dt.datetime.now().strftime("%Y-%m-%d %H:%M")
    L = rep["labels"]
    o = [
        "<!doctype html><html lang='de'><head><meta charset='utf-8'>",
        "<meta name='viewport' content='width=device-width,initial-scale=1'>",
        f"<title>Benchmark-Bericht</title><style>{CSS}</style></head><body><main>",
        f"<h1>Benchmark-Bericht</h1><p class='muted'>erzeugt {e(gen)} · Baseline "
        f"<b>{e(rep['baseline'])}</b></p>",
    ]
    flags = ""
    if rep["budget_broken"]:
        flags += "<span class='flag'>budget broken</span>"
    if rep["parity_broken"]:
        flags += "<span class='flag'>parity broken</span>"
    o.append(f"<p>{flags}</p>" if flags else "")
    o.append(
        "<ul>"
        + "".join(
            f"<li>{e(lab)} gegen {e(rep['baseline'])}: "
            f"<span class='besser'>{c['besser']} besser</span>, "
            f"<span class='schlechter'>{c['schlechter']} schlechter</span>, "
            f"{c['unverändert']} unverändert"
            + (f" ({e(c['note'])})" if c.get("note") else "")
            + "</li>"
            for lab, c in rep["summary"].items()
        )
        + "</ul>"
    )
    o.append(
        "<h2>Schritte</h2><div class='wrap'><table><tr><th>Schritt</th><th>Suite</th>"
        "<th>Seeds</th><th>Board</th><th>Datum</th><th>Modell</th></tr>"
    )
    for lab in L:
        s = rep["steps"][lab]
        o.append(
            f"<tr><td>{e(lab)}</td><td>{e(s['suite'])} v{s['suite_version']}</td>"
            f"<td class='n'>{s['seeds']}</td><td>{'ja' if s['board'] else 'nein'}</td>"
            f"<td>{e(s['date'])}</td><td><code>{e(s['model'])}</code></td></tr>"
        )
    o.append("</table></div><h2>Kennzahlen</h2><div class='wrap'><table><tr><th>KPI</th><th></th>")
    o += [f"<th>{e(lab)}</th>" for lab in L]
    o += [f"<th>Δ {e(lab)}</th>" for lab in L if lab != rep["baseline"]]
    o.append("<th>Schwelle</th></tr>")
    group = ""
    for row in rep["rows"]:
        k = row["kpi"]
        if GROUPS[k[0]] != group:
            group = GROUPS[k[0]]
            o.append(f"<tr><th colspan='{3 + 2 * len(L)}'>{e(group)}</th></tr>")
        o.append(f"<tr><td><b>{k}</b> {e(row['name'])}</td><td>{'↑' if row['up'] else '↓'}</td>")
        o += [f"<td class='n'>{e(cell_text(row['cells'][lab], k))}</td>" for lab in L]
        for lab in L:
            if lab == rep["baseline"]:
                continue
            v = row["vs_base"][lab]
            o.append(f"<td class='n {v[0]}'>{e(delta_text(v, k))}</td>")
        thr = next((v[2] for v in row["vs_base"].values() if v[2]), "")
        o.append(f"<td>{e(thr)}</td></tr>")
    o.append(
        "</table></div><h2>Budget</h2><div class='wrap'><table><tr><th>Schritt</th>"
        "<th>Posten</th><th>Wert (B)</th><th>Grenze (B)</th><th>Status</th><th>Regel</th></tr>"
    )
    for lab in L:
        for b in rep["budget"][lab]:
            st = (
                "<span class='muted'>nicht gemessen</span>"
                if b["ok"] is None
                else (
                    "<span class='ok'>ok</span>"
                    if b["ok"]
                    else "<span class='broken'>gerissen</span>"
                )
            )
            o.append(
                f"<tr><td>{e(lab)}</td><td>{e(b['name'])}</td>"
                f"<td class='n'>{fmt(b['value'], 'R2')}</td>"
                f"<td class='n'>{fmt(b['limit'], 'R2')}</td><td>{st}</td>"
                f"<td>{e(b['note'])}</td></tr>"
            )
    o.append("</table></div>")
    curve = svg_curve(rep["curves"])
    if curve:
        o.append("<h2>S2: Merk-Test nach Abstand</h2>" + curve)
    bars = svg_bars(rep["by_type"])
    if bars:
        o.append("<h2>F1 je Frageart (%)</h2>" + bars)
    for lab, items in rep["changed"].items():
        if not items:
            continue
        o.append(
            f"<details><summary><b>Geänderte Antworten {e(lab)}</b> ({len(items)})</summary>"
            "<div class='wrap'><table><tr><th>ID</th><th>Frage</th><th>vorher</th><th>nachher</th>"
            "<th>Antwort nachher</th></tr>"
        )
        for i in items:
            o.append(
                f"<tr><td>{e(i['id'])}</td><td>{e(i['question'])}</td><td>{CLASS_DE[i['before']]}</td>"
                f"<td>{CLASS_DE[i['after']]}</td><td>{e(i['answer_after'])}</td></tr>"
            )
        o.append("</table></div></details>")
    o.append("</main></body></html>")
    return "\n".join(x for x in o if x) + "\n"
