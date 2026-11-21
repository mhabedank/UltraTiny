"""Facts x templates -> training / held-out / demo data (contracts/training-cli.md `ut datagen`).

Validation follows data-model.md:
- Fact.id unique; Fact.topic listed in topics.toml; Fact.relation has templates;
  Fact.subject / Fact.object only alphabet characters; Fact.source listed in DATA_LICENSES.md.
- QuestionTemplate.relation matches a Fact.relation; QuestionTemplate.text contains
  {subject} and/or {object}; QuestionTemplate.split in {train, heldout}.
- TrainingExample `<bos> q <sep> a <eos>` must fit ctx_len; answers <= max_answer_len.
"""

from __future__ import annotations

import csv
import glob
import hashlib
import json
import random
import re
import tomllib
from dataclasses import dataclass
from pathlib import Path

from .alphabet import Alphabet
from .config import Config

REPO_ROOT = Path(__file__).resolve().parents[3]
TRAINING_ROOT = Path(__file__).resolve().parents[2]


class DataError(ValueError):
    pass


@dataclass(frozen=True)
class Fact:
    id: str
    topic: str
    relation: str
    subject: str
    object: str
    source: str


@dataclass(frozen=True)
class QTemplate:
    relation: str
    text: str
    split: str
    answer: str | None


@dataclass(frozen=True)
class Relation:
    name: str
    answers: list[str]
    questions: list[QTemplate]
    free: bool
    repeat: int = 1


def _expand(patterns: list[str], base: Path) -> list[Path]:
    out: list[Path] = []
    for p in patterns:
        hits = sorted(glob.glob(str(base / p)))
        if not hits:
            raise DataError(f"no files match {p}")
        out.extend(Path(h) for h in hits)
    return out


def allowed_source_prefixes(licenses_md: Path = REPO_ROOT / "DATA_LICENSES.md") -> set[str]:
    text = licenses_md.read_text(encoding="utf-8")
    return set(re.findall(r"^\|\s*`([a-z0-9_-]+)`\s*\|", text, flags=re.M))


def load_topics(path: Path) -> set[str]:
    return set(tomllib.loads(path.read_text(encoding="utf-8"))["topics"])


def load_facts(paths: list[Path]) -> list[Fact]:
    facts: list[Fact] = []
    for p in paths:
        with p.open(encoding="utf-8", newline="") as f:
            for row in csv.DictReader(f, delimiter="\t", quoting=csv.QUOTE_NONE):
                facts.append(Fact(**{k: (v or "").strip() for k, v in row.items()}))
    return facts


def load_relations(paths: list[Path]) -> dict[str, Relation]:
    rels: dict[str, Relation] = {}
    for p in paths:
        raw = tomllib.loads(p.read_text(encoding="utf-8"))
        for name, r in raw.get("relations", {}).items():
            if name in rels:
                raise DataError(f"relation {name} defined twice")
            qs = [
                QTemplate(name, q["text"], q.get("split", "train"), q.get("answer"))
                for q in r["questions"]
            ]
            rels[name] = Relation(
                name, list(r["answers"]), qs, bool(r.get("free", False)), int(r.get("repeat", 1))
            )
    return rels


def validate(
    facts: list[Fact],
    rels: dict[str, Relation],
    topics: set[str],
    sources: set[str],
    alphabet: Alphabet,
) -> None:
    errors: list[str] = []
    seen: set[str] = set()
    used_relations = {f.relation for f in facts}
    for f in facts:
        if f.id in seen:
            errors.append(f"duplicate Fact.id {f.id}")
        seen.add(f.id)
        if f.topic not in topics:
            errors.append(f"{f.id}: Fact.topic '{f.topic}' not in topics.toml")
        if f.relation not in rels:
            errors.append(f"{f.id}: Fact.relation '{f.relation}' has no templates")
        for name, value in (("subject", f.subject), ("object", f.object)):
            bad = alphabet.invalid_chars(value.replace("|", ""))
            if bad or not value:
                errors.append(f"{f.id}: Fact.{name} invalid characters {sorted(bad)!r}")
        if f.source.split(":", 1)[0] not in sources:
            errors.append(f"{f.id}: Fact.source '{f.source}' not listed in DATA_LICENSES.md")
        if f.relation in rels and rels[f.relation].free and len(f.subject.split("|")) < 2:
            errors.append(f"{f.id}: free fact needs >= 2 question phrasings")
    # The same (normalized) question must never map to two different answers.
    answers_of: dict[str, set[str]] = {}
    for f in facts:
        if f.relation in rels and rels[f.relation].free:
            for q in f.subject.split("|"):
                key = " ".join(re.sub(r"[?.!,]", " ", q.lower()).split())
                answers_of.setdefault(key, set()).add(f.object)
    for key, objs in answers_of.items():
        if len(objs) > 1:
            errors.append(f"question {key!r} has {len(objs)} different answers")
    for r in rels.values():
        if r.name not in used_relations:
            errors.append(f"QuestionTemplate.relation '{r.name}' matches no Fact.relation")
        if not r.answers:
            errors.append(f"relation {r.name}: needs >= 1 answer template")
        for q in r.questions:
            if "{subject}" not in q.text and "{object}" not in q.text:
                errors.append(f"relation {r.name}: template without placeholder: {q.text!r}")
            if q.split not in ("train", "heldout"):
                errors.append(f"relation {r.name}: invalid split {q.split!r}")
            bad = alphabet.invalid_chars(re.sub(r"\{(subject|object)\}", "", q.text))
            if bad:
                errors.append(f"relation {r.name}: invalid chars {sorted(bad)!r} in {q.text!r}")
        if not r.free:
            n_train = sum(q.split == "train" for q in r.questions)
            n_held = sum(q.split == "heldout" for q in r.questions)
            if n_train + n_held < 8 or n_held < 2:
                errors.append(
                    f"relation {r.name}: needs >= 8 question templates incl. >= 2 held out"
                )
    if errors:
        raise DataError("\n".join(errors))


def _fill(t: str, f: Fact, subject: str | None = None) -> str:
    return t.replace("{subject}", subject or f.subject).replace("{object}", f.object)


def qa_pairs(facts: list[Fact], rels: dict[str, Relation]) -> tuple[list, list]:
    """Return (train, heldout) lists of (question, answer, fact_id)."""
    train, held = [], []
    for f in facts:
        r = rels[f.relation]
        if r.free:
            phrasings = [p.strip() for p in f.subject.split("|")]
            answer = _fill(r.answers[0], f)
            for p in phrasings[:-1]:
                train.append((p, answer, f.id))
            held.append((phrasings[-1], answer, f.id))
            continue
        for i, q in enumerate(r.questions):
            ans_t = q.answer or r.answers[i % len(r.answers)]
            pair = (_fill(q.text, f), _fill(ans_t, f), f.id)
            (train if q.split == "train" else held).append(pair)
    return train, held


_LETTER = re.compile(r"[A-Za-zÄÖÜäöüß]")


FILLERS = ["bitte", "mal", "eigentlich", "denn", "genau", "doch", "jetzt", "nochmal"]


def add_noise(q: str, rng: random.Random, protect: tuple[str, ...] = ()) -> str:
    """Character- and word-level noise. Words belonging to `protect` (subject/object) are
    never dropped, so the question keeps its answerable content."""
    ops = ["lower_first", "drop_punct", "typo", "all_lower", "filler", "drop_word"]
    for op in rng.sample(ops, k=rng.choice([1, 2])):
        words = q.split(" ")
        if op == "lower_first" and q:
            q = q[0].lower() + q[1:]
        elif op == "drop_punct" and q and q[-1] in "?.!":
            q = q[:-1]
        elif op == "all_lower":
            q = q.lower()
        elif op == "filler" and len(words) > 1:
            i = rng.randrange(1, len(words))
            q = " ".join(words[:i] + [rng.choice(FILLERS)] + words[i:])
        elif op == "drop_word" and len(words) > 3:
            keep = set(" ".join(protect).replace("?", "").split())
            cand = [i for i, w in enumerate(words[:-1]) if w not in keep]
            if cand:
                i = rng.choice(cand)
                q = " ".join(words[:i] + words[i + 1 :])
        elif op == "typo":
            idx = [i for i in range(len(q) - 1) if _LETTER.match(q[i]) and _LETTER.match(q[i + 1])]
            if idx:
                i = rng.choice(idx)
                q = q[:i] + q[i + 1] + q[i] + q[i + 2 :]
    return q


def generate(cfg: Config, out_dir: Path, seed: int, alphabet: Alphabet | None = None) -> dict:
    alphabet = alphabet or Alphabet()
    base = TRAINING_ROOT
    facts = load_facts(_expand(cfg.data.facts, base))
    rels = load_relations(_expand(cfg.data.templates, base))
    topics = load_topics(base / cfg.data.topics)
    validate(facts, rels, topics, allowed_source_prefixes(), alphabet)

    rng = random.Random(seed)
    train_pairs, held_pairs = qa_pairs(facts, rels)
    max_len = cfg.model.ctx_len

    def fits(q: str, a: str) -> bool:
        return len(q) + len(a) + 3 <= max_len and len(a) <= cfg.data.max_answer_len

    train_lines: list[str] = []
    skipped = 0

    def norm(s: str) -> str:
        return " ".join(re.sub(r"[?.!,]", " ", s.lower()).split())

    # Noisy variants must never reproduce a held-out prompt (would leak into SC-004).
    held_norm = {norm(q) for q, _, _ in held_pairs}
    by_id = {f.id: f for f in facts}
    for q, a, fid in train_pairs:
        f = by_id[fid]
        protect = (f.object,) if rels[f.relation].free else (f.subject, f.object)
        variants = [q] + [add_noise(q, rng, protect) for _ in range(cfg.data.noisy_copies)]
        for v in dict.fromkeys(variants):  # dedupe, keep order
            if v != q and norm(v) in held_norm:
                continue
            if fits(v, a):
                train_lines.extend([f"{v}\t{a}"] * rels[f.relation].repeat)
            else:
                skipped += 1
    rel_of = {f.id: f.relation for f in facts}
    held = [
        {"prompt": q, "expected": a, "fact": fid, "relation": rel_of[fid]}
        for q, a, fid in held_pairs
        if fits(q, a)
    ]

    demo: list[dict] = []
    demo_path = base / cfg.data.demo_prompts
    known_answers = {a for _, a, _ in train_pairs}
    if demo_path.exists():
        with demo_path.open(encoding="utf-8", newline="") as f:
            for row in csv.DictReader(f, delimiter="\t", quoting=csv.QUOTE_NONE):
                if row["expected"] in known_answers and fits(row["prompt"], row["expected"]):
                    demo.append({"prompt": row["prompt"], "expected": row["expected"]})

    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "train.txt").write_text("\n".join(train_lines) + "\n", encoding="utf-8")
    for name, rows in (("heldout.jsonl", held), ("demo.jsonl", demo)):
        with (out_dir / name).open("w", encoding="utf-8") as f:
            for r in rows:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
    digest = hashlib.sha256()
    for name in ("train.txt", "heldout.jsonl", "demo.jsonl"):
        digest.update((out_dir / name).read_bytes())
    sha = digest.hexdigest()
    (out_dir / "dataset.sha256").write_text(sha + "\n")
    return {
        "facts": len(facts),
        "train_examples": len(train_lines),
        "heldout": len(held),
        "demo": len(demo),
        "skipped_too_long": skipped,
        "sha256": sha,
    }


def read_train(path: Path) -> list[tuple[str, str]]:
    pairs = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line:
            q, a = line.split("\t")
            pairs.append((q, a))
    return pairs


def read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines() if x]
