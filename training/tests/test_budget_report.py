"""Budget report board profiles (specs/005-nodemcu-port/contracts/budget-report.md)."""

import json
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SCRIPT = REPO / "tools/budget_report.py"


def run(model: str, board: str, tmp_path: Path) -> tuple[int, dict]:
    out = tmp_path / f"{board}.json"
    r = subprocess.run(
        [sys.executable, str(SCRIPT), "--model", str(REPO / model), "--board", board,
         "--json", str(out)],
        capture_output=True, text=True, check=False,
    )  # fmt: skip
    return r.returncode, json.loads(out.read_text())


def test_nodemcu_model_passes_nodemcu_budget(tmp_path):
    code, rep = run("models/nodemcu.utny", "nodemcu", tmp_path)
    assert code == 0 and rep["ok"] and rep["board"] == "nodemcu"
    assert rep["arena_bytes"]["used"] <= 36 * 1024
    assert rep["mapped_window"]["ok"]


def test_starter_model_fails_nodemcu_arena(tmp_path):
    code, rep = run("models/starter.utny", "nodemcu", tmp_path)
    assert code == 1 and not rep["arena_bytes"]["ok"]


def test_starter_model_passes_legacy_esp32(tmp_path):
    code, rep = run("models/starter.utny", "esp32", tmp_path)
    assert code == 0 and rep["ok"] and rep["board"] == "esp32"


def test_facts_budget_entry(tmp_path):
    """Fact table of a hybrid model (specs/006): <= 90 % of the 64 KB area."""
    facts = REPO / "runtime/tests/fixtures/facts_small.utft"
    out = tmp_path / "f.json"
    r = subprocess.run(
        [sys.executable, str(SCRIPT), "--model", str(REPO / "models/nodemcu.utny"),
         "--facts", str(facts), "--json", str(out)],
        capture_output=True, text=True, check=False,
    )  # fmt: skip
    rep = json.loads(out.read_text())
    assert r.returncode == 0 and rep["facts_bytes"]["ok"]
    big = tmp_path / "big.utft"
    big.write_bytes(b"UTFT" + b"\0" * 60000)
    r = subprocess.run(
        [sys.executable, str(SCRIPT), "--model", str(REPO / "models/nodemcu.utny"),
         "--facts", str(big), "--json", str(out)],
        capture_output=True, text=True, check=False,
    )  # fmt: skip
    assert r.returncode == 1 and not json.loads(out.read_text())["facts_bytes"]["ok"]
