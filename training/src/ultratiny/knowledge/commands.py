"""`ut knowledge …` commands (specs/008-wissens-compiler/contracts/cli.md)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

from .compat import check_compat
from .compile import build
from .image import Image
from .topic import TopicError, load_topic

CASES_HEADER = "view\tkey\toutcome\tanswer\n"
UNKNOWN_KEY = b"Xyz"


def _summary(report: dict) -> list[str]:
    s = report["sections"]
    lines = [
        f"topic {report['topic']} (schema {report['schema_version']}): "
        f"{report['objects']} objects in {len(report['classes'])} classes, "
        f"{report['relations']} relations, {report['views']} views",
        f"facts: {report['facts_explicit']} explicit, {report['facts_derived']} derived "
        + (
            "(" + ", ".join(f"{k} {v}" for k, v in report["derived_per_rule"].items()) + ")"
            if report["derived_per_rule"]
            else ""
        ),
        f"answerable facts (F7): {report['answerable']}",
        f"image: {report['bytes']} B of {report['budget_bytes']} B "
        f"({100 * report['bytes'] / report['budget_bytes']:.0f} %), "
        f"{report['bytes_per_answerable']} B per answerable fact (R5)",
        "sections: " + ", ".join(f"{k} {v}" for k, v in s.items()),
    ]
    return lines


def _fail(e: TopicError) -> int:
    for line in e.errors:
        print(line, file=sys.stderr)
    print(f"knowledge: {len(e.errors)} error(s)", file=sys.stderr)
    return 1


def cmd_build(a) -> int:
    try:
        topic = load_topic(a.topic)
        image, report = build(topic)
    except TopicError as e:
        return _fail(e)
    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(image)
    rep_path = out.with_suffix(".build.json")
    rep_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=1, sort_keys=True) + "\n", encoding="utf-8"
    )
    print("\n".join(_summary(report)))
    print(f"knowledge: wrote {out} and {rep_path}")
    return 0


def cmd_check(a) -> int:
    try:
        topic = load_topic(a.topic)
        image, report = build(topic)  # includes every competency question
    except TopicError as e:
        return _fail(e)
    n_q = sum(len(v.questions) for v in topic.views.values())
    print(
        f"knowledge: {topic.id}: build ok, {n_q} competency questions ok, F7 {report['answerable']}"
    )
    if a.image:
        committed = Path(a.image).read_bytes()
        if committed != image:
            print(
                f"knowledge: {a.image} differs from a fresh build; run `ut knowledge build`",
                file=sys.stderr,
            )
            return 1
        print(f"knowledge: {a.image} is current")
    if a.compat:
        if topic.compat_oracle is None:
            print("knowledge: topic has no [compat] oracle", file=sys.stderr)
            return 1
        res = check_compat(Image(image), topic.compat_oracle, topic.compat_changes)
        print(
            f"compat: {res['same']} identical, {res['listed']} listed changes, "
            f"{len(res['unlisted'])} unlisted, {len(res['unreviewed'])} unreviewed, "
            f"{len(res['stale_changes'])} stale change rows"
        )
        bad = res["unlisted"] + res["unreviewed"]
        for letter, key, old, new in bad[:20]:
            print(f"  {letter} {key!r}\n    old: {old}\n    new: {new}", file=sys.stderr)
        if bad or res["stale_changes"]:
            for s in res["stale_changes"][:20]:
                print(f"  stale change row: {s}", file=sys.stderr)
            return 1
    return 0


def make_cases(img: Image) -> list[tuple[str, bytes, str, bytes]]:
    """Golden query cases (contracts/query.md "Cases file"): per view a sample of facts, one
    not-applicable and one unknown key, and every shortened list."""
    cases: list[tuple[str, bytes, str, bytes]] = []
    for v in img.views:
        vid = v.letter or v.name
        keys = img.candidate_keys(v)
        facts = [k for k in keys if img.lookup(v, k)[0] == "fact"]
        nas = [k for k in keys if img.lookup(v, k)[0] == "na"]
        if v.kind != 1:  # not-applicable through an object of another class
            other = [
                img.obj_key(n) for n in range(img.n_objects) if not (v.mask >> img.obj_class(n)) & 1
            ]
            nas += other[:1]
        sample = facts if len(facts) <= 20 else facts[:5] + facts[-5:]
        longs = [k for k in facts if k not in sample and b" weitere" in img.lookup(v, k)[1]]
        chosen = sample + longs + nas[:1] + [UNKNOWN_KEY]
        for k in chosen:
            outcome, _ = img.lookup(v, k)
            cases.append((vid, k, outcome, img.query_view(v, k)))
    return cases


def write_cases(img: Image, path: Path) -> int:
    cases = make_cases(img)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(CASES_HEADER)
        for vid, k, outcome, ans in cases:
            f.write(f"{vid}\t{k.decode()}\t{outcome}\t{ans.decode()}\n")
    return len(cases)


def cmd_cases(a) -> int:
    img = Image(Path(a.image).read_bytes())
    if not img.ok:
        print(f"knowledge: {a.image}: {img.status}", file=sys.stderr)
        return 1
    n = write_cases(img, Path(a.out))
    print(f"knowledge: wrote {n} cases to {a.out}")
    return 0


def cmd_query(a) -> int:
    img = Image(Path(a.image).read_bytes())
    print(img.query(a.query).decode())
    return 0


def add_parser(sub) -> None:
    p = sub.add_parser("knowledge", help="compile and check knowledge images (specs/008)")
    ks = p.add_subparsers(dest="kcmd", required=True)
    q = ks.add_parser("build", help="topic directory -> .utki + .build.json")
    q.add_argument("--topic", required=True)
    q.add_argument("--out", required=True)
    q.set_defaults(func=cmd_build)
    q = ks.add_parser("check", help="build in memory, competency questions, compat")
    q.add_argument("--topic", required=True)
    q.add_argument("--image", help="committed image that must equal a fresh build")
    q.add_argument("--compat", action="store_true", help="compare with the topic's compat oracle")
    q.set_defaults(func=cmd_check)
    q = ks.add_parser("cases", help="golden query cases from the Python reference")
    q.add_argument("--topic", help="(unused, for symmetry)")
    q.add_argument("--image", required=True)
    q.add_argument("--out", required=True)
    q.set_defaults(func=cmd_cases)
    q = ks.add_parser("query", help='one answer, e.g. --query "O Cu"')
    q.add_argument("--image", required=True)
    q.add_argument("--query", required=True)
    q.set_defaults(func=cmd_query)
    from .propose import add_parsers as add_propose

    add_propose(ks)
