"""Board mode with a scripted console and against utiny-host (specs/007 T034, research R8)."""

import json
import shlex
from pathlib import Path

import pytest

from ultratiny.bench import board
from ultratiny.bench.subject import TransformerSubject
from ultratiny.bench.suite import SuiteError, load_suite

ROOT = Path(__file__).parents[2]
MINI = Path(__file__).parent / "fixtures" / "bench_mini"
MODEL = ROOT / "models" / "nodemcu.utny"
HOST = ROOT / "build" / "utiny-host"


class FakeConsole:
    """Minimal serial console: echo, /info, /stats, /trace json, answers with trace lines."""

    def __init__(self, ident, answers, reset_on=None, hang_on=None, wrong_on=None, ctx=104):
        self.ident, self.answers = ident, answers
        self.reset_on, self.hang_on, self.wrong_on, self.ctx = reset_on, hang_on, wrong_on, ctx
        self.out = bytearray(b"\r\nUltraTiny v0 \xe2\x80\x94 " + board.BANNER.encode() + b"\r\n> ")
        self.line = ""
        self.json = False

    def read(self):
        data, self.out = bytes(self.out), bytearray()
        return data

    def close(self):
        pass

    def say(self, s):
        self.out += s.encode()

    def write(self, data):
        for ch in data.decode():
            if ch != "\r":
                self.line += ch
                self.say(ch)
                continue
            line, self.line = self.line, ""
            self.handle(line)

    def handle(self, line):
        i = self.ident
        if line == "/info":
            self.say(
                f"\r\nParameter: {i['params']} | Datei: {i['size']} Bytes | Arena: 35504 Bytes"
                f"\r\nTraining: git {i['git']}, Datum {i['date']}"
                "\r\nLetzte Antwort: erstes Zeichen nach 150 ms, 5.0 Zeichen/s\r\n> "
            )
        elif line.startswith("/trace"):
            self.json = line.endswith("json")
            self.say("\r\nTrace: ok\r\n> ")
        elif line == "/stats":
            sysj = {
                "type": "sys",
                "heap_free": 4960,
                "heap_min": 4500,
                "arena_need": 35504,
                "arena_buf": 36864,
            }
            self.say(
                "\r\n  Heap ok" + (f"\r\n@ut {json.dumps(sysj)}" if self.json else "") + "\r\n> "
            )
        elif line == self.hang_on:
            return
        elif line == self.reset_on:
            self.say(
                "\r\nets Jan  8 2013\r\nUltraTiny v0 \xe2\x80\x94 ".encode("latin1").decode(
                    "latin1"
                )
                + board.BANNER
                + "\r\n> "
            )
        else:
            ans = self.answers.get(line, "?")
            if line == self.wrong_on:
                ans += "x"
            self.say("\r\n" + ans)
            if self.json:
                for k, ch in enumerate(ans):
                    rec = {
                        "type": "token",
                        "i": k,
                        "pos": self.ctx - 20 + k,
                        "ch": ch,
                        "stop": False,
                        "us": 200_000,
                    }
                    self.say("\r\n@ut " + json.dumps(rec))
            self.say("\r\n> ")


@pytest.fixture(scope="module")
def setup():
    suite = load_suite(MINI)
    subj = TransformerSubject(MODEL)
    items, _, _ = board.sample_items(suite, "all")
    answers = {it.question: subj.answer(it.question)[0] for it in items}
    return suite, subj.identity(), answers, items


def run(setup, **kw):
    suite, ident, answers, _ = setup
    dl = board.devlib()
    dev = dl.Device(link=FakeConsole(ident, answers, **kw), timeout=1.0)
    return board.run_board(suite, MODEL, None, dev, "fake", log=lambda *_: None)


def test_clean_run(setup):
    r = run(setup)
    assert r["complete"] and not r["events"]
    assert all(i["parity"] for i in r["items"])
    assert r["kpis"]["T1"]["detail"]["typed"]["median"] == 150
    assert r["kpis"]["T2"]["value"] == 5.0  # 200 ms per step, first character excluded
    assert r["kpis"]["T3"]["value"] == 5.0  # all steps sit at >= 90 % of the context
    det = r["kpis"]["R1"]["detail"]
    assert r["kpis"]["R1"]["value"] == 35504 and det["heap_free_boot"] == 4960


def test_parity_mismatch_reset_and_hang(setup):
    _, _, _, items = setup
    r = run(
        setup, wrong_on=items[0].question, reset_on=items[1].question, hang_on=items[2].question
    )
    assert r["items"][0]["parity"] is False and "pc_answer" in r["items"][0]
    kinds = [e["event"] for e in r["events"]]
    assert "reset" in kinds and "hang" in kinds
    assert r["complete"] is False
    assert any(i.get("parity") for i in r["items"][3:])  # the run went on


def test_identity_mismatch_stops(setup):
    suite, ident, answers, _ = setup
    bad = dict(ident, params=1)
    dl = board.devlib()
    dev = dl.Device(link=FakeConsole(bad, answers), timeout=1.0)
    with pytest.raises(SuiteError, match="params"):
        board.run_board(suite, MODEL, None, dev, "x", log=lambda *_: None)


def test_step_rates():
    recs = [{"type": "token", "pos": p, "us": 100_000, "stop": False} for p in range(90, 100)]
    recs.append({"type": "token", "pos": 100, "us": 1, "stop": True})
    r = board.step_rates(recs, 104)
    assert r["t2"] == pytest.approx(10.0) and r["t3"] == pytest.approx(10.0)
    assert r["t3_steps"] == 6  # positions 94..99 are >= 93.6


@pytest.mark.skipif(not HOST.exists(), reason="build/utiny-host not built")
def test_host_console_parity_with_unknown_character():
    suite = load_suite(MINI)
    dl = board.devlib()
    cmd = f"{HOST} --model {MODEL} --console"
    dev = dl.Device(link=dl.ExecLink(shlex.split(cmd)), timeout=20)
    try:
        r = board.run_board(suite, MODEL, None, dev, "host", mode="parity", log=lambda *_: None)
        subj = TransformerSubject(MODEL)
        q = "Was ist € und Na?"  # '€' is not in the alphabet
        raw = dev.ask(subj.console_text(q))
        ans, _ = board.split_answer(raw)
        assert board.norm_answer(ans) == board.norm_answer(subj.answer(q)[0])
        assert ans == "Na ist das Symbol von Natrium."
    finally:
        dev.close()
    assert all(i["parity"] for i in r["items"]) and len(r["items"]) == 5


def test_demo_merge_and_script_size(tmp_path):
    from ultratiny.bench import demo

    a = {"label": "A", "rows": [{"id": "d/1", "question": "Q|1", "answer": "x", "first_ms": 5}]}
    b = {"label": "B", "rows": [{"id": "d/1", "question": "Q|1", "answer": "y", "first_ms": None}]}
    md = demo.merge_markdown(a, b, "t")
    assert "| 1 | Q\\|1 | x | y | 5 | – |" in md
    bad = tmp_path / "s.tsv"
    bad.write_text("id\tquestion\nd/1\tHallo?\n", encoding="utf-8")
    with pytest.raises(SuiteError, match="10-15"):
        demo.load_script(bad)
    assert len(demo.load_script(ROOT / "bench" / "demo" / "007.tsv")) == 12


@pytest.mark.skipif(not HOST.exists(), reason="build/utiny-host not built")
def test_demo_on_two_host_consoles(tmp_path):
    from ultratiny.bench import demo

    dl = board.devlib()
    script = demo.load_script(ROOT / "bench" / "demo" / "007.tsv")
    runs = []
    for label in ("a", "b"):
        dev = dl.Device(
            link=dl.ExecLink([str(HOST), "--model", str(MODEL), "--console"]), timeout=20
        )
        try:
            runs.append(demo.run_single(dev, script, label))
        finally:
            dev.close()
    assert [r["answer"] for r in runs[0]["rows"]] == [r["answer"] for r in runs[1]["rows"]]
    assert "Paris" in demo.merge_markdown(*runs)
