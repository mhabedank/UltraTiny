"""Two CPU runs with the same seed must produce byte-identical model files (spec US2)."""

import hashlib
import json
from pathlib import Path

from ultratiny.cli import main

ROOT = Path(__file__).resolve().parents[1]


def _run(out: Path) -> str:
    rc = main(["pipeline", "--config", str(ROOT / "configs/tiny-test.toml"), "--out", str(out),
               "--device", "cpu", "--seed", "7"])  # fmt: skip
    assert rc == 0
    meta = json.loads((out / "run.json").read_text())
    assert meta["seed"] == 7 and meta["device"] == "cpu"
    assert meta["git_commit"] and meta["data_sha256"]
    return hashlib.sha256((out / "model.utny").read_bytes()).hexdigest()


def test_pipeline_cpu_runs_are_byte_identical(tmp_path):
    assert _run(tmp_path / "a") == _run(tmp_path / "b")
