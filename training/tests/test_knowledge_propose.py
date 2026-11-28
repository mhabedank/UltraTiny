"""LLM fact proposals with human review (specs/008-wissens-compiler US4, FR-022, research R14)."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from ultratiny.knowledge.propose import accept, gaps, propose
from ultratiny.knowledge.topic import load_topic

MINI = Path(__file__).parent / "fixtures" / "topics" / "mini"


@pytest.fixture
def mini(tmp_path) -> Path:
    d = tmp_path / "mini"
    shutil.copytree(MINI, d)
    return d


def fake_llm(prompt: str) -> str:
    """Proposes a population for every city; refuses for Desstadt."""
    if "Desstadt" in prompt:
        return '{"value": ""}'
    return "Antwort: " + json.dumps({"value": "3,5", "source": "llm:fake", "reason": "geschätzt"})


def fact_files(d: Path) -> dict[str, str]:
    return {p.name: p.read_text(encoding="utf-8") for p in sorted((d / "facts").glob("*.tsv"))}


def test_gaps():
    topic = load_topic(MINI)
    missing = [k for k, _ in gaps(topic, "einwohner")]
    assert "Aa" not in missing and "De" in missing and "Zz" in missing


def test_propose_writes_only_the_review_list(mini):
    before = fact_files(mini)
    out = propose(mini, "einwohner", fake_llm, limit=4)
    assert fact_files(mini) == before  # no fact file changes
    rows = out.read_text(encoding="utf-8").splitlines()
    assert rows[0] == "subject\trelation\tvalue\tsource\treason\taccepted"
    assert all(r.endswith("\t") for r in rows[1:])  # `accepted` left empty for a person
    assert not any(r.startswith("De\t") for r in rows)  # the model declined


def test_accept_copies_only_reviewed_rows_with_a_real_source(mini):
    out = mini / "proposals" / "review.tsv"
    out.parent.mkdir()
    out.write_text(
        "subject\trelation\tvalue\tsource\treason\taccepted\n"
        "Ce\teinwohner\t3,5\town\tgeprüft\tyes\n"  # accepted with a real source
        "Zz\teinwohner\t1,0\tllm:fake\tgeschätzt\tyes\n"  # llm source -> rejected
        "L01\teinwohner\t2,0\town\tunsicher\tno\n"  # not accepted
        "L02\teinwohner\tviele\town\tfalsch\tyes\n",  # wrong type -> rejected
        encoding="utf-8",
    )
    n, rejected = accept(out, mini)
    assert n == 1 and len(rejected) == 2
    assert "llm sources are not allowed" in rejected[0] and "decimal" in rejected[1]
    acc = (mini / "facts" / "accepted.tsv").read_text(encoding="utf-8").splitlines()
    assert acc == ["subject\trelation\tvalue\tsource", "Ce\teinwohner\t3,5\town"]
    topic = load_topic(mini)  # the accepted fact is part of the topic now
    assert any(f.subject == "Ce" and f.relation == "einwohner" for f in topic.facts)
    n2, _ = accept(out, mini)  # idempotent
    assert n2 == 0
