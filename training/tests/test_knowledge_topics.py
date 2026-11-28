"""Every topic under topics/ (specs/008-wissens-compiler FR-001, SC-004, SC-007).

Parametrised over the directories, so adding a topic needs no change here: it must build, answer
its competency questions, and its committed image and golden cases must equal a fresh build.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from ultratiny.knowledge.commands import CASES_HEADER, make_cases
from ultratiny.knowledge.compile import build
from ultratiny.knowledge.image import Image
from ultratiny.knowledge.topic import load_topic

REPO = Path(__file__).resolve().parents[2]
TOPICS = sorted(p for p in (REPO / "topics").iterdir() if (p / "topic.toml").exists())


@pytest.mark.parametrize("topic_dir", TOPICS, ids=[p.name for p in TOPICS])
def test_topic_builds_and_committed_files_are_current(topic_dir):
    image, report = build(load_topic(topic_dir))  # includes every competency question
    committed = REPO / "models" / f"{topic_dir.name}.utki"
    assert committed.exists(), f"run `make knowledge` for {topic_dir.name}"
    assert committed.read_bytes() == image, f"{committed} is stale; run `make knowledge`"
    cases = REPO / "models" / f"{topic_dir.name}_cases.tsv"
    lines = [CASES_HEADER.rstrip("\n")]
    lines += [f"{v}\t{k.decode()}\t{o}\t{a.decode()}" for v, k, o, a in make_cases(Image(image))]
    assert cases.read_text(encoding="utf-8") == "\n".join(lines) + "\n", f"{cases} is stale"
    assert report["bytes"] <= report["budget_bytes"]
