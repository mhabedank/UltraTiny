"""Build-time rules (specs/008-wissens-compiler FR-006, FR-007, research R8)."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from ultratiny.knowledge import rules
from ultratiny.knowledge.compile import build
from ultratiny.knowledge.image import Image
from ultratiny.knowledge.topic import TopicError, load_topic

MINI = Path(__file__).parent / "fixtures" / "topics" / "mini"


@pytest.fixture
def mini(tmp_path) -> Path:
    d = tmp_path / "mini"
    shutil.copytree(MINI, d)
    return d


def derived(topic) -> dict[tuple[str, str], str]:
    facts, _ = rules.apply_rules(topic)
    return {(f.subject, f.relation): f.value for f in facts[len(topic.facts) :]}


def test_every_rule_kind():
    topic = load_topic(MINI)
    d = derived(topic)
    # class rule with `between` and `except` (Zz has rang 9, outside anyway)
    assert d[("Aa", "groesse")] == "groß" and d[("Ce", "groesse")] == "groß"
    assert ("De", "groesse") not in d  # rang 4 is outside [1, 3]
    # class rule with `equals`
    assert d[("Zz", "groesse")] == "klein"
    # chain: stadt -land-> land -kontinent-> value
    assert d[("Aa", "erdteil")] == "Ostia" and d[("Zz", "erdteil")] == "Westia"
    # table
    assert d[("NL", "gruss")] == "Salve" and d[("SL", "gruss")] == "Hallo"


def test_provenance_names_rule_and_inputs():
    topic = load_topic(MINI)
    facts, per_rule = rules.apply_rules(topic)
    chain = next(f for f in facts if (f.subject, f.relation) == ("Aa", "erdteil"))
    assert chain.origin.startswith("rule erdteil from ") and chain.origin.count("facts/") == 2
    assert per_rule == {"gross": 3, "klein": 1, "erdteil": 4, "gruss": 2}


def test_except_list(mini):
    s = (mini / "schema.toml").read_text(encoding="utf-8")
    (mini / "schema.toml").write_text(s.replace('except = ["Zz"]', 'except = ["Aa"]'))
    d = derived(load_topic(mini))
    assert ("Aa", "groesse") not in d and d[("Be", "groesse")] == "groß"


def test_equal_explicit_fact_is_dropped(mini):
    with open(mini / "facts" / "basis.tsv", "a", encoding="utf-8") as f:
        f.write("Aa\tgroesse\tgroß\town\n")
    topic = load_topic(mini)
    facts, per_rule = rules.apply_rules(topic)
    assert per_rule["gross"] == 2  # Aa already had it explicitly
    assert sum((f.subject, f.relation) == ("Aa", "groesse") for f in facts) == 1


def test_conflict_between_two_rules(mini):
    s = (mini / "schema.toml").read_text(encoding="utf-8")
    (mini / "schema.toml").write_text(s.replace("equals = 9", "equals = 2"))
    with pytest.raises(TopicError) as e:
        rules.apply_rules(load_topic(mini))
    msg = str(e.value)
    assert "[rules.klein]" in msg and "contradicts" in msg and "rule gross" in msg


def test_rules_that_keep_growing_stop(mini, monkeypatch):
    monkeypatch.setattr(rules, "MAX_FACTS", 45)
    with pytest.raises(TopicError) as e:
        rules.apply_rules(load_topic(mini))
    assert "rules keep growing" in str(e.value)


def test_derived_facts_answer_on_the_image():
    img = Image(build(load_topic(MINI))[0])
    assert img.query("erdteil Ce").decode() == "Erdteil: Cestadt liegt auf Ostia."
    assert img.query("groesse Zz").decode() == "Größe: Zettstadt ist klein."
