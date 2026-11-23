"""Hybrid chemistry teacher: data generation, held-back sets and evaluation
(specs/006-hybrid-chemielehrer; contracts/eval-sets.md, data-model.md).

Training pair targets are plain text or FN_CHAR + type letter + key (contracts/function-output.md).
"""

from __future__ import annotations

import csv
import hashlib
import json
import random
import re
from collections import Counter, defaultdict
from pathlib import Path

from . import factgen
from . import facttable as ft
from .alphabet import FN_CHAR, Alphabet
from .augment import load_augment
from .config import Config
from .datagen import (
    TRAINING_ROOT,
    DataError,
    _expand,
    add_noise,
    allowed_source_prefixes,
    load_facts,
)

UT_ANSWER_RESERVE = 32  # runtime/include/utiny_console.h (console caps the question length)
EXPLAIN_MAX = 60  # FR-003
UNKNOWN_TEXT = ft.UNKNOWN.decode()
REFUSAL_ANSWER = "Das weiß ich leider nicht. Frag mich etwas zur Chemie!"
NAME, KEY = "\x02", "\x03"  # placeholders while adding noise (never letters, never lowercased)
FAMILY_SAMPLE = 40  # held-back family prompts per type
TRAINED_SAMPLE = 500

# Made-up compound names for "I don't know" negatives (research R5): no real substance.
_FAKE_A = ["Zorb", "Plax", "Quent", "Morl", "Fendr", "Trox", "Gulb", "Wimp", "Krell", "Dorv",
           "Snarg", "Blix"]  # fmt: skip
_FAKE_B = ["ium", "on", "an", "ol", "it", "ex"]
_FAKE_C = ["chlorid", "oxid", "sulfat", "nitrat", "", "säure", "carbonat"]


def _h(*parts) -> int:
    return int.from_bytes(hashlib.sha256(":".join(map(str, parts)).encode()).digest()[:8], "big")


def norm_q(s: str) -> str:
    return " ".join(re.sub(r"[?.!,]", " ", s.lower()).split())


def _read_tsv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as f:
        return [{k: (v or "").strip() for k, v in row.items()}
                for row in csv.DictReader(f, delimiter="\t", quoting=csv.QUOTE_NONE)]  # fmt: skip


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


# ---------------------------------------------------------------- facts


def build_facts(cfg: Config, out_dir: Path) -> tuple[factgen.FactSet, bytes, dict]:
    """Compute, check and write facts.utft + facts.json (FR-004, FR-005, `ut facts`)."""
    fs = factgen.build(cfg, TRAINING_ROOT)
    errors = factgen.check(fs, Alphabet(fn=True), allowed_source_prefixes())
    if errors:
        raise DataError("fact checks failed:\n" + "\n".join(errors))
    out_dir.mkdir(parents=True, exist_ok=True)
    data = ft.write(fs, out_dir / "facts.utft")
    per_type = Counter(c for _, c in fs.records)
    dump = {
        "objects": {k: {"name": o.name, "kind": o.kind, "source": o.source,
                        "aliases": o.aliases} for k, o in fs.objects.items()},
        "facts": {f"{k}|{c}": v for (k, c), (v, _) in sorted(fs.records.items())},
    }  # fmt: skip
    (out_dir / "facts.json").write_text(json.dumps(dump, ensure_ascii=False, indent=1) + "\n")
    summary = {
        "types": len(fs.types),
        "objects": dict(Counter(o.kind for o in fs.objects.values())),
        "records": len(fs.records),
        "records_per_type": dict(sorted(per_type.items())),
        "bytes": len(data),
        "budget_bytes": ft.MAX_SIZE,
        "sha256": hashlib.sha256(data).hexdigest(),
        "checks": "ok",
    }
    return fs, data, summary


# ---------------------------------------------------------------- combos


def model_key(fs: factgen.FactSet, code: str, key: str) -> str | None:
    t = fs.types[code]
    return fs.value(key, t.reverse_of) if t.reverse_of else key


def combos(fs: factgen.FactSet) -> list[tuple[str, str, str]]:
    """(type, object key, outcome) for every type x object of a matching kind."""
    table = ft.Table(ft.build_bytes(fs))
    out = []
    for code in sorted(fs.types):
        t = fs.types[code]
        for k in sorted(fs.objects):
            if fs.objects[k].kind not in t.kinds:
                continue
            mk = model_key(fs, code, k)
            if not mk:
                continue
            out.append((code, k, table.outcome(code + mk)))
    return out


def hold_combos(fs, all_combos, frac: float, seed: int) -> set[tuple[str, str]]:
    """10 % of real-fact combos; every object keeps >= 3 trained types (or all if it has fewer
    than 4), every type keeps >= 80 % of its objects (data-model.md Held-back sets)."""
    facts = [(c, k) for c, k, o in all_combos if o == "fact"]
    per_obj = Counter(k for _, k in facts)
    per_type = Counter(c for c, _ in facts)
    left_obj, left_type = Counter(per_obj), Counter(per_type)
    target = int(frac * len(facts))
    held: set[tuple[str, str]] = set()
    for c, k in sorted(facts, key=lambda ck: _h(seed, "combo", *ck)):
        if len(held) >= target:
            break
        if per_obj[k] < 4 or left_obj[k] - 1 < 3:
            continue
        if left_type[c] - 1 < 0.8 * per_type[c]:
            continue
        held.add((c, k))
        left_obj[k] -= 1
        left_type[c] -= 1
    return held


def held_families(fs, seed: int) -> dict[str, str]:
    out = {}
    for code, t in sorted(fs.types.items()):
        fams = sorted({f for _, f in t.forms if f != "multi"
                       and sum(1 for _, g in t.forms if g == f) >= 2})  # fmt: skip
        out[code] = fams[_h(seed, "family", code) % len(fams)]
    return out


def fill(form: str, name: str, key: str) -> str:
    return form.replace("{name}", name).replace("{key}", key)


def noisy(form: str, name: str, key: str, rng: random.Random) -> str:
    """Surface noise (research R7): lower case, no punctuation, filler, typo, dropped word -
    never inside the key; names may be lowercased."""
    t = form.replace("{name}", NAME).replace("{key}", KEY)
    q = add_noise(t, rng)
    if (NAME in t and NAME not in q) or (KEY in t and KEY not in q):
        q = t
    if q == q.lower() and rng.random() < 0.7:
        name = name.lower()
    return q.replace(NAME, name).replace(KEY, key)


# ---------------------------------------------------------------- datagen


def generate(cfg: Config, out_dir: Path, seed: int) -> dict:
    d = cfg.data
    rng = random.Random(seed)
    ab = Alphabet(fn=True)
    fs, facts_bytes, facts_summary = build_facts(cfg, out_dir)
    ctx = cfg.model.ctx_len
    max_q = ctx - 2 - UT_ANSWER_RESERVE
    too_long: list[str] = []

    def fits(q: str, a: str) -> bool:
        ok = len(q) <= max_q and len(q) + len(a) + 3 <= ctx and not ab.invalid_chars(q)
        return ok

    # Short-test set (FR-010): pinned, never trained.
    kurz_rows, kurz_status = [], "none"
    if d.kurzarbeit:
        kpath = TRAINING_ROOT / d.kurzarbeit
        digest = sha256_file(kpath)
        if d.kurzarbeit_sha256 and digest != d.kurzarbeit_sha256:
            raise DataError(f"{d.kurzarbeit} changed (sha256 {digest}); re-pin kurzarbeit_sha256 "
                            "after the review")  # fmt: skip
        kurz_status = "pinned" if d.kurzarbeit_sha256 else "UNPINNED"
        code_of = {t.name: code for code, t in fs.types.items()}
        for r in _read_tsv(kpath):
            exp = [e.strip() for e in r.get("expected", "").replace(";", "|").split("|")]
            exp = [e for e in exp if e]
            if r["kind"] in ("fact", "multi"):
                # Readable form "element_symbol: Na" -> function output "SNa".
                parsed = []
                for e in exp:
                    tname, sep, key = (s.strip() for s in e.partition(":"))
                    if not sep or tname not in code_of or not key:
                        raise DataError(f"{d.kurzarbeit} {r['id']}: expected entry {e!r} must be "
                                        "'<question type name>: <key>'")  # fmt: skip
                    parsed.append(code_of[tname] + key)
                exp = parsed
            kurz_rows.append({"id": r["id"], "prompt": r["question"], "kind": r["kind"],
                              "expected": exp, "grade": r.get("grade", "")})  # fmt: skip
    kurz_norm = {norm_q(r["prompt"]) for r in kurz_rows}

    # Facts: combos, held-back combos and families.
    all_combos = combos(fs)
    held_c = hold_combos(fs, all_combos, d.combo_holdout, seed)
    held_f = held_families(fs, seed)
    fact_lines: list[tuple[str, str]] = []
    heldout_combo, heldout_family = [], []
    per_type_objs: dict[str, list[str]] = defaultdict(list)
    for code, k, outcome in all_combos:
        t = fs.types[code]
        o = fs.objects[k]
        mk = model_key(fs, code, k)
        target = FN_CHAR + code + mk
        names = [o.name] + o.aliases
        trained_forms = [f for f, fam in t.forms if fam != held_f[code]]
        held_forms = [f for f, fam in t.forms if fam == held_f[code]]
        row = {"kind": "fact", "expected": [code + mk], "type": code, "object": k}
        if (code, k) in held_c:
            form = rng.choice(trained_forms)
            heldout_combo.append({**row, "prompt": fill(form, rng.choice(names), mk),
                                  "family": "trained"})  # fmt: skip
            continue
        if outcome == "fact":
            per_type_objs[code].append(k)
        n_forms = d.forms_per_combo if outcome == "fact" else max(1, d.forms_per_combo // 2)
        for form in rng.sample(trained_forms, min(n_forms, len(trained_forms))):
            name = rng.choice(names)
            variants = [fill(form, name, mk)]
            variants += [noisy(form, name, mk, rng) for _ in range(d.noisy_copies)]
            for q in dict.fromkeys(variants):
                fact_lines.append((q, target))
        if outcome == "fact" and held_forms:
            heldout_family.append({**row, "prompt": fill(rng.choice(held_forms),
                                                         rng.choice(names), mk),
                                   "family": held_f[code]})  # fmt: skip
    # cap held-back family prompts per type
    by_type: dict[str, list] = defaultdict(list)
    for r in heldout_family:
        by_type[r["type"]].append(r)
    heldout_family = []
    for code in sorted(by_type):
        rows = by_type[code]
        rng.shuffle(rows)
        heldout_family += rows[:FAMILY_SAMPLE]

    # "I don't know" negatives: made-up compound names (text) and unknown formulas (copied key).
    other_lines: list[tuple[str, str]] = []
    n_neg = max(20, len(fact_lines) // 50)
    real_keys = set(fs.objects)
    for _ in range(n_neg):
        fake = rng.choice(_FAKE_A) + rng.choice(_FAKE_B) + rng.choice(_FAKE_C)
        code = rng.choice(["R", "m", "b"])
        form = rng.choice([f for f, fam in fs.types[code].forms if fam != held_f[code]])
        other_lines.append((fill(form, fake, ""), UNKNOWN_TEXT))
        fk = ""
        while not fk or fk in real_keys:
            fk = rng.choice("JQXZ") + rng.choice("bjqxz") + str(rng.randint(2, 9))
        form = rng.choice([f for f, fam in fs.types["f"].forms if fam != held_f["f"]])
        fact_lines.append((fill(form, "", fk), FN_CHAR + "f" + fk))

    # Short explanations (FR-003, FR-008): reviewed rows only.
    explain_lines: list[tuple[str, str]] = []
    heldout_explain = []
    n_explain_rows = n_unreviewed = 0
    for pat in d.explanations:
        for path in sorted(TRAINING_ROOT.glob(pat)):
            for r in _read_tsv(path):
                if r.get("reviewed", "").lower() != "yes" or r.get("check", "ok") != "ok":
                    n_unreviewed += 1
                    continue
                n_explain_rows += 1
                answer = r["answer"]
                if len(answer) > EXPLAIN_MAX:
                    too_long.append(f"{r['id']}: answer > {EXPLAIN_MAX} chars")
                    continue
                qs = [q.strip() for q in r["questions"].split("|") if q.strip()]
                kws = [w.strip() for w in r.get("keywords", "").split(";") if w.strip()]
                if len(qs) >= 2 and _h(seed, "explain", r["id"]) % 1000 < d.explain_holdout * 1000:
                    heldout_explain.append(
                        {
                            "prompt": qs[-1],
                            "kind": "explain",
                            "expected": kws,
                            "answer": answer,
                            "id": r["id"],
                        }
                    )
                    qs = qs[:-1]  # fmt: skip
                for q in qs:
                    for v in dict.fromkeys([q, add_noise(q, rng)]):
                        if fits(v, answer):
                            explain_lines.append((v, answer))
                        else:
                            too_long.append(f"{r['id']}: {v!r} does not fit ctx {ctx}")

    # Greetings / persona / refusals (free facts) and LLM refusal phrasings.
    heldout_refusal = []
    refusal_texts = {UNKNOWN_TEXT, REFUSAL_ANSWER}
    for f in load_facts(_expand(d.free_facts, TRAINING_ROOT)) if d.free_facts else []:
        qs = [q.strip() for q in f.subject.split("|")]
        if f.relation == d.refusal_relation:
            refusal_texts.add(f.object)
            heldout_refusal.append({"prompt": qs[-1], "kind": "refuse", "expected": []})
            qs = qs[:-1]
        for q in qs:
            other_lines.append((q, f.object))
    aug = load_augment([], [], d.augment_refusals, TRAINING_ROOT)
    for q, _src in aug.refusals:
        if not ab.invalid_chars(q):
            other_lines.append((q, REFUSAL_ANSWER))

    # Mix (research R7) and leak guard.
    def repeat(lines, share):
        if not lines or d.mix_facts <= 0:
            return lines
        want = len(fact_lines) * share / d.mix_facts
        return lines * max(1, round(want / len(lines)))

    held_norm = {norm_q(r["prompt"]) for r in heldout_combo + heldout_family + heldout_explain
                 + heldout_refusal}  # fmt: skip
    lines, dropped_kurz, dropped_held, skipped = [], 0, 0, 0
    mix = (fact_lines + repeat(explain_lines, d.mix_explain)
           + repeat(other_lines, 1.0 - d.mix_facts - d.mix_explain))  # fmt: skip
    for q, a in mix:
        n = norm_q(q)
        if n in kurz_norm:
            dropped_kurz += 1
        elif n in held_norm:
            dropped_held += 1
        elif not fits(q, a):
            skipped += 1
        else:
            lines.append((q, a))
    rng.shuffle(lines)

    trained_pool = [(q, a) for q, a in lines if a.startswith(FN_CHAR) or a in
                    {x for _, x in explain_lines}]  # fmt: skip
    rng.shuffle(trained_pool)
    trained_sample = []
    for q, a in list(dict.fromkeys(trained_pool))[:TRAINED_SAMPLE]:
        if a.startswith(FN_CHAR):
            trained_sample.append({"prompt": q, "kind": "fact", "expected": [a[1:]]})
        else:
            trained_sample.append({"prompt": q, "kind": "explain", "expected": [], "answer": a})

    # Coverage report (SC-006).
    forms_per_type = {c: len(t.forms) for c, t in fs.types.items()}
    families_per_type = {c: len({f for _, f in t.forms}) for c, t in fs.types.items()}
    if len(fs.types) < 20 or min(forms_per_type.values()) < 10:
        raise DataError("SC-006: need >= 20 question types with >= 10 forms each")

    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "train.txt").write_text("".join(f"{q}\t{a}\n" for q, a in lines), encoding="utf-8")
    sets = {
        "heldout_combo.jsonl": heldout_combo,
        "heldout_family.jsonl": heldout_family,
        "heldout_explain.jsonl": heldout_explain,
        "heldout_refusal.jsonl": heldout_refusal,
        "kurzarbeit.jsonl": kurz_rows,
        "trained_sample.jsonl": trained_sample,
        # quantization probe of train.py (prompt -> exact target string)
        "demo.jsonl": [{"prompt": q, "expected": a} for q, a in trained_pool[:200]],
    }
    for name, rows in sets.items():
        with (out_dir / name).open("w", encoding="utf-8") as f:
            for r in rows:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
    heldback = {"seed": seed, "families": held_f, "combos": sorted(map(list, held_c)),
                "kurzarbeit_sha256": sha256_file(TRAINING_ROOT / d.kurzarbeit) if d.kurzarbeit
                else ""}  # fmt: skip
    (out_dir / "heldback.json").write_text(json.dumps(heldback, indent=1) + "\n")
    digest = hashlib.sha256()
    for name in ["train.txt", "facts.utft", "heldback.json", *sets]:
        digest.update((out_dir / name).read_bytes())
    sha = digest.hexdigest()
    (out_dir / "dataset.sha256").write_text(sha + "\n")
    return {
        "facts": facts_summary,
        "types": len(fs.types),
        "forms_min": min(forms_per_type.values()),
        "families_min": min(families_per_type.values()),
        "two_way": ["S/s", "O/o", "R/f"],
        "train_examples": len(lines),
        "lines": {
            "facts": len(fact_lines),
            "explain": len(explain_lines),
            "other": len(other_lines),
        },  # fmt: skip
        "explanations": {"reviewed": n_explain_rows, "unreviewed_skipped": n_unreviewed},
        "heldout": {k.removesuffix(".jsonl"): len(v) for k, v in sets.items()},
        "held_combos": len(held_c),
        "kurzarbeit": kurz_status,
        "dropped_kurzarbeit_match": dropped_kurz,
        "dropped_heldout_match": dropped_held,
        "skipped_too_long": skipped,
        "too_long": too_long[:20],
        "sha256": sha,
    }


# ---------------------------------------------------------------- evaluation


def read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines() if x]


def score(row: dict, tokens: list[int], ab: Alphabet, table: ft.Table,
          refusal_norm: set[str]) -> dict:  # fmt: skip
    """One prediction scored per contracts/eval-sets.md "Scoring"."""
    from .evaluate import is_correct, normalize

    fo = ft.function_output(tokens, ab)
    printed = ft.answer_bytes(tokens, ab, table).decode("utf-8", "replace")
    outcome = table.outcome(fo)
    refused = fo is None and normalize(printed) in refusal_norm
    kind = row["kind"]
    correct = wrong = False
    if kind in ("fact", "multi"):
        exp = row["expected"]
        if fo is not None and fo in exp:
            correct = True
        elif fo is not None and exp:
            canon = ft.answer_bytes(ab.encode(FN_CHAR + exp[0]), ab, table).decode()
            correct = printed == canon
        wrong = not correct and outcome == "fact"
    elif kind == "explain":
        kws = row.get("expected") or []
        if fo is None and len(printed) <= EXPLAIN_MAX and not refused:
            if kws:
                correct = all(k.lower() in printed.lower() for k in kws)
            elif row.get("answer"):
                correct = is_correct(printed, row["answer"], 0.25)
    elif kind == "refuse":
        correct = refused or (fo is not None and outcome in ("unknown", "na"))
    elif kind == "unknown":
        correct = refused or (fo is not None and outcome in ("unknown", "na"))
        wrong = fo is not None and outcome == "fact"
    return {"prompt": row["prompt"], "kind": kind, "expected": row.get("expected"),
            "output": fo if fo is not None else printed, "printed": printed,
            "correct": correct, "wrong_fact": wrong, "refused": refused,
            "type": row.get("type")}  # fmt: skip


def summarize(results: list[dict]) -> dict:
    n = len(results)
    facts = [r for r in results if r["kind"] in ("fact", "multi")]
    out = {"n": n, "accuracy": sum(r["correct"] for r in results) / n if n else 0.0}
    if facts:
        out["wrong_fact"] = sum(r["wrong_fact"] for r in facts) / len(facts)
        out["declined"] = sum(not r["correct"] and not r["wrong_fact"] for r in facts) / len(facts)
    by: dict[str, list] = defaultdict(list)
    for r in results:
        by[r.get("type") or r["kind"]].append(r["correct"])
    out["by_type"] = {k: round(sum(v) / len(v), 3) for k, v in sorted(by.items())}
    return out


def evaluate_sets(model_path: Path, data_dir: Path, facts_bytes: bytes, limit: int | None = None
                  ) -> dict:  # fmt: skip
    from .evaluate import normalize
    from .reference import Reference

    ref = Reference(model_path)
    ab = ref.m.alphabet
    table = ft.Table(facts_bytes)
    max_len = ref.cfg.ctx_len - 3
    refusal_norm = {normalize(UNKNOWN_TEXT), normalize(REFUSAL_ANSWER)}
    report: dict = {}
    all_results: dict[str, list] = {}
    for name in ("trained_sample", "heldout_family", "heldout_combo", "kurzarbeit",
                 "heldout_explain", "heldout_refusal"):  # fmt: skip
        rows = read_jsonl(data_dir / f"{name}.jsonl")[:limit]
        res = []
        for r in rows:
            if len(r["prompt"]) + 3 >= ref.cfg.ctx_len:
                continue
            toks = ref.generate(r["prompt"], max_len=max_len)["tokens"]
            res.append(score(r, toks, ab, table, refusal_norm))
        all_results[name] = res
        report[name] = summarize(res)
    kz = all_results["kurzarbeit"]
    if kz:
        by_kind: dict[str, list] = defaultdict(list)
        for r in kz:
            by_kind[r["kind"]].append(r["correct"])
        report["kurzarbeit"]["by_kind"] = {k: round(sum(v) / len(v), 3) for k, v in by_kind.items()}
    asked = [r for name in ("heldout_family", "heldout_combo", "heldout_explain", "kurzarbeit")
             for r in all_results[name] if r["kind"] in ("fact", "multi", "explain")]  # fmt: skip
    refuse = [r for r in all_results["heldout_refusal"] + kz if r["kind"] == "refuse"]
    report["refusal"] = {
        "refusal_rate": sum(r["correct"] for r in refuse) / len(refuse) if refuse else 0.0,
        "n_refusal": len(refuse),
        "false_refusal": sum(r["refused"] for r in asked) / len(asked) if asked else 0.0,
        "n_asked": len(asked),
    }
    facts_all = [
        r
        for name in ("heldout_family", "heldout_combo", "kurzarbeit")
        for r in all_results[name]
        if r["kind"] in ("fact", "multi", "unknown")
    ]
    report["wrong_fact_all"] = (sum(r["wrong_fact"] for r in facts_all) / len(facts_all)
                                if facts_all else 0.0)  # fmt: skip
    report["_results"] = all_results
    return report


def check_thresholds(report: dict, cfg: Config) -> list[str]:
    e = cfg.eval
    failed = []

    def acc(name):
        return report.get(name, {}).get("accuracy", 0.0), report.get(name, {}).get("n", 0)

    for name, minimum in (
        ("heldout_combo", e.combo_min),
        ("heldout_family", e.family_min),
        ("kurzarbeit", e.kurzarbeit_min),
        ("heldout_explain", e.explain_min),
    ):
        a, n = acc(name)
        if n and a < minimum:
            failed.append(f"{name} {a:.3f} < {minimum}")
    if report.get("wrong_fact_all", 0.0) > e.wrong_fact_max:
        failed.append(f"wrong facts {report['wrong_fact_all']:.3f} > {e.wrong_fact_max}")
    r = report.get("refusal", {})
    if r.get("n_refusal") and r["refusal_rate"] < e.refusal_min:
        failed.append(f"refusal rate {r['refusal_rate']:.3f} < {e.refusal_min}")
    if r.get("n_asked") and r["false_refusal"] > e.false_refusal_max:
        failed.append(f"false refusals {r['false_refusal']:.3f} > {e.false_refusal_max}")
    return failed
