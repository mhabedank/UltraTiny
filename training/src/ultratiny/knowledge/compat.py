"""Compatibility with spec 006 (specs/008-wissens-compiler/research.md R10).

- `export_oracle`: one-off export of every answer the UTFT v1 fact table gave (run once, before
  UTFT v1 was removed; the result is committed as topics/chemie/compat/utft1_answers.tsv).
- `check_compat`: renders the oracle queries through a knowledge image via the legacy letters and
  compares byte for byte; differences must be listed and reviewed in compat/changes.tsv.
"""

from __future__ import annotations

import csv
from pathlib import Path

ORACLE_HEADER = ("letter", "key", "outcome", "answer")
CHANGES_HEADER = ("letter", "key", "old", "new", "reason", "reviewed")


def _tsv_safe(s: str) -> str:
    if "\t" in s or "\n" in s:
        raise ValueError(f"answer contains a tab or newline: {s!r}")
    return s


def read_oracle(path: Path) -> list[dict[str, str]]:
    with open(path, encoding="utf-8", newline="") as f:
        lines = [ln for ln in f if not ln.startswith("#")]
    return list(csv.DictReader(lines, delimiter="\t", quoting=csv.QUOTE_NONE))


def read_changes(path: Path | None) -> dict[tuple[str, str], dict[str, str]]:
    if path is None or not Path(path).exists():
        return {}
    with open(path, encoding="utf-8", newline="") as f:
        lines = [ln for ln in f if not ln.startswith("#")]
    out = {}
    for r in csv.DictReader(lines, delimiter="\t", quoting=csv.QUOTE_NONE):
        out[(r["letter"], r["key"])] = r
    return out


def check_compat(image, oracle_path: Path, changes_path: Path | None) -> dict:
    """Compare every oracle row with the image. Returns counts and the unlisted differences."""
    changes = read_changes(changes_path)
    same, listed, unlisted, unreviewed = 0, 0, [], []
    seen = set()
    for r in read_oracle(oracle_path):
        letter, key = r["letter"], r["key"]
        if letter == "":  # the missing-table row: image-independent firmware text
            continue
        got = image.legacy_answer(letter, key.encode()).decode("utf-8")
        if got == r["answer"]:
            same += 1
            continue
        ch = changes.get((letter, key))
        if (
            ch
            and ch.get("reviewed") == "yes"
            and ch.get("old") == r["answer"]
            and ch.get("new") == got
        ):
            listed += 1
            seen.add((letter, key))
        elif ch and ch.get("reviewed") != "yes":
            unreviewed.append((letter, key, r["answer"], got))
        else:
            unlisted.append((letter, key, r["answer"], got))
    stale = sorted(set(changes) - seen)
    return {
        "same": same,
        "listed": listed,
        "unlisted": unlisted,
        "unreviewed": unreviewed,
        "stale_changes": stale,
    }
