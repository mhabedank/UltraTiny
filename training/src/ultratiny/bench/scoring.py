"""Scoring of visible answers and KPI aggregation (research R5, contracts/result-format.md).

Every answer is scored on the text the board prints (spec FR-007). Values are recognised from the
suite's reference facts: the known values of a value class are all fact values of the properties in
that class; numbers use a numeric pattern. A fact answer is

    refused     it contains one of the suite's refusal forms
    wrong_fact  it contains a known value of the question's value classes that is not accepted
    correct     it contains an accepted value and no other value of those classes
    no_answer   anything else
"""

from __future__ import annotations

import re
import unicodedata
from collections import defaultdict
from dataclasses import dataclass

from .suite import Item, Suite, ValueClass

CORRECT, WRONG, REFUSED, NO_ANSWER = "correct", "wrong_fact", "refused", "no_answer"
CLASSES = (CORRECT, WRONG, REFUSED, NO_ANSWER)
_NUM = re.compile(r"(?<![\w,.])(\d+(?:[.,]\d+)?)(?![\w])")


def normalize(s: str) -> str:
    return " ".join(unicodedata.normalize("NFC", s).split())


def _num(s: str) -> tuple[float, int] | None:
    s = s.strip().replace(",", ".")
    try:
        v = float(s)
    except ValueError:
        return None
    dec = len(s.split(".")[1]) if "." in s else 0
    return v, dec


def number_matches(answer_tok: str, expected: str, vc: ValueClass) -> bool:
    """Answer number equals the expected value at the answer's precision (≤ the class's decimals).

    "18" and "18,02" both match an expected 18,02; "23" matches 22,99 (rounded answer)."""
    a, e = _num(answer_tok), _num(expected)
    if a is None or e is None:
        return False
    prec = min(a[1], max(vc.decimals, e[1]))
    return round(e[0], prec) == round(a[0], prec) and a[1] <= max(vc.decimals, e[1])


@dataclass
class _Vocab:
    regex: re.Pattern | None
    values: set[str]


class Scorer:
    def __init__(self, suite: Suite):
        self.suite = suite
        self.forms = [normalize(f) for f in suite.refusal_forms if f.strip()]
        values: dict[str, set[str]] = defaultdict(set)
        for f in suite.facts.values():
            vc = suite.class_of(f.property)
            if vc.kind == "vocab" and f.value.strip():
                values[vc.name].add(normalize(f.value))
        self.vocab: dict[str, _Vocab] = {}
        for name, vc in suite.value_classes.items():
            vals = values.get(name, set())
            if vc.kind != "vocab" or not vals:
                self.vocab[name] = _Vocab(None, vals)
                continue
            alts = "|".join(re.escape(v) for v in sorted(vals, key=lambda v: (-len(v), v)))
            flags = 0 if vc.case_sensitive else re.IGNORECASE
            self.vocab[name] = _Vocab(re.compile(rf"(?<!\w)(?:{alts})(?!\w)", flags), vals)
        self.names: dict[str, set[str]] = defaultdict(set)
        for (obj, _), f in suite.facts.items():
            self.names[obj] |= {normalize(obj), normalize(f.object_name)}

    # ---------------------------------------------------------------- pieces

    def refused(self, answer: str) -> bool:
        a = normalize(answer)
        return any(f in a for f in self.forms)

    def found(self, answer: str, cls: str) -> list[str]:
        vc = self.suite.value_classes[cls]
        a = normalize(answer)
        if vc.kind == "number":
            return [m.group(1) for m in _NUM.finditer(a)]
        v = self.vocab[cls]
        return [m.group(0) for m in v.regex.finditer(a)] if v.regex else []

    def _is_accepted(self, tok: str, cls: str, accepted: list[str]) -> bool:
        vc = self.suite.value_classes[cls]
        if vc.kind == "number":
            return any(number_matches(tok, e, vc) for e in accepted)
        if vc.case_sensitive:
            return normalize(tok) in accepted
        return normalize(tok).lower() in {e.lower() for e in accepted}

    # ---------------------------------------------------------------- items

    def classify_fact(self, item: Item, answer: str) -> str:
        if self.refused(answer):
            return REFUSED
        accepted: dict[str, list[str]] = defaultdict(list)
        subjects: set[str] = set()
        for prop, obj in item.expected:
            v = self.suite.value(obj, prop)
            acc = accepted[self.suite.class_of(prop).name]  # creates the class entry
            if v is not None:
                acc.append(normalize(v))
            subjects |= self.names.get(obj, set())
        hit = other = False
        for cls, acc in accepted.items():
            for tok in self.found(answer, cls):
                if self._is_accepted(tok, cls, acc):
                    hit = True
                elif normalize(tok) not in subjects:  # the question's own object is no wrong value
                    other = True
        if other:
            return WRONG
        return CORRECT if hit else NO_ANSWER

    def classify_other(self, item: Item, answer: str) -> str:
        """explain / refuse / unknown items."""
        if self.refused(answer):
            return REFUSED
        if item.kind == "explain":
            a = normalize(answer)
            ok = len(a) <= self.suite.explain_max and all(
                k.lower() in a.lower() for k in item.keywords
            )
            return CORRECT if ok else NO_ANSWER
        # refuse / unknown: stating any known (non-numeric) value is a wrong fact
        for v in self.vocab.values():
            if v.regex is not None and v.regex.search(normalize(answer)):
                return WRONG
        return NO_ANSWER

    def declined_expected(self, item: Item) -> bool:
        return all(self.suite.value(obj, prop) is None for prop, obj in item.expected)

    def score(self, item: Item, answer: str) -> dict:
        cls = (self.classify_fact if item.kind in ("fact", "multi") else self.classify_other)(
            item, answer
        )
        if item.kind in ("fact", "multi") and self.declined_expected(item):
            ok = cls == REFUSED  # e.g. the ion of a noble gas: "not applicable" is right
        elif item.kind in ("fact", "multi", "explain"):
            ok = cls == CORRECT
        else:
            ok = cls == REFUSED
        return {"class": cls, "ok": ok}


# ---------------------------------------------------------------- KPIs


def _rate(num: int, den: int) -> float | None:
    return round(100.0 * num / den, 1) if den else None


def kpi(value, n=None, detail=None) -> dict:
    """KPI value (data-model.md "KPI value": value, n, detail, status)."""
    out: dict = {"value": value, "status": "measured" if value is not None else "not_measured"}
    if n is not None:
        out["n"] = n
    if detail:
        out["detail"] = detail
    return out


def not_measured(reason: str = "") -> dict:
    d = {"value": None, "status": "not_measured"}
    if reason:
        d["reason"] = reason
    return d


def fact_kpis(items: list[dict]) -> dict:
    """F1-F6 from per-question records (contracts/result-format.md "KPI definitions")."""
    by_set: dict[str, list[dict]] = defaultdict(list)
    for r in items:
        by_set[r["set"]].append(r)
    out: dict = {}
    unseen = [r for r in by_set.get("unseen", []) if r["kind"] in ("fact", "multi")]
    if unseen:
        per: dict[str, list[bool]] = defaultdict(list)
        for r in unseen:
            per[r["type"]].append(r["class"] == CORRECT)
        out["F1"] = kpi(
            _rate(sum(r["class"] == CORRECT for r in unseen), len(unseen)),
            len(unseen),
            {"by_type": {k: _rate(sum(v), len(v)) for k, v in sorted(per.items())}},
        )
        out["F4"] = kpi(_rate(sum(r["class"] == REFUSED for r in unseen), len(unseen)), len(unseen))
    else:
        out["F1"] = out["F4"] = not_measured("no unseen set")
    f2 = unseen + [r for r in by_set.get("kurzarbeit", []) if r["kind"] in ("fact", "multi")]
    out["F2"] = (
        kpi(_rate(sum(r["class"] == WRONG for r in f2), len(f2)), len(f2))
        if f2
        else not_measured("no fact items")
    )
    f3 = by_set.get("unknown", []) + by_set.get("offtopic", [])
    if f3:
        detail = {
            s: _rate(sum(r["class"] == REFUSED for r in by_set[s]), len(by_set[s]))
            for s in ("unknown", "offtopic")
            if by_set.get(s)
        }
        out["F3"] = kpi(
            _rate(sum(r["class"] == REFUSED for r in f3), len(f3)), len(f3), {"by_set": detail}
        )
    else:
        out["F3"] = not_measured("no unknown/offtopic sets")
    ka = by_set.get("kurzarbeit", [])
    if ka:
        per_kind: dict[str, list[bool]] = defaultdict(list)
        for r in ka:
            per_kind[r["kind"]].append(r["ok"])
        out["F5"] = kpi(
            _rate(sum(r["ok"] for r in ka), len(ka)),
            len(ka),
            {"by_kind": {k: _rate(sum(v), len(v)) for k, v in sorted(per_kind.items())}},
        )
    else:
        out["F5"] = not_measured("no short-test set")
    facts = by_set.get("facts", [])
    out["F6"] = (
        kpi(sum(r["class"] == CORRECT for r in facts), len(facts))
        if facts
        else not_measured("no reference facts")
    )
    return out
