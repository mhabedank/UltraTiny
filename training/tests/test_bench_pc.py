"""PC run, result file and --check (specs/007-benchmark-kpi-bericht T010, T044)."""

import copy
import json
from pathlib import Path

from ultratiny.bench import pc
from ultratiny.bench.suite import load_suite

FIX = Path(__file__).parent / "fixtures"
TINY_V2 = Path(__file__).parents[2] / "runtime" / "tests" / "fixtures" / "tiny_v2.utny"
FACTS = Path(__file__).parents[2] / "runtime" / "tests" / "fixtures" / "facts_small.utft"
KPIS = [
    "F1",
    "F2",
    "F3",
    "F4",
    "F5",
    "F6",
    "R1",
    "R2",
    "R3",
    "R4",
    "S1",
    "S2",
    "S3",
    "T1",
    "T2",
    "T3",
]


def run(**kw):
    return pc.run_pc(load_suite(FIX / "bench_mini"), TINY_V2, log=lambda *_: None, **kw)


def test_result_has_every_kpi_and_identity():
    r = run(label="tiny")
    assert sorted(r["kpis"]) == sorted(KPIS)
    assert r["kind"] == "pc" and r["label"] == "tiny" and r["complete"] is True
    assert r["model"]["params"] > 0 and len(r["model"]["sha256"]) == 64
    assert r["suite"]["name"] == "mini" and "unseen" in r["suite"]["sets"]
    assert r["kpis"]["T1"]["status"] == "not_measured"
    sets = {i["set"] for i in r["items"]}
    assert sets == {"unseen", "unknown", "offtopic", "kurzarbeit", "s3", "facts"}
    assert all(i["class"] in ("correct", "wrong_fact", "refused", "no_answer") for i in r["items"])
    assert r["overlap"]["unseen"] == "unknown"


def test_two_runs_identical_and_jobs_independent():
    a, b = run(), run(jobs=2)
    assert a["kpis"] == b["kpis"]
    assert a["items"] == b["items"]


def test_v2_model_without_facts_prints_missing_text():
    r = run(only={"unseen"})
    assert r["complete"] is False
    assert all("Faktentabelle fehlt" in i["answer"] or i["class"] != "correct" for i in r["items"])


def test_with_facts_answers_are_rendered():
    r = pc.run_pc(
        load_suite(FIX / "bench_mini"), TINY_V2, FACTS, only={"unseen"}, log=lambda *_: None
    )
    assert r["knowledge"]["size"] == FACTS.stat().st_size
    assert r["kpis"]["R3"]["value"] == FACTS.stat().st_size
    assert all("\x01" not in i["answer"] for i in r["items"])


def test_overlap_with_training_data(tmp_path):
    td = tmp_path / "train.txt"
    td.write_text("Wofür steht N?\tx\nirgendwas\ty\n", encoding="utf-8")
    r = run(only={"unseen"}, train_data=td)
    assert r["overlap"]["unseen"] == 1


def test_check_detects_changes(tmp_path):
    r = run()
    assert pc.check(r, copy.deepcopy(r)) == []
    ref = copy.deepcopy(r)
    ref["items"][0]["class"] = "correct" if r["items"][0]["class"] != "correct" else "wrong_fact"
    ref["kpis"]["F1"]["value"] = -1
    diffs = pc.check(r, ref)
    assert any(r["items"][0]["id"] in d for d in diffs)
    assert any(d.startswith("KPI F1") for d in diffs)
    p = tmp_path / "r.json"
    pc.write_result(r, p)
    assert pc.check(r, json.loads(p.read_text(encoding="utf-8"))) == []


def test_rating_sheet_roundtrip(tmp_path):
    r = run(only={"s3"})
    sheet = tmp_path / "r.s3.tsv"
    assert pc.write_sheet(r, sheet)["status"] == "not_measured"
    lines = sheet.read_text(encoding="utf-8").splitlines()
    lines = [lines[0]] + [ln.rstrip("\t") + "\tja" if ln.endswith("\t") else ln for ln in lines[1:]]
    sheet.write_text("\n".join(lines) + "\n", encoding="utf-8")
    s3 = pc.write_sheet(r, sheet)
    assert s3["value"] == 100.0 and s3["n"] == 2
    r2 = copy.deepcopy(r)
    r2["items"][0]["answer"] += "x"  # changed answer: its rating no longer counts
    assert pc.s3_from_ratings(r2, pc.read_ratings(sheet))["n"] == 1
