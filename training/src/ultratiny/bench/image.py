"""Image-only KPIs of a knowledge image (specs/008-wissens-compiler/research.md R13).

F7 = answerable facts in the image: distinct (view, key) whose lookup outcome is "fact" (R9).
R3 = image bytes, R5 = R3 / F7. All three are deterministic (noise threshold 0) and need no model.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import platform
from pathlib import Path

from . import RESULT_FORMAT, TOOL_VERSION
from .scoring import kpi, not_measured
from .suite import KPI_IDS, Suite

IMAGE_KPIS = ("F7", "R3", "R5")


def answerable(data: bytes) -> int:
    """F7 of an image file (UTKI v1)."""
    from ..knowledge.image import Image

    img = Image(data)
    if not img.ok:
        raise ValueError(f"knowledge image invalid: {img.status}")
    return img.count_answerable()


def run_image(suite: Suite, facts: Path, label: str | None = None, host: str | None = None) -> dict:
    data = Path(facts).read_bytes()
    return image_result(suite, data, answerable(data), Path(facts).name, label or Path(facts).stem,
                        host)  # fmt: skip


def image_result(suite: Suite, data: bytes, f7: int, file: str, label: str,
                 host: str | None = None) -> dict:  # fmt: skip
    from .pc import git_commit

    kpis = {k: not_measured("image-only result") for k in KPI_IDS}
    kpis["F7"] = kpi(f7)
    kpis["R3"] = kpi(len(data))
    kpis["R5"] = kpi(round(len(data) / f7, 2)) if f7 else not_measured("F7 is 0")
    know = {"sha256": hashlib.sha256(data).hexdigest(), "size": len(data), "file": file}
    return {
        "format": RESULT_FORMAT,
        "kind": "image",
        "label": label,
        "complete": True,
        "suite": suite.info(),
        "model": None,
        "knowledge": know,
        "board": None,
        "env": {
            "commit": git_commit(),
            "date": dt.date.today().isoformat(),
            "host": host or platform.node(),
            "tool": TOOL_VERSION,
        },
        "overlap": {},
        "kpis": dict(sorted(kpis.items())),
        "items": [],
        "events": [],
    }
