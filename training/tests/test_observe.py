"""Tests for the observability viewer's event parsing (tools/observe.py, specs/002)."""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "tools"))
observe = importlib.import_module("observe")

RAW = (
    "Ich.\r\n"
    '@ut {"type":"token","i":0,"pos":14,"ch":"I","stop":false,"p":0.9,"h":0.1,"us":30,'
    '"top":[["I",0.9],["M",0.05],["G",0.01]]}\r\n'
    '@ut {"type":"token","i":1,"pos":15,"ch":"<eos>","stop":true,"p":1.0,"h":0.0,"us":31,'
    '"top":[["<eos>",1.0],["a",0.0],["b",0.0]]}\r\n'
    '@ut {"type":"answer","n":1,"steps":2,"end":"eos","aborted":false,"prefill":14,'
    '"ctx_used":15,"ctx_len":256,"first_ms":0.03,"total_ms":0.06,"cps":16.0,"ms_avg":0.03,'
    '"ms_min":0.03,"ms_max":0.03,"p_avg":0.95,"p_min":0.9,"p_min_i":0,"h_avg":0.05,'
    '"prof_us":{"embed":1,"ffn":9}}'
)


def test_split_events_separates_json_lines():
    text, events = observe.split_events(RAW)
    assert text == "Ich."
    assert [e["type"] for e in events] == ["token", "token", "answer"]


def test_parse_answer_and_render():
    res = observe.parse_answer(RAW)
    assert res["answer"] == "Ich."
    assert len(res["tokens"]) == 2 and res["summary"]["end"] == "eos"
    lines = observe.render_answer(observe.Style(False), res, "Ich.")
    assert "✓ wie erwartet" in lines[1]
    assert any("Profil" in line for line in lines)


def test_broken_event_line_is_kept_as_text():
    text, events = observe.split_events("x\r\n@ut {kaputt")
    assert events == [] and "@ut {kaputt" in text


HOST = REPO / "build/utiny-host"


@pytest.mark.skipif(not HOST.exists(), reason="needs build/utiny-host (cmake build of runtime/)")
def test_end_to_end_against_host_console():
    from devlib import PROMPT, Device, ExecLink

    model = REPO / "models/starter.utny"
    dev = Device(link=ExecLink([str(HOST), "--model", str(model), "--console"]), timeout=30)
    dev.read_until(PROMPT, timeout=10)
    sess = observe.Session(dev, observe.Style(False), None, stats_each=True)
    sess.command("/trace json")
    res = sess.ask("Wer bist du?")
    assert res["answer"] == "Ich bin UltraTiny, ein kleines Sprachmodell auf einem ESP32."
    assert "".join(t["ch"] for t in res["tokens"] if not t["stop"]) == res["answer"]
    assert res["summary"]["n"] == len(res["answer"])
    assert "System:" in observe.render_sys(
        {"type": "sys", "uptime_ms": 1000, "cpu_load": [None, 5]}
    )
    sess.command("/trace aus")
    assert dev.ask("Wer bist du?") == res["answer"]  # plain output again
    dev.close()
