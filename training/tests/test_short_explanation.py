"""Automatic check of shortened explanations (specs/006 research R8, task T032)."""

from ultratiny.alphabet import Alphabet
from ultratiny.augment import check_short_explanation

AB = Alphabet()
LONG = ("Ein Ion ist ein elektrisch geladenes Teilchen. Es entsteht, wenn ein Atom Elektronen "
        "abgibt oder aufnimmt.")  # fmt: skip
Q = ["Was ist ein Ion?", "Ion?"]


def chk(short, long=LONG, q=Q, facts=frozenset({"CaCO3", "H2O"})):
    return check_short_explanation(long, short, q, set(facts), AB)


def test_accepts_good_short_answer():
    assert chk("Ein Ion ist ein elektrisch geladenes Teilchen.") == "ok"


def test_rejects_too_long_or_bad_chars():
    assert chk("x" * 61).startswith("reject")
    assert chk("Ein Ion ist ein geladenes Teilchen → ja.").startswith("reject")


def test_rejects_new_number_or_formula():
    assert chk("Ein Ion hat 2 Ladungen.").startswith("reject")
    assert chk("Ein Ion wie NaCl ist geladen.").startswith("reject")


def test_rejects_missing_key_term():
    assert chk("Ein geladenes Teilchen.") == "reject: key term missing"


def test_table_fact_becomes_fact_question():
    long = "Kalk ist Calciumcarbonat, Formel CaCO3. Er kommt in Gestein vor."
    assert chk("Kalk ist Calciumcarbonat, CaCO3.", long, ["Was ist Kalk chemisch?"]) == "to_fact"
