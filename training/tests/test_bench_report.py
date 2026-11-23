"""Comparison report (specs/007-benchmark-kpi-bericht T029, research R9/R10)."""

import copy
from pathlib import Path

import pytest

from ultratiny.bench import pc, report
from ultratiny.bench.suite import load_suite

FIX = Path(__file__).parent / "fixtures"
TINY_V2 = Path(__file__).parents[2] / "runtime" / "tests" / "fixtures" / "tiny_v2.utny"


@pytest.fixture(scope="module")
def base():
    r = pc.run_pc(load_suite(FIX / "bench_mini"), TINY_V2, label="base", log=lambda *_: None)
    r["kpis"]["F1"] = {"value": 50.0, "n": 200, "status": "measured"}
    return r


def variant(base, label, **kpis):
    r = copy.deepcopy(base)
    r["label"] = label
    for k, v in kpis.items():
        r["kpis"][k] = dict(r["kpis"][k], value=v, status="measured")
    return r


def verdict_of(rep, label, k):
    return next(row for row in rep["rows"] if row["kpi"] == k)["vs_base"][label][0]


def test_noise_threshold(base):
    rep = report.build(
        [
            (Path("a.json"), base),
            (Path("b.json"), variant(base, "s2", F1=52.0)),
            (Path("c.json"), variant(base, "s4", F1=54.0)),
        ]
    )
    assert verdict_of(rep, "s2", "F1") == "unverändert"
    assert verdict_of(rep, "s4", "F1") == "besser"
    rep = report.build([(Path("a.json"), base), (Path("b.json"), variant(base, "w", F1=40.0))])
    assert verdict_of(rep, "w", "F1") == "schlechter"


def test_seed_spread(base):
    seeds = [variant(base, "s", F1=v) for v in (50.0, 58.0, 62.0)]  # mean 56.7, spread ~6.1
    rep = report.build(
        [(Path("a.json"), base)] + [(Path(f"{i}.json"), r) for i, r in enumerate(seeds)]
    )
    assert verdict_of(rep, "s", "F1") == "unverändert"  # 6.7 > 3, but not > 2 x spread
    row = next(r for r in rep["rows"] if r["kpi"] == "F1")
    assert row["cells"]["s"]["n"] == 3 and row["cells"]["s"]["spread"] > 5


def test_exact_kpis_count_any_change(base):
    rep = report.build(
        [
            (Path("a.json"), base),
            (Path("b.json"), variant(base, "b", R2=base["kpis"]["R2"]["value"] + 1)),
        ]
    )
    assert verdict_of(rep, "b", "R2") == "schlechter"


def test_not_comparable_and_not_measured(base):
    other = copy.deepcopy(base)
    other["label"] = "x"
    other["suite"]["sets"]["unseen"] = "v2:deadbeef"
    rep = report.build([(Path("a.json"), base), (Path("b.json"), other)])
    assert verdict_of(rep, "x", "F1") == "nicht vergleichbar"
    assert verdict_of(rep, "x", "F5") != "nicht vergleichbar"
    assert verdict_of(rep, "x", "T1") == "nicht gemessen"


def test_budget_and_parity_flags(base):
    big = copy.deepcopy(base)
    big["label"] = "big"
    big["model"]["size"] = 700_000
    board = copy.deepcopy(base)
    board.update(kind="board", label="base")
    board["items"][0]["parity"] = False
    rep = report.build([(Path("a.json"), base), (Path("b.json"), big), (Path("c.json"), board)])
    assert rep["budget_broken"] and rep["parity_broken"]
    md = report.to_markdown(rep, generated="X")
    assert "budget broken" in md and "parity broken" in md and "gerissen" in md


def test_changed_answers_listed(base):
    other = copy.deepcopy(base)
    other["label"] = "o"
    item = other["items"][0]
    item["class"] = "correct" if item["class"] != "correct" else "wrong_fact"
    rep = report.build([(Path("a.json"), base), (Path("b.json"), other)])
    assert [c["id"] for c in rep["changed"]["o"]] == [item["id"]]
    assert item["id"] in report.to_markdown(rep, generated="X")


def test_deterministic_output(base):
    res = [(Path("a.json"), base), (Path("b.json"), variant(base, "b", F1=60.0))]
    a = report.to_markdown(report.build(res), generated="X") + report.to_html(
        report.build(res), "X"
    )
    b = report.to_markdown(report.build(res), generated="X") + report.to_html(
        report.build(res), "X"
    )
    assert a == b
    assert "<svg" in a and "<script" not in a
