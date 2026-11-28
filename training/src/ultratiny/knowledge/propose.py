"""Optional LLM fact proposals with human review (specs/008-wissens-compiler/research.md R14).

`propose` lists subjects of a relation's class without a value, asks a language model for value,
source and reason, and writes `topics/<id>/proposals/<date>.tsv` (column `accepted` empty). It never
touches a fact file. `accept` copies rows with `accepted = yes` and an allowed non-`llm:` source
into `facts/accepted.tsv` (data-model.md "Fact proposal"). No fact value enters a topic without a
person's decision (FR-022).
"""

from __future__ import annotations

import csv
import datetime as dt
import json
import sys
from collections.abc import Callable
from pathlib import Path

from ..datagen import allowed_source_prefixes
from .topic import TopicError, check_value, load_topic, source_error

HEADER = ("subject", "relation", "value", "source", "reason", "accepted")
ACCEPTED_FILE = Path("facts") / "accepted.tsv"

PROMPT = (
    "Du hilfst, eine geprüfte Wissensbasis zu füllen. Gib für das Objekt '{name}' ({key}) den "
    "Wert der Eigenschaft '{relation}' an. Antworte nur mit JSON: "
    '{{"value": "...", "source": "wikidata:Q... oder eine andere überprüfbare Quelle", '
    '"reason": "kurze Begründung"}}. Wenn du es nicht sicher weißt, antworte mit {{"value": ""}}.'
)


def gaps(topic, relation: str) -> list[tuple[str, str]]:
    """(key, name) of the relation's subjects without a value."""
    rel = topic.relations[relation]
    have = {f.subject for f in topic.facts if f.relation == relation}
    return [(o.key, o.name) for o in topic.objects if o.cls == rel.subject and o.key not in have]


def propose(
    topic_dir: Path,
    relation: str,
    ask: Callable[[str], str],
    out: Path | None = None,
    limit: int | None = None,
) -> Path:
    topic = load_topic(topic_dir)
    if relation not in topic.relations:
        raise TopicError([f"relation {relation!r} unknown"])
    rows = []
    for key, name in gaps(topic, relation)[:limit]:
        raw = ask(PROMPT.format(name=name, key=key, relation=relation))
        try:
            ans = json.loads(raw[raw.index("{") : raw.rindex("}") + 1])
        except (ValueError, json.JSONDecodeError):
            continue
        value = str(ans.get("value", "")).strip()
        if not value:
            continue
        rows.append(
            (
                key,
                relation,
                value,
                str(ans.get("source", "")).strip(),
                str(ans.get("reason", "")).strip(),
                "",
            )
        )
    out = out or topic.root / "proposals" / f"{dt.date.today().isoformat()}.tsv"
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w", encoding="utf-8", newline="\n") as f:
        f.write("\t".join(HEADER) + "\n")
        for r in rows:
            f.write("\t".join(c.replace("\t", " ").replace("\n", " ") for c in r) + "\n")
    return out


def accept(proposal: Path, topic_dir: Path | None = None) -> tuple[int, list[str]]:
    """Copy accepted rows into facts/accepted.tsv. Returns (copied, rejection messages)."""
    proposal = Path(proposal)
    topic_dir = Path(topic_dir) if topic_dir else proposal.resolve().parents[1]
    topic = load_topic(topic_dir)
    allowed = allowed_source_prefixes()
    obj_class = topic.class_of()
    target = topic.root / ACCEPTED_FILE
    existing: list[tuple[str, ...]] = []
    if target.exists():
        with open(target, encoding="utf-8", newline="") as f:
            existing = [tuple(r) for r in csv.reader(f, delimiter="\t")][1:]
    rejected: list[str] = []
    new: list[tuple[str, ...]] = []
    with open(proposal, encoding="utf-8", newline="") as f:
        for i, r in enumerate(csv.DictReader(f, delimiter="\t"), 2):
            if r.get("accepted", "").strip() != "yes":
                continue
            where = f"{proposal}:{i}"
            rel = topic.relations.get(r["relation"])
            if rel is None:
                rejected.append(f"{where}: relation {r['relation']!r} unknown")
                continue
            if e := source_error(r["source"], allowed):
                rejected.append(f"{where}: {e}")
                continue
            if e := check_value(rel, r["value"], obj_class):
                rejected.append(f"{where}: {e}")
                continue
            new.append((r["subject"], r["relation"], r["value"], r["source"]))
    rows = sorted(set(existing) | set(new))
    target.parent.mkdir(parents=True, exist_ok=True)
    with open(target, "w", encoding="utf-8", newline="\n") as f:
        f.write("subject\trelation\tvalue\tsource\n")
        for r in rows:
            f.write("\t".join(r) + "\n")
    return len(set(new) - set(existing)), rejected


def _ollama_ask(model: str, host: str = "http://localhost:11434") -> Callable[[str], str]:
    """The Spark LLM client of training/tools/shorten_llm.py (Ollama HTTP API)."""
    import urllib.request

    def ask(prompt: str) -> str:
        req = urllib.request.Request(
            host.rstrip("/") + "/api/generate",
            data=json.dumps({"model": model, "prompt": prompt, "stream": False}).encode(),
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=300) as resp:
            return json.loads(resp.read())["response"]

    return ask


def cmd_propose(a) -> int:
    try:
        out = propose(
            Path(a.topic),
            a.relation,
            _ollama_ask(a.model, a.host),
            Path(a.out) if a.out else None,
            a.limit,
        )
    except TopicError as e:
        print("\n".join(e.errors), file=sys.stderr)
        return 1
    print(f"knowledge: wrote {out}; fill in `accepted` (yes/no) and real sources, then accept")
    return 0


def cmd_accept(a) -> int:
    try:
        n, rejected = accept(Path(a.proposal), Path(a.topic) if a.topic else None)
    except TopicError as e:
        print("\n".join(e.errors), file=sys.stderr)
        return 1
    for r in rejected:
        print(f"  rejected: {r}", file=sys.stderr)
    print(f"knowledge: {n} new fact(s) in facts/accepted.tsv, {len(rejected)} rejected")
    return 0


def add_parsers(ks) -> None:
    q = ks.add_parser("propose", help="LLM proposals for a relation's gaps (review list only)")
    q.add_argument("--topic", required=True)
    q.add_argument("--relation", required=True)
    q.add_argument("--model", required=True, help="Ollama model on the Spark, e.g. qwen3.6:35b")
    q.add_argument("--host", default="http://localhost:11434")
    q.add_argument("--limit", type=int)
    q.add_argument("--out")
    q.set_defaults(func=cmd_propose)
    q = ks.add_parser("accept", help="copy accepted proposal rows into facts/accepted.tsv")
    q.add_argument("proposal")
    q.add_argument("--topic")
    q.set_defaults(func=cmd_accept)
