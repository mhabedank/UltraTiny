"""Build-time reasoning (specs/008-wissens-compiler/research.md R8, data-model.md "Rule").

The board never reasons (FR-009): every rule result and every reverse direction is computed here and
shipped as plain facts or index structures.

- `apply_rules`: class, chain and table rules, repeated until a round adds nothing (fixpoint).
- `check_reverse`: a relation with `reverse = one` must map each value to exactly one subject.
"""

from __future__ import annotations

from dataclasses import dataclass

from .topic import Fact, Topic, TopicError, check_value, parse_number

MAX_ROUNDS = 32
MAX_FACTS = 65535


@dataclass
class Derived:
    """Provenance of a derived fact (data-model.md Fact.origin)."""

    rule: str
    inputs: list[str]


def _index(facts: list[Fact]) -> dict[tuple[str, str], list[Fact]]:
    idx: dict[tuple[str, str], list[Fact]] = {}
    for f in facts:
        idx.setdefault((f.subject, f.relation), []).append(f)
    return idx


def apply_rules(topic: Topic) -> tuple[list[Fact], dict[str, int]]:
    """All facts (explicit + derived) and the number of new facts per rule.

    Raises TopicError on a conflict (FR-007) or when the rule set keeps growing (edge case "rules
    that feed each other")."""
    facts = list(topic.facts)
    idx = _index(facts)
    obj_class = topic.class_of()
    per_rule = {r.id: 0 for r in topic.rules}
    for _round in range(MAX_ROUNDS):
        added = 0
        for rule in topic.rules:
            where = f"schema.toml:[rules.{rule.id}]"
            add = topic.relations[rule.add_relation]
            candidates: list[tuple[str, str, list[Fact]]] = []  # subject, value, inputs
            if rule.kind == "class":
                for f in [f for f in facts if f.relation == rule.if_relation]:
                    if f.subject in rule.except_:
                        continue
                    if rule.equals is not None:
                        ok = f.value == rule.equals
                    else:
                        x, lo, hi = (parse_number(s) for s in (f.value, *rule.between))
                        ok = x is not None and lo is not None and hi is not None and lo <= x <= hi
                    if ok:
                        candidates.append((f.subject, rule.add_value, [f]))
            elif rule.kind == "chain":
                for f in [f for f in facts if f.relation == rule.first]:
                    for g in idx.get((f.value, rule.then), []):
                        candidates.append((f.subject, g.value, [f, g]))
            elif rule.kind == "table":
                for f in [f for f in facts if f.relation == rule.from_]:
                    if f.value in rule.map:
                        candidates.append((f.subject, rule.map[f.value], [f]))
            for subject, value, inputs in candidates:
                if e := check_value(add, value, obj_class):
                    raise TopicError([f"{where}: derived ({subject}, {add.name}, {value}): {e}"])
                existing = idx.get((subject, add.name), [])
                if any(x.value == value for x in existing):
                    continue  # state "same": dropped
                if add.card == "one" and existing:
                    x = existing[0]
                    raise TopicError(
                        [
                            f"{where}: derived ({subject}, {add.name}, {value}) contradicts "
                            f"({subject}, {add.name}, {x.value}) from {x.origin}"
                        ]
                    )
                origin = f"rule {rule.id} from " + ", ".join(i.origin for i in inputs)
                nf = Fact(subject, add.name, value, "computed", origin)
                facts.append(nf)
                idx.setdefault((subject, add.name), []).append(nf)
                per_rule[rule.id] += 1
                added += 1
                if len(facts) > MAX_FACTS:
                    raise TopicError([f"{where}: more than {MAX_FACTS} facts; rules keep growing"])
        if not added:
            return facts, per_rule
    raise TopicError([f"schema.toml:[rules]: no fixpoint after {MAX_ROUNDS} rounds"])


def check_reverse(topic: Topic, facts: list[Fact]) -> None:
    """FR-005: `reverse = one` maps each value to exactly one subject."""
    errors: list[str] = []
    for rel in topic.relations.values():
        if rel.reverse != "one":
            continue
        first: dict[str, Fact] = {}
        for f in facts:
            if f.relation != rel.name:
                continue
            prev = first.get(f.value)
            if prev is not None and prev.subject != f.subject:
                errors.append(
                    f"{f.origin}: relation {rel.name!r} has reverse = one, but value {f.value!r} "
                    f"belongs to {prev.subject} ({prev.origin}) and {f.subject}"
                )
            first.setdefault(f.value, f)
    if errors:
        raise TopicError(errors)
