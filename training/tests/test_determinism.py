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


def test_hybrid_datagen_and_training_deterministic(tmp_path):
    """specs/006 FR-015: same config + seed -> identical data, fact table and model."""
    from dataclasses import replace

    from ultratiny import hybrid
    from ultratiny.config import load_config
    from ultratiny.train import train

    cfg = load_config(ROOT / "configs/hybrid-smoke.toml")
    cfg = replace(cfg, train=replace(cfg.train, steps=15, batch_size=8, num_threads=1))
    digests = []
    for name in ("a", "b"):
        out = tmp_path / name
        stats = hybrid.generate(cfg, out / "data", 7)
        train(cfg, out / "data", out, 7, "cpu", log=lambda *_: None)
        state = (out / "ckpt.pt").read_bytes()
        digests.append((stats["sha256"], (out / "data/facts.utft").read_bytes(),
                        hashlib.sha256(state).hexdigest()))  # fmt: skip
    assert digests[0][:2] == digests[1][:2]
    from ultratiny.train import load_checkpoint

    a = load_checkpoint(tmp_path / "a/ckpt.pt")[1]
    b = load_checkpoint(tmp_path / "b/ckpt.pt")[1]
    assert all((a[k] == b[k]).all() for k in a)
