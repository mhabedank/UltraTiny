"""Proposal generator with a fake LLM (specs/007-benchmark-kpi-bericht T017)."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parents[1] / "tools"))
import augment_llm as aug  # noqa: E402
import bench_propose_llm as bp  # noqa: E402

from ultratiny.bench.suite import read_tsv  # noqa: E402

MINI = Path(__file__).parent / "fixtures" / "bench_mini"


class FakeLLM:
    def __init__(self, *a, **k):
        self.calls = 0

    def json(self, prompt, schema, temperature=0.8, salt=""):
        self.calls += 1
        if "ok" in schema["properties"]:
            return {"ok": list(range(20))}
        if "Fantasienamen" in prompt:
            return {"items": ["Brolmium", "Natrium", "Zavutin"]}
        if "Absatz" in prompt:
            return {"items": ["Ein Absatz über das Thema. " * 20]}
        return {"items": [f"Frage {self.calls} zu {salt[-12:]}?", "Welches Symbol hat Natrium?"]}


@pytest.fixture
def mini_suite(tmp_path, monkeypatch):
    import shutil

    d = tmp_path / "mini"
    shutil.copytree(MINI, d)
    with open(d / "suite.toml", "a", encoding="utf-8") as f:
        f.write(
            '\n[propose]\ntopic = "Test"\nunknown_objects = "Elemente"\n'
            'offtopic_themes = ["Sport"]\n'
            's3_kinds = ["Begrüßungen"]\ntext_themes = ["Atome"]\n'
        )
    monkeypatch.setattr(aug, "CACHE", tmp_path / "cache")
    monkeypatch.setattr(aug, "LOG_FILE", tmp_path / "log.txt")
    monkeypatch.setattr(aug.cached, "stores", {})
    monkeypatch.setattr(aug, "Ollama", FakeLLM)

    class _Ok:
        def close(self):
            pass

    monkeypatch.setattr(bp.urllib.request, "urlopen", lambda *a, **k: _Ok())
    return d


def test_all_tasks_write_proposals(mini_suite):
    assert bp.main(["--suite", str(mini_suite), "--model", "qwen3:8b", "all"]) == 0
    q = read_tsv(mini_suite / "proposals" / "questions.tsv")
    assert q and all(r["source"] == "llm:qwen3:8b" for r in q)
    assert all(
        r["question"] != "Welches Symbol hat Natrium?" for r in q
    )  # training template dropped
    u = read_tsv(mini_suite / "proposals" / "unknown.tsv")
    assert u and not any("Natrium" in r["question"] for r in u)  # known objects are no unknowns
    assert read_tsv(mini_suite / "proposals" / "text.tsv")[0]["theme"] == "Atome"


def test_disallowed_model_is_refused(mini_suite):
    assert bp.main(["--suite", str(mini_suite), "--model", "llama3:8b", "s3"]) == 2


def test_unreachable_ollama_gives_clear_error(mini_suite, monkeypatch, capsys):
    def refuse(*a, **k):
        raise OSError("Connection refused")

    monkeypatch.setattr(bp.urllib.request, "urlopen", refuse)
    assert bp.main(["--suite", str(mini_suite), "--model", "qwen3:8b", "all"]) == 2
    assert "Ollama not reachable" in capsys.readouterr().err
