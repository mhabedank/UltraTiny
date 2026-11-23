"""Demo runner: the same demo script on two boards or images, answers side by side (FR-022).

A demo script is a TSV with `id` and `question` (10-15 rows, data-model.md "Demo script").
With one board, run the script once per firmware image (`single`) and `merge` the two runs.
"""

from __future__ import annotations

import json
from pathlib import Path

from .board import BANNER, devlib, parse_info, split_answer
from .suite import SuiteError, read_tsv


def load_script(path: Path) -> list[dict]:
    rows = read_tsv(path)
    if not 10 <= len(rows) <= 15:
        raise SuiteError(f"{path}: a demo script has 10-15 questions, found {len(rows)}")
    return [{"id": r["id"], "question": r["question"]} for r in rows]


def run_single(dev, script: list[dict], label: str, has_reset: bool = False) -> dict:
    dev.reset() if has_reset else dev.read_until(devlib().PROMPT, timeout=30)
    info = parse_info(dev.command("/info"))
    dev.command("/trace aus")
    rows = []
    for q in script:
        try:
            raw = dev.ask(q["question"])
        except TimeoutError:
            rows.append({**q, "answer": "(keine Antwort: Zeitüberschreitung)", "first_ms": None})
            continue
        ans, _ = split_answer(raw)
        if BANNER in raw:
            ans = "(Board neu gestartet)"
        first = parse_info(dev.command("/info")).get("first_ms")
        rows.append({**q, "answer": ans, "first_ms": first})
    return {"label": label, "info": {k: v for k, v in info.items() if k != "raw"}, "rows": rows}


def merge_markdown(a: dict, b: dict, title: str = "") -> str:
    def esc(s):
        return str(s).replace("|", "\\|").replace("\n", " ")

    out = [
        f"# Demo {esc(title)}".rstrip(),
        "",
        f"A = **{esc(a['label'])}**, B = **{esc(b['label'])}**",
        "",
        f"| # | Frage | Antwort A ({esc(a['label'])}) | Antwort B ({esc(b['label'])}) "
        "| erstes Zeichen A (ms) | erstes Zeichen B (ms) |",
        "|---|---|---|---|---|---|",
    ]
    rb = {r["id"]: r for r in b["rows"]}
    for i, r in enumerate(a["rows"], 1):
        o = rb.get(r["id"], {})
        out.append(
            f"| {i} | {esc(r['question'])} | {esc(r['answer'])} | {esc(o.get('answer', '–'))} | "
            f"{r['first_ms'] if r['first_ms'] is not None else '–'} | "
            f"{o.get('first_ms') if o.get('first_ms') is not None else '–'} |"
        )
    return "\n".join(out) + "\n"


def save_run(run: dict, path: Path) -> None:
    Path(path).write_text(json.dumps(run, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def load_run(path: Path) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))
