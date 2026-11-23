"""Suite loading and pin checks (specs/007-benchmark-kpi-bericht T007, SC-006)."""

import shutil
from pathlib import Path

import pytest

from ultratiny.bench.suite import SuiteError, all_questions, load_suite, pin_suite

MINI = Path(__file__).parent / "fixtures" / "bench_mini"


def copy_mini(tmp_path: Path) -> Path:
    dst = tmp_path / "mini"
    shutil.copytree(MINI, dst)
    return dst


def test_mini_suite_loads():
    s = load_suite(MINI)
    assert s.name == "mini" and s.version == 1
    assert {k: len(v) for k, v in s.sets.items()} == {
        "unseen": 5,
        "unknown": 2,
        "offtopic": 2,
        "kurzarbeit": 3,
        "s3": 2,
    }
    assert set(s.s1) == {"topic", "general"} and len(s.s2) == 6
    assert s.value("Na", "element_atommasse") == "22,99"
    assert s.sets["unseen"][3].expected == [("element_symbol", "Na"), ("element_atommasse", "Na")]
    assert all(v.startswith("v1:") for v in s.versions().values())


def test_changed_byte_fails_with_file_name(tmp_path):
    d = copy_mini(tmp_path)
    p = d / "sets" / "unseen.tsv"
    p.write_bytes(p.read_bytes().replace(b"Natrium", b"Natrion", 1))
    with pytest.raises(SuiteError, match="sets/unseen.tsv: changed"):
        load_suite(d)
    pin_suite(d)
    load_suite(d)  # re-pinned


def test_unpinned_file_is_refused(tmp_path):
    d = copy_mini(tmp_path)
    toml = d / "suite.toml"
    text = toml.read_text(encoding="utf-8")
    start = text.index('"facts.tsv" = "') + len('"facts.tsv" = "')
    toml.write_text(text[:start] + text[start + 64 :], encoding="utf-8")
    with pytest.raises(SuiteError, match="not pinned"):
        load_suite(d)
    load_suite(d, allow_unpinned=True)


@pytest.mark.parametrize(
    "line, msg",
    [
        ("un/009\t-\tfact\tWas ist X?\tfoo_bar: Na\n", "unknown property"),
        ("un/009\t-\tfact\tWas ist X?\telement_symbol: Xx\n", "no fact for"),
        ("un/001\t-\tfact\tWas ist X?\telement_symbol: Na\n", "duplicate id"),
        ("un/009\t-\tfact\t" + "x" * 71 + "\telement_symbol: Na\n", "longer than 70"),
        ("un/009\t-\tquiz\tWas ist X?\t\n", "unknown kind"),
    ],
)
def test_invalid_items_are_rejected(tmp_path, line, msg):
    d = copy_mini(tmp_path)
    with open(d / "sets" / "unseen.tsv", "a", encoding="utf-8") as f:
        f.write(line)
    pin_suite(d)
    with pytest.raises(SuiteError, match=msg):
        load_suite(d)


def test_duplicate_fact_is_rejected(tmp_path):
    d = copy_mini(tmp_path)
    with open(d / "facts.tsv", "a", encoding="utf-8") as f:
        f.write("Na\tNatrium\telement_symbol\tNa\n")
    pin_suite(d)
    with pytest.raises(SuiteError, match="duplicate fact"):
        load_suite(d)


def test_all_questions_normalised(tmp_path):
    d = copy_mini(tmp_path)
    qs = all_questions(tmp_path)
    assert "wofür steht n" in qs and "wie spät ist es" in qs
    assert len(qs) == 14
    assert d.exists()
