"""Optional LLM-generated augmentation data (specs/003-chemielehrer, DGX Spark workflow).

Three snapshot files (produced by tools/augment_llm.py, committed like the Wikidata snapshot):

- phrasings  TSV  id, phrasing, source            extra train phrasings for free facts
- templates  TSV  relation, text, answer, source  extra train question templates
- refusals   TSV  phrasing, source                extra off-topic inputs for the refusal relation

Everything here is *train-only*. Held-out prompts are never touched, and datagen drops any
augmented question that equals a held-out prompt or maps to a different answer.
"""

from __future__ import annotations

import csv
import glob
import re
from dataclasses import dataclass, field
from pathlib import Path

PLACEHOLDER = re.compile(r"\{(subject|object)\}")

# Typographic characters LLMs like to produce -> alphabet equivalents.
_REPLACE = {
    "„": '"', "“": '"', "”": '"', "‚": "'", "‘": "'", "’": "'", "´": "'", "`": "'",
    "–": "-", "—": "-", "‑": "-", "…": "...", " ": " ", " ": " ",
}  # fmt: skip


def sanitize(text: str) -> str:
    for a, b in _REPLACE.items():
        text = text.replace(a, b)
    return " ".join(text.replace("\t", " ").replace("|", " ").split())


@dataclass
class Augment:
    phrasings: dict[str, list[tuple[str, str]]] = field(default_factory=dict)  # id -> [(q, src)]
    templates: dict[str, list[tuple[str, str | None, str]]] = field(default_factory=dict)
    refusals: list[tuple[str, str]] = field(default_factory=list)

    @property
    def empty(self) -> bool:
        return not (self.phrasings or self.templates or self.refusals)


def _rows(patterns: list[str], base: Path) -> list[dict]:
    rows: list[dict] = []
    for pat in patterns:
        for p in sorted(glob.glob(str(base / pat))):  # optional: no match is fine
            with open(p, encoding="utf-8", newline="") as f:
                rows += list(csv.DictReader(f, delimiter="\t", quoting=csv.QUOTE_NONE))
    return rows


def load_augment(phrasings: list[str], templates: list[str], refusals: list[str],
                 base: Path) -> Augment:  # fmt: skip
    aug = Augment()
    for r in _rows(phrasings, base):
        aug.phrasings.setdefault(r["id"], []).append((r["phrasing"], r["source"]))
    for r in _rows(templates, base):
        aug.templates.setdefault(r["relation"], []).append(
            (r["text"], r.get("answer") or None, r["source"])
        )
    for r in _rows(refusals, base):
        aug.refusals.append((r["phrasing"], r["source"]))
    return aug


# ---------------------------------------------------------------- short explanations (specs/006)

SHORT_MAX = 60  # FR-003: question + answer must fit context 104
_VALUE_TOKEN = re.compile(r"\b[\wÄÖÜäöüß]*\d[\wÄÖÜäöüß]*\b|\b(?:[A-Z][a-z]?\d*){2,}\b")
_QWORDS = {"Was", "Wie", "Warum", "Wieso", "Welche", "Welcher", "Welches", "Wann", "Wo", "Wozu",
           "Erkläre", "Erklär", "Nenne", "Beschreibe", "Definiere", "Gib"}  # fmt: skip


def key_terms(question: str) -> list[str]:
    """Capitalized words of the question that are not question words (topic candidates)."""
    words = re.findall(r"[A-ZÄÖÜ][\wÄÖÜäöüß-]+", question)
    return [w for w in words if w not in _QWORDS]


def check_short_explanation(long_answer: str, short: str, questions: list[str],
                            fact_tokens: set[str], alphabet) -> str:  # fmt: skip
    """Automatic check of an LLM-shortened explanation (research R8, FR-002/FR-008).

    Returns "ok", "to_fact" (the text states a value the fact table holds; the entry becomes a
    factual question instead) or "reject: <reason>".
    """
    if not short or len(short) > SHORT_MAX:
        return f"reject: empty or > {SHORT_MAX} chars"
    if alphabet.invalid_chars(short):
        return "reject: characters outside the alphabet"
    values = set(_VALUE_TOKEN.findall(short))
    if any(v not in long_answer for v in values):
        return "reject: number/formula not in the long answer"
    if values & fact_tokens:
        return "to_fact"
    terms = [t for q in questions[:2] for t in key_terms(q)]
    if terms and not any(t[:5].lower() in short.lower() for t in terms):
        return "reject: key term missing"
    return "ok"
