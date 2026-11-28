#!/usr/bin/env python3
"""Export reference facts for a benchmark suite (specs/007-benchmark-kpi-bericht, research R4).

The export is run once per suite version; its output is reviewed, committed and pinned, so the
benchmark never depends on the fact generator at run time.

    # chemie: the spec 006 fact set (factgen), property names = question type names
    uv run python ../tools/bench_export_facts.py --config configs/chemie-hybrid.toml \
        --out ../bench/suites/chemie/facts.tsv [--canonical]
    # allgemein: the starter facts (capitals, element symbols) in both directions
    uv run python ../tools/bench_export_facts.py --starter data/facts/starter.tsv \
        --out ../bench/suites/allgemein/facts.tsv
    # a compiled topic (specs/008): every answerable fact of the views with a legacy letter;
    # --types maps the letters to the property names of the suite (spec 006 type names)
    uv run python ../tools/bench_export_facts.py --topic ../topics/chemie \
        --types data/templates/hybrid.toml --out /tmp/facts.tsv

`--canonical` prints the first question form of every property as a `canonical = …` line for
suite.toml.
"""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path


def from_factgen(config: Path) -> tuple[list[tuple[str, str, str, str]], dict[str, str]]:
    from ultratiny import factgen
    from ultratiny.config import load_config

    cfg = load_config(config)
    base = Path(config).resolve().parents[1]
    fs = factgen.build(cfg, base)
    rows = []
    for (key, code), (value, _src) in fs.records.items():
        o = fs.objects[key]
        rows.append((key, o.name, fs.types[code].name, value))
    by_code = {t.name: code for code, t in fs.types.items()}
    for key, o in fs.objects.items():
        # value-less types: the answer is the key itself or the name (contracts/function-output.md)
        if o.kind == "element":
            rows.append((key, o.name, fs.types["S"].name, key))
            rows.append((key, o.name, fs.types["s"].name, o.name))
            z = fs.value(key, "O")
            if z:
                rows.append((z, z, fs.types["o"].name, o.name))
                rows.append(
                    (key, o.name, fs.types["E"].name, z)
                )  # profile: scored by atomic number
        elif o.kind == "compound":
            rows.append((key, o.name, fs.types["R"].name, key))
            rows.append((key, o.name, fs.types["f"].name, o.name))
    canonical = {t.name: t.forms[0][0] for t in fs.types.values() if t.forms}
    assert set(canonical) <= set(by_code)
    return rows, canonical


def from_starter(path: Path) -> tuple[list[tuple[str, str, str, str]], dict[str, str]]:
    rows = []
    with open(path, encoding="utf-8", newline="") as f:
        for r in csv.DictReader(f, delimiter="\t"):
            subj, obj = r["subject"], r["object"]
            if r["relation"] == "hauptstadt_von":
                rows.append((subj, subj, "hauptstadt_von", obj))
                rows.append((obj, obj, "hauptstadt_land", subj))
            elif r["relation"] == "element_symbol":
                rows.append((subj, subj, "element_symbol", obj))
                rows.append((obj, obj, "symbol_element", subj))
    canonical = {
        "hauptstadt_von": "Was ist die Hauptstadt von {name}?",
        "hauptstadt_land": "Von welchem Land ist {key} die Hauptstadt?",
        "element_symbol": "Was ist das Symbol von {name}?",
        "symbol_element": "Welches Element hat das Symbol {key}?",
    }
    return rows, canonical


def from_topic(topic_dir: Path, types: Path | None) -> tuple[list[tuple[str, str, str, str]], dict]:
    """Answerable facts of a compiled topic (specs/008 research R13). The expected value is what
    the answer's last slot prints: the value, the key, the name or another relation's value."""
    import tomllib

    from ultratiny.knowledge.compile import build
    from ultratiny.knowledge.image import SL_KEY, SL_NAME, SL_REL, SL_V, Image
    from ultratiny.knowledge.topic import load_topic

    img = Image(build(load_topic(topic_dir))[0])
    names: dict[str, str] = {}
    canonical: dict[str, str] = {}
    if types:
        for code, t in tomllib.loads(types.read_text(encoding="utf-8"))["types"].items():
            names[code] = t["name"]
            canonical[t["name"]] = t["forms"][0]["text"]
    rows = []
    for v in img.views:
        if not v.letter:
            continue
        prop = names.get(v.letter, v.name)
        tpl = img.str(v.template)
        slots = [(i, b) for i, b in enumerate(tpl) if b <= SL_REL and (i == 0 or tpl[i - 1] != SL_REL)]
        last_i, last = slots[-1]
        for key in img.candidate_keys(v):
            outcome, n, items = img._subject(v, key)
            if outcome != "fact":
                continue
            name = img.obj_name(n).decode()
            k = key.decode()
            if last == SL_KEY:
                value = k
            elif last == SL_NAME:
                value = name
            elif last == SL_V:
                value = img.lookup(v, key)[1].decode() if items is None else items[0].decode()
            else:  # {r:relation}
                value = img._single(img.rels[tpl[last_i + 1] - 1], n).decode()
            obj_name = k if v.kind == 1 else name  # reverse: the key is the object (spec 006 rows)
            rows.append((k, obj_name, prop, value))
    return rows, canonical


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--config", help="training config with the spec 006 fact data (chemie)")
    g.add_argument("--starter", help="starter.tsv (allgemein)")
    g.add_argument("--topic", help="topic directory (specs/008), compiled on the fly")
    ap.add_argument("--types", help="with --topic: hybrid.toml mapping letters to property names")
    ap.add_argument("--out", required=True)
    ap.add_argument("--canonical", action="store_true", help="print canonical question lines")
    a = ap.parse_args(argv)
    if a.topic:
        rows, canonical = from_topic(Path(a.topic), Path(a.types) if a.types else None)
    elif a.config:
        rows, canonical = from_factgen(Path(a.config))
    else:
        rows, canonical = from_starter(Path(a.starter))
    seen: dict[tuple[str, str], str] = {}
    for obj, _name, prop, value in rows:
        if (obj, prop) in seen and seen[(obj, prop)] != value:
            print(f"bench_export_facts: conflicting values for {obj} / {prop}", file=sys.stderr)
            return 2
        seen[(obj, prop)] = value
    rows = sorted(set(rows), key=lambda r: (r[2], r[0]))
    with open(a.out, "w", encoding="utf-8", newline="") as f:
        f.write("object\tobject_name\tproperty\tvalue\n")
        for r in rows:
            f.write("\t".join(x.replace("\t", " ") for x in r) + "\n")
    print(
        f"bench_export_facts: {len(rows)} facts, {len({r[2] for r in rows})} properties -> {a.out}"
    )
    if a.canonical:
        for prop in sorted(canonical):
            print(f'[properties.{prop}]\ncanonical = "{canonical[prop]}"')
    return 0


if __name__ == "__main__":
    sys.exit(main())
