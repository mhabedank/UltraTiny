#!/usr/bin/env python3
"""Propose benchmark test questions and S1 topic text with a local LLM (specs/007, T017/T018).

Runs on the DGX Spark via Ollama, like tools/augment_llm.py. Only models allowed by
DATA_LICENSES.md (gemma4:*, gpt-oss:*, qwen3*) are accepted. The LLM only writes *question text*
and *topic prose*; expected answers (`property: object`) come from the request and the suite's
reference facts, never from the LLM (spec FR-006). Output goes to `bench/suites/<suite>/proposals/`
for review; it never writes `sets/` or `text/` directly.

Topic-specific wording (topic, off-topic themes, text themes, S3 prompt kinds) lives in the suite's
`[propose]` section, so this script has no topic knowledge.

    python3 tools/bench_propose_llm.py --suite ../bench/suites/chemie all
    python3 tools/bench_propose_llm.py --suite ../bench/suites/allgemein questions --per-property 20
    subcommands: questions, unknown, offtopic, s3, text, all

Progress is cached in runs/augment_cache/bench_*.jsonl, so an interrupted run resumes.
"""

from __future__ import annotations

import argparse
import random
import re
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import augment_llm as aug  # noqa: E402

from ultratiny.bench.suite import load_suite, norm_q, read_tsv  # noqa: E402

ALLOWED = re.compile(r"^(gemma4|gpt-oss|qwen3)")  # DATA_LICENSES.md "llm"
TEMPLATE_FILES = sorted((ROOT / "data" / "templates").glob("*.toml"))


# ---------------------------------------------------------------- training-data exclusion


def _template_texts() -> list[str]:
    out = []
    for p in TEMPLATE_FILES:
        cfg = tomllib.loads(p.read_text(encoding="utf-8"))
        for group in ("relations", "types"):
            for t in cfg.get(group, {}).values():
                for q in t.get("questions", []) + t.get("forms", []):
                    out.append(q["text"] if isinstance(q, dict) else str(q))
    for r in read_tsv(ROOT / "data" / "augment" / "vorlagen.tsv"):
        out.append(r["text"])
    return out


class Exclusion:
    """Normalised training prompts and template patterns; proposals matching any are dropped."""

    def __init__(self):
        self.exact: set[str] = set()
        self.patterns: list[re.Pattern] = []
        for t in _template_texts():
            n = norm_q(re.sub(r"\{\w+\}", "\x00", t))
            parts = [re.escape(x) for x in n.split("\x00")]
            if len(parts) > 1:
                if len(n.replace("\x00", "").replace(" ", "")) < 6:
                    continue  # e.g. "{subject}" alone: too little fixed text to compare
                self.patterns.append(
                    re.compile("^" + r"(\S+(?: \S+){0,3})".join(parts) + "$")
                )  # a name: <= 4 words
            else:
                self.exact.add(n)
        for r in read_tsv(ROOT / "data" / "augment" / "paraphrasen.tsv"):
            self.exact.add(norm_q(r["phrasing"]))
        for r in read_tsv(ROOT / "data" / "augment" / "abweisen.tsv"):
            self.exact.add(norm_q(r["phrasing"]))
        for p in (ROOT / "data" / "facts").glob("*.tsv"):
            for r in read_tsv(p):
                for q in (r.get("subject") or "").split("|"):
                    if q.strip():
                        self.exact.add(norm_q(q))
        for r in read_tsv(ROOT / "data" / "eval" / "kurzarbeit.tsv"):
            self.exact.add(norm_q(r["question"]))

    def __contains__(self, q: str) -> bool:
        n = norm_q(q)
        return n in self.exact or any(p.match(n) for p in self.patterns)


# ---------------------------------------------------------------- tasks


def _list(llm, prompt: str, kind: str, key: str) -> list[str]:
    res = aug.cached(
        kind, key, lambda: llm.json(prompt, aug.LIST_SCHEMA, salt=key).get("items", [])
    )
    return [c for c in (aug.clean(x, 400) for x in res) if c]


def _filter(cands: list[str], excl: Exclusion, seen: set[str], max_len: int) -> list[str]:
    out = []
    for c in cands:
        n = norm_q(c)
        if len(c) > max_len or c in excl or n in seen:
            continue
        seen.add(n)
        out.append(c)
    return out


# Prompt templates (German, as the questions); `{q}` = an example of the meaning to keep.
P_QUESTIONS = (
    "Thema: {topic}.\nSchreibe {n} verschiedene kurze deutsche Fragen, die genau dasselbe fragen "
    'wie: "{q}"\nVariiere Satzbau und Wortwahl, so wie Schüler oder Prüfungsaufgaben fragen '
    '(z. B. "Nenne ...", "Gib ... an", Kurzformen, auch ohne Fragezeichen). Höchstens {max} '
    'Zeichen. Nenne den Begriff "{term}" wörtlich. Antworte als JSON {{"items": [...]}}.'
)
P_UNKNOWN = (
    "Erfinde {n} Fantasienamen für {what}, die es nicht gibt. Sie sollen echt klingen, aber "
    'erfunden sein. Nur die Namen, als JSON {{"items": [...]}}.'
)
P_OFFTOPIC = (
    'Schreibe {n} kurze deutsche Fragen oder Eingaben zum Thema "{theme}", wie ein Jugendlicher '
    "sie einem kleinen Chatbot schreiben würde. Sie dürfen nichts mit {topic} zu tun haben. "
    'Höchstens {max} Zeichen. Antworte als JSON {{"items": [...]}}.'
)
P_S3 = (
    "Schreibe {n} kurze deutsche Eingaben an einen kleinen Chatbot für {topic}: {kind}. "
    'Höchstens {max} Zeichen. Antworte als JSON {{"items": [...]}}.'
)
P_TEXT = (
    "Schreibe einen sachlichen, gut lesbaren deutschen Absatz (700 bis 900 Zeichen) über "
    '"{theme}" für {audience}. Nur Fließtext, keine Listen, keine Überschrift. '
    'Antworte als JSON {{"items": ["<Absatz>"]}}.'
)
MAX_Q = 70  # console question limit at context 104 (data-model.md Test item.question)


def task_questions(suite, cfg, llm, jl, excl, a) -> list[tuple]:
    rng = random.Random(a.seed)
    by_prop: dict[str, list] = {}
    for (_obj, prop), f in sorted(suite.facts.items()):
        by_prop.setdefault(prop, []).append(f)
    seen: set[str] = set()
    rows = []
    for prop in sorted(by_prop):
        p = suite.properties[prop]
        for f in rng.sample(by_prop[prop], min(a.per_property, len(by_prop[prop]))):
            meaning = p.canonical.format(name=f.object_name, key=f.object)
            term = f.object if p.reverse else f.object_name
            prompt = P_QUESTIONS.format(topic=cfg["topic"], n=a.n, q=meaning, max=MAX_Q, term=term)
            key = f"q|{suite.name}|{prop}|{f.object}|{a.n}"
            cands = _list(llm, prompt, "bench_questions", key)
            cond = f'Bedingung: Die Frage fragt eindeutig dasselbe wie "{meaning}".'
            cands = aug.judge(jl, cond, cands, key)
            for q in _filter(cands, excl, seen, MAX_Q)[: a.keep]:
                rows.append((prop, f.object, q, f"llm:{a.model}"))
    return rows


def task_unknown(suite, cfg, llm, jl, excl, a) -> list[tuple]:
    known = {f.object_name.lower() for f in suite.facts.values()}
    known |= {o.lower() for o, _ in suite.facts}
    prompt = P_UNKNOWN.format(n=a.n_unknown * 2, what=cfg["unknown_objects"])
    cands = _list(llm, prompt, "bench_unknown", f"u|{suite.name}|{a.n_unknown}")
    names = [n for n in cands if n.lower() not in known and len(n) <= 30]
    rng = random.Random(a.seed)
    forms = [p.canonical for p in suite.properties.values() if "{name}" in p.canonical]
    rows, seen = [], set()
    for name in names:
        q = rng.choice(forms).format(name=name, key=name)
        if norm_q(q) not in seen and len(q) <= MAX_Q:
            seen.add(norm_q(q))
            rows.append((q, f"llm:{a.model}"))
    return rows[: a.n_unknown]


def task_offtopic(suite, cfg, llm, jl, excl, a) -> list[tuple]:
    rows, seen = [], set()
    for theme in cfg["offtopic_themes"]:
        prompt = P_OFFTOPIC.format(n=a.n, theme=theme, topic=cfg["topic"], max=MAX_Q)
        key = f"o|{suite.name}|{theme}|{a.n}"
        cands = _list(llm, prompt, "bench_offtopic", key)
        cond = f"Bedingung: Die Eingabe hat nichts mit {cfg['topic']} zu tun."
        cands = aug.judge(jl, cond, cands, key)
        rows += [(q, theme, f"llm:{a.model}") for q in _filter(cands, excl, seen, MAX_Q)[:3]]
    return rows


def task_s3(suite, cfg, llm, jl, excl, a) -> list[tuple]:
    rows, seen = [], set()
    for kind in cfg["s3_kinds"]:
        prompt = P_S3.format(n=a.n, topic=cfg["topic"], kind=kind, max=MAX_Q)
        key = f"s|{suite.name}|{kind}|{a.n}"
        cands = _filter(_list(llm, prompt, "bench_s3", key), excl, seen, MAX_Q)
        rows += [(q, kind, f"llm:{a.model}") for q in cands[:4]]
    return rows


def task_text(suite, cfg, llm, jl, excl, a) -> list[tuple]:
    rows = []
    audience = cfg.get("audience", "Schüler der Klassen 7 bis 10")
    for theme in cfg["text_themes"]:
        prompt = P_TEXT.format(theme=theme, audience=audience)
        key = f"t|{suite.name}|{theme}"

        def ask(p=prompt, k=key):
            return llm.json(p, aug.LIST_SCHEMA, salt=k).get("items", [])

        for para in aug.cached("bench_text", key, ask)[:1]:
            t = "".join(ch for ch in aug.sanitize(para) if ch in aug.AB)
            if len(t) >= 300:
                rows.append((theme, t, f"llm:{a.model}"))
    return rows


TASKS = {
    "questions": (task_questions, ("property", "object", "question", "source")),
    "unknown": (task_unknown, ("question", "source")),
    "offtopic": (task_offtopic, ("question", "theme", "source")),
    "s3": (task_s3, ("question", "kind", "source")),
    "text": (task_text, ("theme", "text", "source")),
}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--suite", required=True)
    ap.add_argument("--host", default="http://localhost:11434")
    ap.add_argument("--model", default="qwen3.6:35b")
    ap.add_argument("--judge-model", default=None)
    ap.add_argument("--no-judge", action="store_true")
    ap.add_argument("--seed", type=int, default=2026)
    ap.add_argument("--n", type=int, default=8, help="candidates per LLM call")
    ap.add_argument("--keep", type=int, default=1, help="questions kept per object")
    ap.add_argument("--per-property", type=int, default=10, help="objects sampled per property")
    ap.add_argument("--n-unknown", type=int, default=50)
    ap.add_argument("task", choices=[*TASKS, "all"])
    a = ap.parse_args(argv)
    for m in (a.model, a.judge_model or a.model):
        if not ALLOWED.match(m):
            print(
                f"bench_propose_llm: model {m!r} is not allowed by DATA_LICENSES.md",
                file=sys.stderr,
            )
            return 2
    suite = load_suite(a.suite, allow_unpinned=True)
    cfg = tomllib.loads((Path(a.suite) / "suite.toml").read_text(encoding="utf-8")).get("propose")
    if not cfg:
        print("bench_propose_llm: suite.toml has no [propose] section", file=sys.stderr)
        return 2
    llm = aug.Ollama(a.host, a.model, a.seed)
    jl = None if a.no_judge else aug.Ollama(a.host, a.judge_model or a.model, a.seed)
    excl = Exclusion()
    out_dir = Path(a.suite) / "proposals"
    for name in TASKS if a.task == "all" else [a.task]:
        fn, cols = TASKS[name]
        rows = fn(suite, cfg, llm, jl, excl, a)
        aug.write_tsv(out_dir / f"{name}.tsv", list(cols), rows)
        aug.log(f"bench_propose_llm: {name}: {len(rows)} rows -> {out_dir / (name + '.tsv')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
