"""Topic validation (specs/008-wissens-compiler FR-004, FR-005, FR-007; data-model.md rules).

Each bad case copies the `mini` fixture topic and breaks one rule; the build must stop and name
file, line or TOML key, and the rule.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from ultratiny.knowledge.compile import build
from ultratiny.knowledge.topic import TopicError, load_topic

MINI = Path(__file__).parent / "fixtures" / "topics" / "mini"


@pytest.fixture
def mini(tmp_path) -> Path:
    d = tmp_path / "mini"
    shutil.copytree(MINI, d)
    return d


def append(path: Path, line: str) -> None:
    with open(path, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def replace(path: Path, old: str, new: str) -> None:
    s = path.read_text(encoding="utf-8")
    assert old in s, old
    path.write_text(s.replace(old, new, 1), encoding="utf-8")


def errors_of(d: Path) -> str:
    with pytest.raises(TopicError) as e:
        build(load_topic(d))
    return str(e.value)


def test_mini_loads_and_builds():
    topic = load_topic(MINI)
    assert topic.id == "mini" and len(topic.objects) == 20
    image, report = build(topic)
    assert report["answerable"] > 0 and report["facts_derived"] == 10


@pytest.mark.parametrize(
    "line, needle",
    [
        ("Aa\trang\tzwei\town", "is not an int"),
        ("Aa\teinwohner\t12,55\town", "decimal with 1 decimals"),
        ("NL\tsprache\tMittel\town", "not one of the enum values"),
        ("Aa\tland\tAa\town", "is a stadt, expected land"),
        ("Aa\trang\t7\town", "card=one, but Aa already has 1"),
        ("Aa\trang\t1\town", "duplicate fact"),
        ("Aa\tkontinent\tOstia\town", "needs a land"),
        ("Qq\trang\t5\town", "not an object key"),
        ("Aa\tfoo\t1\town", "relation 'foo' unknown"),
        ("Aa\teinwohner\t1,0\t", "missing source"),
        ("Aa\teinwohner\t1,0\tllm:qwen3", "llm sources are not allowed"),
        ("Aa\teinwohner\t1,0\tblog:x", "not allowed (DATA_LICENSES.md)"),
        ("NL\tkontinent\t" + "x" * 61 + "\town", "longer than 60 B"),
    ],
)
def test_bad_fact(mini, line, needle):
    append(mini / "facts" / "basis.tsv", line)
    err = errors_of(mini)
    assert needle in err
    assert "facts/basis.tsv:" in err  # file and line


@pytest.mark.parametrize(
    "line, needle",
    [
        ("Aa\tDoppelt\tstadt\town", "already defined"),
        ("Qq\tAastadt\tstadt\town", "already used in class stadt"),
        ("Qqqqqqqqqqqqq\tLang\tstadt\town", "> 12 B"),
        ("Q§\tSonder\tstadt\town", "outside the alphabet"),
        ("Qn\t" + "N" * 41 + "\tstadt\town", "> 40 B"),
        ("Qc\tKlasse\tdorf\town", "class 'dorf' unknown"),
    ],
)
def test_bad_object(mini, line, needle):
    append(mini / "objects.tsv", line)
    err = errors_of(mini)
    assert needle in err and "objects.tsv:" in err


def test_reverse_one_must_be_unique(mini):
    replace(mini / "facts" / "basis.tsv", "Be\trang\t2", "Be\trang\t1")
    # same rang for Aa and Be: reverse = one is violated (and the class order ties)
    err = errors_of(mini)
    assert "reverse = one" in err and "Aa" in err and "Be" in err


def test_rule_conflict_with_explicit_fact(mini):
    append(mini / "facts" / "basis.tsv", "Aa\tgroesse\tklein\town")
    err = errors_of(mini)
    assert "[rules.gross]" in err and "contradicts" in err and "facts/basis.tsv" in err


def test_list_that_cannot_fit(mini):
    replace(mini / "schema.toml", 'more = " und {n} weitere"', 'more = "' + "x" * 95 + '{n}"')
    err = errors_of(mini)
    assert "> 100" in err


def test_template_needs_prefix(mini):
    replace(mini / "schema.toml", 'template = "Rang von {name}: {v}."', 'template = "{name}: {v}."')
    assert "must start with fixed text" in errors_of(mini)


def test_unused_relation_and_missing_question(mini):
    append(mini / "schema.toml", '\n[relations.extra]\nsubject = "land"\ntype = "text"\n')
    assert "no view uses this relation" in errors_of(mini)


def test_more_required_for_lists(mini):
    replace(mini / "schema.toml", 'more = " und {n} weitere"\n', "")
    assert "'more' is required" in errors_of(mini)


def test_letter_unique(mini):
    replace(mini / "schema.toml", 'letter = "K"', 'letter = "R"')
    assert "already used by" in errors_of(mini)


def test_competency_question_must_match(mini):
    replace(
        mini / "schema.toml", 'expect = "Rang von Aastadt: 1."', 'expect = "Rang von Aastadt: 2."'
    )
    assert "expected 'Rang von Aastadt: 2.'" in errors_of(mini)


def test_budget(mini):
    append(mini / "topic.toml", "budget_bytes = 500")
    assert "exceeds the budget" in errors_of(mini)


def test_topic_id_must_match_directory(mini):
    replace(mini / "topic.toml", 'id = "mini"', 'id = "anders"')
    assert "must equal the directory name" in errors_of(mini)
