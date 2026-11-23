"""PC measurement run, result file, S3 rating sheet and --check (spec US1/US6, research R11-R13)."""

from __future__ import annotations

import csv
import datetime as dt
import hashlib
import json
import multiprocessing as mp
import platform
import subprocess
from pathlib import Path

from . import RESULT_FORMAT, TOOL_VERSION
from .lm import s1 as s1_kpi
from .lm import s2 as s2_kpi
from .scoring import Scorer, fact_kpis, kpi, not_measured
from .subject import load_subject
from .suite import REPO_ROOT, Item, Suite, norm_q

QUALITY_KPIS = ("F1", "F2", "F3", "F4", "F5", "F6", "S1", "S2")
SET_ORDER = ("unseen", "unknown", "offtopic", "kurzarbeit", "s3", "facts")


# ---------------------------------------------------------------- questions


def fact_items(suite: Suite) -> list[Item]:
    """F6: one canonical question per reference fact (object x property)."""
    out = []
    for (obj, prop), f in sorted(suite.facts.items()):
        tpl = suite.properties[prop].canonical
        if not tpl:
            continue
        q = tpl.format(name=f.object_name, key=f.object)
        out.append(Item("facts", f"{prop}:{obj}", "fact", q, [(prop, obj)], []))
    return out


def all_items(suite: Suite, only: set[str] | None = None) -> list[Item]:
    items = []
    for role in SET_ORDER:
        if only and role not in only:
            continue
        items += fact_items(suite) if role == "facts" else suite.sets.get(role, [])
    return items


# ---------------------------------------------------------------- answering (optionally parallel)

_W: dict = {}


def _init(model, facts):
    _W["s"] = load_subject(model, facts)


def _ask(q: str) -> tuple[str, bool]:
    return _W["s"].answer(q)


def answer_all(subject, questions: list[str], model, facts, jobs: int) -> list[tuple[str, bool]]:
    if jobs <= 1 or len(questions) < 2 * jobs:
        return [subject.answer(q) for q in questions]
    ctx = mp.get_context("spawn")
    with ctx.Pool(
        jobs, initializer=_init, initargs=(str(model), str(facts) if facts else None)
    ) as p:
        return p.map(_ask, questions, chunksize=8)


# ---------------------------------------------------------------- run


def git_commit() -> str:
    try:
        return subprocess.run(
            ["git", "rev-parse", "--short=12", "HEAD"],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return "unknown"


def read_train_questions(path: Path) -> set[str]:
    out = set()
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        q = line.split("\t", 1)[0]
        if q:
            out.add(norm_q(q))
    return out


def run_pc(
    suite: Suite,
    model: Path,
    facts: Path | None = None,
    label: str | None = None,
    jobs: int = 1,
    only: set[str] | None = None,
    train_data: Path | None = None,
    host: str | None = None,
    log=print,
) -> dict:
    subject = load_subject(model, facts)
    scorer = Scorer(suite)
    items = all_items(suite, only)
    log(f"bench: {len(items)} questions, {len(suite.s1)} S1 sections, {len(suite.s2)} S2 probes")
    answers = answer_all(subject, [it.question for it in items], model, facts, jobs)
    records = []
    for it, (ans, too_long) in zip(items, answers, strict=True):
        sc = scorer.score(it, ans) if not too_long else {"class": "no_answer", "ok": False}
        rec = {
            "set": it.set,
            "id": it.id,
            "kind": it.kind,
            "type": it.type,
            "question": it.question,
            "answer": ans,
            "class": sc["class"],
            "ok": sc["ok"],
        }
        if too_long:
            rec["too_long"] = True
        records.append(rec)

    kpis = fact_kpis(records)
    ident = subject.identity()
    know = subject.knowledge()
    kpis["R2"] = kpi(ident["size"])
    kpis["R3"] = kpi(know["size"] if know else 0)
    f6 = kpis["F6"].get("value")
    kpis["R4"] = (
        kpi(round((kpis["R2"]["value"] + kpis["R3"]["value"]) / f6, 1))
        if f6
        else not_measured("F6 is 0 or not measured")
    )
    if only is None or "s1" in only:
        log("bench: S1 ...")
        kpis["S1"] = s1_kpi(subject, suite.s1)
    else:
        kpis["S1"] = not_measured("skipped (--only)")
    if only is None or "s2" in only:
        log("bench: S2 ...")
        kpis["S2"] = s2_kpi(subject, suite.s2, suite.s2_cfg)
    else:
        kpis["S2"] = not_measured("skipped (--only)")
    for k in ("T1", "T2", "T3", "R1"):
        kpis[k] = not_measured("board KPI")
    kpis["S3"] = not_measured("not rated")
    for k in suite.not_applicable:
        kpis[k] = {"value": None, "status": "not_applicable"}

    overlap: dict = {}
    if train_data is not None:
        train = read_train_questions(train_data)
        for role, its in sorted(suite.sets.items()):
            overlap[role] = sum(norm_q(it.question) in train for it in its)
    else:
        overlap = {role: "unknown" for role in sorted(suite.sets)}

    return {
        "format": RESULT_FORMAT,
        "kind": "pc",
        "label": label or ident.get("name") or Path(model).stem,
        "complete": only is None,
        "suite": suite.info(),
        "model": ident,
        "knowledge": know,
        "board": None,
        "env": {
            "commit": git_commit(),
            "date": dt.date.today().isoformat(),
            "host": host or platform.node(),
            "tool": TOOL_VERSION,
            "jobs": jobs,
        },
        "overlap": overlap,
        "kpis": dict(sorted(kpis.items())),
        "items": records,
        "events": [],
    }


def default_out(result: dict, results_dir: Path) -> Path:
    date = result["env"]["date"].replace("-", "")
    return results_dir / f"{result['label']}_{result['suite']['name']}_{result['kind']}_{date}.json"


def write_result(result: dict, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def read_result(path: Path) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


# ---------------------------------------------------------------- S3 rating sheet (FR-015)


def sheet_path(result_path: Path) -> Path:
    p = Path(result_path)
    return p.with_name(p.stem + ".s3.tsv")


def answer_sha(answer: str) -> str:
    return hashlib.sha256(answer.encode("utf-8")).hexdigest()[:16]


def read_ratings(path: Path) -> dict[str, tuple[str, str]]:
    """id -> (answer_sha256, grammar_ok) (data-model.md Rating sheet)."""
    if not path.exists():
        return {}
    with open(path, encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f, delimiter="\t", quoting=csv.QUOTE_NONE))
    return {
        r["id"]: (r.get("answer_sha256", ""), (r.get("grammar_ok") or "").strip().lower())
        for r in rows
    }


def s3_from_ratings(result: dict, ratings: dict[str, tuple[str, str]]) -> dict:
    rated = []
    for r in result["items"]:
        if r["set"] != "s3":
            continue
        sha, ok = ratings.get(r["id"], ("", ""))
        if sha == answer_sha(r["answer"]) and ok in ("ja", "nein"):
            rated.append(ok == "ja")
    n = sum(1 for r in result["items"] if r["set"] == "s3")
    if not n:
        return not_measured("no S3 prompts")
    if not rated:
        return not_measured("not rated")
    out = kpi(round(100.0 * sum(rated) / len(rated), 1), len(rated))
    if len(rated) < n:
        out["detail"] = {"unrated": n - len(rated)}
    return out


def write_sheet(result: dict, path: Path) -> dict:
    """Write the rating sheet; keep ratings whose answer is unchanged; return the S3 KPI."""
    old = read_ratings(path)
    rows = []
    for r in result["items"]:
        if r["set"] != "s3":
            continue
        sha = answer_sha(r["answer"])
        prev_sha, ok = old.get(r["id"], ("", ""))
        rows.append(
            (
                r["id"],
                sha,
                r["answer"].replace("\t", " ").replace("\n", " "),
                ok if prev_sha == sha else "",
            )
        )
    if rows:
        with open(path, "w", encoding="utf-8", newline="") as f:
            f.write("id\tanswer_sha256\tanswer\tgrammar_ok\n")
            for row in rows:
                f.write("\t".join(row) + "\n")
    return s3_from_ratings(result, read_ratings(path))


# ---------------------------------------------------------------- --check (FR-024)


def check(result: dict, ref: dict) -> list[str]:
    """Differences in quality KPIs, S3 answers and per-question classes (identity/env ignored)."""
    diffs = []
    for k in QUALITY_KPIS:
        a, b = ref["kpis"].get(k, {}), result["kpis"].get(k, {})
        if (a.get("value"), a.get("detail")) != (b.get("value"), b.get("detail")):
            diffs.append(f"KPI {k}: committed {a.get('value')!r}, now {b.get('value')!r}")
    if ref.get("suite", {}).get("files") != result.get("suite", {}).get("files"):
        diffs.append("suite files differ from the committed result (re-pinned test set?)")
    old = {(r["set"], r["id"]): r for r in ref["items"]}
    new = {(r["set"], r["id"]): r for r in result["items"]}
    for key in sorted(set(old) | set(new)):
        a, b = old.get(key), new.get(key)
        if a is None or b is None:
            diffs.append(f"{key[0]} {key[1]}: {'new' if a is None else 'missing'} question")
        elif a["class"] != b["class"] or (key[0] == "s3" and a["answer"] != b["answer"]):
            diffs.append(
                f"{key[0]} {key[1]} {b['question']!r}: {a['class']} -> {b['class']} "
                f"(answer {b['answer']!r})"
            )
    return diffs


def summary_lines(result: dict) -> list[str]:
    out = []
    for k, v in result["kpis"].items():
        val = v.get("value")
        extra = f" (n={v['n']})" if "n" in v else ""
        if v.get("status") != "measured":
            val = v.get("status") + (f": {v['reason']}" if v.get("reason") else "")
        out.append(f"  {k:3} {val}{extra}")
    return out
