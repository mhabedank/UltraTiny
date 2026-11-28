"""Scoring of the hybrid evaluation (contracts/eval-sets.md "Scoring", task T040)."""

import pytest

from ultratiny import hybrid
from ultratiny.alphabet import EOS, FN, Alphabet
from ultratiny.datagen import TRAINING_ROOT
from ultratiny.evaluate import normalize
from ultratiny.knowledge.image import Image

AB = Alphabet(fn=True)
TABLE = Image((TRAINING_ROOT.parent / "models/chemie.utki").read_bytes())
REFUSALS = {normalize(hybrid.UNKNOWN_TEXT), normalize(hybrid.REFUSAL_ANSWER)}


def fn(s):
    return [FN, *AB.encode(s), EOS]


def text(s):
    return [*AB.encode(s), EOS]


def sc(kind, expected, tokens, **extra):
    row = {"prompt": "q", "kind": kind, "expected": expected, **extra}
    return hybrid.score(row, tokens, AB, TABLE, REFUSALS)


@pytest.mark.parametrize(
    ("kind", "expected", "tokens", "correct", "wrong"),
    [
        ("fact", ["OCu"], fn("OCu"), True, False),  # exact function output
        ("fact", ["pNa", "ONa"], fn("ONa"), True, False),  # accepted alternative
        # other type with a different printed answer for the same object -> counted as wrong
        ("fact", ["OCu"], fn("o29"), False, True),
        ("fact", ["OCu"], fn("ONa"), False, True),  # wrong object -> wrong fact
        ("fact", ["OCu"], fn("OXx"), False, False),  # unknown key -> decline
        ("fact", ["OCu"], text(hybrid.REFUSAL_ANSWER), False, False),  # refusal -> decline
        ("fact", ["iNe"], fn("iNe"), True, False),  # not applicable is the right answer
        ("multi", ["SNa", "ONa"], fn("ONa"), True, False),
        ("refuse", [], text(hybrid.REFUSAL_ANSWER), True, False),
        ("refuse", [], fn("OXx"), True, False),  # unknown lookup counts as declining
        ("refuse", [], text("Hallo!"), False, False),
        ("unknown", [], text(hybrid.UNKNOWN_TEXT), True, False),
        ("unknown", [], fn("OCu"), False, True),  # invented fact for an unknown object
        ("explain", ["Stoff"], text("Ein Stoff wandelt sich um."), True, False),
        ("explain", ["Stoff"], text("Etwas passiert."), False, False),
        ("explain", ["Stoff"], fn("OCu"), False, False),
    ],
)
def test_scoring_table(kind, expected, tokens, correct, wrong):
    r = sc(kind, expected, tokens)
    assert (r["correct"], r["wrong_fact"]) == (correct, wrong)


def test_printed_answer_of_correct_output():
    r = sc("fact", ["SCu"], fn("SCu"))
    assert r["correct"] and r["printed"] == "Das Symbol von Kupfer ist Cu."


def test_summarize_rates():
    rs = [sc("fact", ["OCu"], fn("OCu")), sc("fact", ["OCu"], fn("ONa")),
          sc("fact", ["OCu"], fn("OXx")), sc("fact", ["OCu"], fn("OCu"))]  # fmt: skip
    s = hybrid.summarize(rs)
    assert s["accuracy"] == 0.5 and s["wrong_fact"] == 0.25 and s["declined"] == 0.25
