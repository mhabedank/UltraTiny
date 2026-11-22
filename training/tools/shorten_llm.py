#!/usr/bin/env python3
"""Propose <= 60-character curriculum explanations with a local LLM (specs/006, task T031).

Reads the long `frei` answers of data/facts/chemie_rlp_*.tsv and chemie_reaktionen.tsv, asks the
LLM (Ollama, e.g. on the DGX Spark) for short versions, and keeps the first proposal that passes
the automatic check (ultratiny.augment.check_short_explanation: length, alphabet, no new numbers
or formulas, key term present; table facts -> `to_fact`). The LLM never creates facts (FR-005).

Writes data/facts/chemie_kurz.tsv with `reviewed = no`. The user reviews the file in the pull
request and sets `reviewed = yes` per row (FR-008); datagen only trains reviewed rows.

    python3 tools/shorten_llm.py --host http://localhost:11434 --model qwen3.6:35b

Progress is cached in runs/augment_cache/ (resumes after an interruption).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tools"))
from augment_llm import LIST_SCHEMA, Ollama, cached, log, read_tsv, run_parallel  # noqa: E402

from ultratiny import factgen  # noqa: E402
from ultratiny.alphabet import Alphabet  # noqa: E402
from ultratiny.augment import SHORT_MAX, check_short_explanation, key_terms, sanitize  # noqa: E402
from ultratiny.config import load_config  # noqa: E402

AB = Alphabet()
SOURCES = ["chemie_rlp_a.tsv", "chemie_rlp_b.tsv", "chemie_rlp_c.tsv", "chemie_reaktionen.tsv"]
OUT = ROOT / "data" / "facts" / "chemie_kurz.tsv"
COLS = ["id", "questions", "answer", "keywords", "source", "check", "reviewed"]

PROMPT = """Du bist Chemielehrer (Klassen 7 bis 10). Kürze die folgende Antwort auf eine
Schülerfrage auf HÖCHSTENS {limit} Zeichen (inklusive Leerzeichen). Regeln:
- ein einziger vollständiger deutscher Satz, sachlich richtig, für Schüler verständlich
- nur Inhalte aus der Originalantwort, KEINE neuen Fakten, Zahlen oder Formeln
- der Begriff aus der Frage soll im Satz vorkommen
- keine Anführungszeichen, keine Aufzählung

Frage: {question}
Originalantwort: {answer}

Gib 3 verschiedene Vorschläge als JSON {{"items": [...]}} zurück."""


def fact_tokens() -> set[str]:
    cfg = load_config(ROOT / "configs" / "chemie-hybrid.toml")
    fs = factgen.build(cfg, ROOT)
    return {k for k, o in fs.objects.items() if o.kind != "element" or len(k) > 1}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)  # fmt: skip
    ap.add_argument("--host", default="http://localhost:11434")
    ap.add_argument("--model", default="qwen3.6:35b")
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--seed", type=int, default=1234)
    ap.add_argument("--limit", type=int, default=SHORT_MAX - 5, help="target length for the LLM")
    a = ap.parse_args()
    llm = Ollama(a.host, a.model, a.seed)
    tokens = fact_tokens()
    entries = []
    for name in SOURCES:
        for r in read_tsv(ROOT / "data" / "facts" / name):
            if r["relation"] == "frei":
                entries.append(r)
    log(f"{len(entries)} Erklärungen, Modell {llm.model}")

    def work(r: dict) -> tuple:
        qs = [q.strip() for q in r["subject"].split("|") if q.strip()]
        prompt = PROMPT.format(limit=a.limit, question=qs[0], answer=r["object"])
        props = cached("shorten", r["id"], lambda: llm.json(prompt, LIST_SCHEMA, 0.4, r["id"]))
        status, answer = "reject: no proposal", ""
        for p in props.get("items", []):
            s = sanitize(str(p)).strip()
            st = check_short_explanation(r["object"], s, qs, tokens, AB)
            if st == "ok" or (st == "to_fact" and status.startswith("reject")):
                status, answer = st, s
            if st == "ok":
                break
            if status.startswith("reject"):
                status = st
        kw = next((t for t in key_terms(qs[0]) if t[:5].lower() in answer.lower()), "")
        return (r["id"], "|".join(qs), answer, kw, f"llm:{llm.model}", status, "no")

    rows = list(run_parallel(entries, work, a.workers, lambda r: r["id"],
                             lambda row: row[5][:26]))  # fmt: skip
    rows.sort(
        key=lambda row: [int(x) if x.isdigit() else x for x in row[0].replace("/", " ").split()]
    )
    OUT.write_text("\t".join(COLS) + "\n" + "".join("\t".join(r) + "\n" for r in rows),
                   encoding="utf-8")  # fmt: skip
    n_ok = sum(r[5] == "ok" for r in rows)
    n_fact = sum(r[5] == "to_fact" for r in rows)
    log(f"-> {OUT.name}: {n_ok} ok, {n_fact} to_fact, {len(rows) - n_ok - n_fact} abgelehnt. "
        "Bitte prüfen und 'reviewed' auf yes setzen.")  # fmt: skip
    return 0


if __name__ == "__main__":
    sys.exit(main())
