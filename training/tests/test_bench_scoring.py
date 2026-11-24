"""Answer scoring against a hand-labelled sample (specs/007-benchmark-kpi-bericht T008, SC-008)."""

import csv
from pathlib import Path

from ultratiny.bench.scoring import Scorer, fact_kpis, number_matches
from ultratiny.bench.suite import Item, ValueClass, _parse_expected, load_suite

FIX = Path(__file__).parent / "fixtures"


def load_sample():
    with open(FIX / "bench_scoring_sample.tsv", encoding="utf-8") as f:
        lines = [x for x in f if not x.startswith("#")]
    return list(csv.DictReader(lines, delimiter="\t", quoting=csv.QUOTE_NONE))


def test_hand_labelled_sample_agrees():
    suite = load_suite(FIX / "bench_mini")
    sc = Scorer(suite)
    rows = load_sample()
    assert len(rows) == 50
    misses = []
    for r in rows:
        exp, kws = _parse_expected(r["expected"], r["kind"], "sample")
        item = Item("unseen", "x", r["kind"], "?", exp, kws)
        got = sc.score(item, r["answer"])["class"]
        if got != r["label"]:
            misses.append((r["answer"], r["label"], got))
    assert len(misses) <= 1, misses  # SC-008: at least 49 of 50
    assert not misses, misses  # the sample is written to the rules, so all should agree


def test_number_matching():
    vc = ValueClass("number", "number", decimals=2)
    assert number_matches("22,99", "22,99", vc)
    assert number_matches("23", "22,99", vc)
    assert number_matches("18,0", "18,02", vc)
    assert not number_matches("22,9", "22,99", vc)
    assert not number_matches("229", "22,99", vc)


def test_fact_kpis_denominators():
    recs = [
        {"set": "unseen", "kind": "fact", "type": "a", "class": "correct", "ok": True},
        {"set": "unseen", "kind": "fact", "type": "b", "class": "wrong_fact", "ok": False},
        {"set": "unseen", "kind": "fact", "type": "b", "class": "refused", "ok": False},
        {"set": "unseen", "kind": "fact", "type": "c", "class": "no_answer", "ok": False},
        {"set": "unknown", "kind": "unknown", "type": "unknown", "class": "refused", "ok": True},
        {"set": "offtopic", "kind": "refuse", "type": "refuse", "class": "no_answer", "ok": False},
        {"set": "kurzarbeit", "kind": "fact", "type": "a", "class": "wrong_fact", "ok": False},
        {"set": "kurzarbeit", "kind": "explain", "type": "explain", "class": "correct", "ok": True},
        {"set": "facts", "kind": "fact", "type": "a", "class": "correct", "ok": True},
    ]
    k = fact_kpis(recs)
    assert k["F1"]["value"] == 25.0 and k["F1"]["n"] == 4
    assert k["F1"]["detail"]["by_type"] == {"a": 100.0, "b": 0.0, "c": 0.0}
    assert k["F2"]["value"] == 40.0 and k["F2"]["n"] == 5
    assert k["F3"]["value"] == 50.0 and k["F4"]["value"] == 25.0
    assert k["F5"]["value"] == 50.0 and k["F6"]["value"] == 1
