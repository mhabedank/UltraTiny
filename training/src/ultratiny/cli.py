"""`ut` command line (contracts/training-cli.md)."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .alphabet import Alphabet
from .config import load_config
from .datagen import generate, read_jsonl
from .evaluate import evaluate, refusal_metrics
from .export import read_model, write_model
from .golden import write_golden
from .reference import Reference, arena_size

MODEL_BUDGET = 2 * 1024 * 1024
ARENA_BUDGET = 128 * 1024
HEADROOM = 0.10
# NodeMCU budgets (constitution v2.0.0, specs/005 + 006): model area, arena, fact table area.
NODEMCU_MODEL_AREA = 688128
NODEMCU_ARENA_BUDGET = 40 * 1024
NODEMCU_FACTS_AREA = 0x10000


def _common(p: argparse.ArgumentParser) -> None:
    p.add_argument("--seed", type=int, default=1234)
    p.add_argument("--device", choices=["auto", "cuda", "mps", "cpu"], default="auto")


def cmd_datagen(a) -> int:
    cfg = load_config(a.config)
    if cfg.data.hybrid:
        from . import hybrid

        stats = hybrid.generate(cfg, Path(a.out), a.seed)
        print(json.dumps(stats, indent=2, ensure_ascii=False))
        return 0
    stats = generate(cfg, Path(a.out), a.seed)
    print(json.dumps(stats, indent=2))
    return 0


def cmd_train(a) -> int:
    from .train import train  # torch import is slow; only load when needed

    cfg = load_config(a.config)
    meta = train(cfg, Path(a.data), Path(a.out), a.seed, a.device)
    print(f"done in {meta['wall_time_s']} s on {meta['device']}, loss {meta['final_loss']:.4f}")
    return 0


def cmd_export(a) -> int:
    from .train import load_checkpoint

    ckpt = Path(a.ckpt)
    mcfg, state = load_checkpoint(ckpt)
    run_json = ckpt.parent / "run.json"
    run = json.loads(run_json.read_text()) if run_json.exists() else {}
    meta = {
        "name": run.get("config", {}).get("name", "model"),
        "git": run.get("git_commit", "unknown")[:12],
        "date": run.get("date", ""),
        "data": run.get("data_sha256", "")[:12],
        "device": run.get("device", ""),
        "seed": run.get("seed"),
    }
    facts = getattr(a, "facts", None)
    if facts and Path(facts).exists():
        import hashlib

        from .knowledge.image import Image

        data = Path(facts).read_bytes()
        meta["facts"] = hashlib.sha256(data).hexdigest()[:12]
        img = Image(data)
        if img.ok:
            meta["topic"] = img.topic  # model and image must belong to one topic (specs/008 R11)
    size = write_model(Path(a.out), mcfg, state, Alphabet.for_vocab(mcfg.vocab_size), meta)
    print(f"wrote {a.out} ({size} bytes)")
    return 0


def budget_check(model_path: Path) -> dict:
    m = read_model(model_path)
    arena = arena_size(m.cfg)
    report = {
        "model_bytes": m.size,
        "model_budget": MODEL_BUDGET,
        "arena_bytes": arena,
        "arena_budget": ARENA_BUDGET,
        "model_ok": m.size <= MODEL_BUDGET * (1 - HEADROOM),
        "arena_ok": arena <= ARENA_BUDGET * (1 - HEADROOM),
    }
    report["ok"] = report["model_ok"] and report["arena_ok"]
    return report


def cmd_eval(a) -> int:
    ref = Reference(Path(a.model))
    data = Path(a.data)
    out = {}
    for name in ("demo", "heldout"):
        rows = read_jsonl(data / f"{name}.jsonl")
        out[name] = evaluate(ref, rows, limit=a.limit)
        print(f"{name}: {out[name]['accuracy']:.3f} ({out[name]['n']} prompts)")
    target = Path(a.out) if a.out else Path(a.model).with_name("eval.json")
    target.write_text(json.dumps(out, indent=2, ensure_ascii=False) + "\n")
    return 0


def cmd_golden(a) -> int:
    rows = read_jsonl(Path(a.prompts))
    prompts = [r["prompt"] for r in rows][: a.n]
    write_golden(Path(a.model), prompts, Path(a.out), a.max)
    print(f"wrote {a.out} ({len(prompts)} cases)")
    return 0


def budget_check_nodemcu(model_path: Path, facts_path: Path | None) -> dict:
    m = read_model(model_path)
    arena = arena_size(m.cfg)
    facts = facts_path.stat().st_size if facts_path and facts_path.exists() else 0
    report = {
        "board": "nodemcu",
        "model_bytes": m.size,
        "model_budget": NODEMCU_MODEL_AREA,
        "arena_bytes": arena,
        "arena_budget": NODEMCU_ARENA_BUDGET,
        "facts_bytes": facts,
        "facts_budget": NODEMCU_FACTS_AREA,
        "model_ok": m.size <= NODEMCU_MODEL_AREA * (1 - HEADROOM),
        "arena_ok": arena <= NODEMCU_ARENA_BUDGET * (1 - HEADROOM),
        "facts_ok": facts <= NODEMCU_FACTS_AREA * (1 - HEADROOM),
    }
    report["ok"] = report["model_ok"] and report["arena_ok"] and report["facts_ok"]
    return report


def cmd_pipeline_hybrid(a, cfg) -> int:
    """facts -> datagen -> train -> export (v2) -> eval (all sets) -> golden -> budget."""
    from . import hybrid
    from .train import train

    out = Path(a.out)
    data = out / "data"
    print("== facts + datagen")
    stats = hybrid.generate(cfg, data, a.seed)
    print(json.dumps(stats, indent=2, ensure_ascii=False))
    facts_path = out / "knowledge.utki"
    facts_bytes = (data / "knowledge.utki").read_bytes()
    facts_path.write_bytes(facts_bytes)
    print("== train")
    train(cfg, data, out, a.seed, a.device)
    print("== export")
    cmd_export(argparse.Namespace(ckpt=str(out / "ckpt.pt"), out=str(out / "model.utny"),
                                  facts=str(facts_path)))  # fmt: skip
    model = out / "model.utny"
    print("== eval (quantized reference + knowledge image)")
    report = hybrid.evaluate_sets(model, data, facts_bytes)
    results = report.pop("_results")
    for name in ("trained_sample", "heldout_family", "heldout_combo", "kurzarbeit",
                 "heldout_explain"):  # fmt: skip
        r = report[name]
        extra = f", wrong fact {r['wrong_fact']:.3f}" if "wrong_fact" in r else ""
        print(f"{name}: {r['accuracy']:.3f} ({r['n']} prompts{extra})")
    rf = report["refusal"]
    print(f"refusal rate: {rf['refusal_rate']:.3f} ({rf['n_refusal']}), "
          f"false refusals: {rf['false_refusal']:.3f}, wrong facts (all): "
          f"{report['wrong_fact_all']:.3f}")  # fmt: skip
    report["facts"] = stats["facts"]
    report["thresholds"] = {k: v for k, v in vars(cfg.eval).items() if k.endswith(("_min", "_max"))}
    (out / "eval.json").write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n")
    (out / "eval_results.json").write_text(json.dumps(results, ensure_ascii=False) + "\n")
    print("== golden")
    max_q = cfg.model.ctx_len - 2 - hybrid.UT_ANSWER_RESERVE  # the console types these in full
    prompts = [
        r["prompt"]
        for name in ("kurzarbeit", "heldout_family", "heldout_combo", "heldout_refusal")
        for r in hybrid.read_jsonl(data / f"{name}.jsonl")
        if len(r["prompt"]) <= max_q
    ]
    write_golden(model, prompts[: cfg.eval.golden_cases], out / "golden.json",
                 max_len=cfg.model.ctx_len - 3, facts_bytes=facts_bytes)  # fmt: skip
    print("== budget")
    budget = budget_check_nodemcu(model, facts_path)
    (out / "budget.json").write_text(json.dumps(budget, indent=2) + "\n")
    print(json.dumps(budget, indent=2))
    failed = hybrid.check_thresholds(report, cfg)
    if not budget["ok"]:
        failed.append("budget")
    if failed:
        print("FAILED: " + ", ".join(failed), file=sys.stderr)
        return 1
    print("OK")
    return 0


def cmd_pipeline(a) -> int:
    from .train import train

    cfg = load_config(a.config)
    if cfg.data.hybrid:
        return cmd_pipeline_hybrid(a, cfg)
    out = Path(a.out)
    data = out / "data"
    print("== datagen")
    print(json.dumps(generate(cfg, data, a.seed), indent=2))
    print("== train")
    train(cfg, data, out, a.seed, a.device)
    print("== export")
    cmd_export(argparse.Namespace(ckpt=str(out / "ckpt.pt"), out=str(out / "model.utny")))
    model = out / "model.utny"
    print("== eval (quantized reference)")
    ref = Reference(model)
    results = {}
    for name in ("demo", "heldout"):
        rows = read_jsonl(data / f"{name}.jsonl")
        results[name] = evaluate(ref, rows, cfg.eval.max_edit_ratio)
        print(f"{name}: {results[name]['accuracy']:.3f} ({results[name]['n']} prompts)")
    held_rows = read_jsonl(data / "heldout.jsonl")
    ref_m = refusal_metrics(
        results["demo"], results["heldout"], held_rows, cfg.eval.refusal_relation
    )
    if ref_m:
        results["refusal"] = ref_m
        print(
            f"chemistry held-out: {ref_m['chem_heldout']:.3f} ({ref_m['n_chem_heldout']}), "
            f"refusal rate: {ref_m['refusal_rate']:.3f} ({ref_m['n_refusal']}), "
            f"false refusals: {ref_m['false_refusal']:.3f}"
        )
    (out / "eval.json").write_text(json.dumps(results, indent=2, ensure_ascii=False) + "\n")
    print("== golden")
    prompts = [r["prompt"] for r in read_jsonl(data / "demo.jsonl")]
    prompts += [r["prompt"] for r in read_jsonl(data / "heldout.jsonl")]
    write_golden(model, prompts[: cfg.eval.golden_cases], out / "golden.json")
    print("== budget")
    budget = budget_check(model)
    (out / "budget.json").write_text(json.dumps(budget, indent=2) + "\n")
    print(json.dumps(budget, indent=2))
    failed = []
    if results["demo"]["n"] and results["demo"]["accuracy"] < cfg.eval.demo_min:
        failed.append("demo accuracy")
    held_acc = ref_m["chem_heldout"] if ref_m else results["heldout"]["accuracy"]
    if results["heldout"]["n"] and held_acc < cfg.eval.heldout_min:
        failed.append("held-out accuracy")
    if ref_m and ref_m["refusal_rate"] < cfg.eval.refusal_min:
        failed.append("refusal rate")
    if ref_m and ref_m["false_refusal"] > cfg.eval.false_refusal_max:
        failed.append("false refusals")
    if not budget["ok"]:
        failed.append("budget")
    if failed:
        print("FAILED: " + ", ".join(failed), file=sys.stderr)
        return 1
    print("OK")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="ut", description="UltraTiny training toolkit")
    sub = ap.add_subparsers(dest="cmd", required=True)

    from .knowledge.commands import add_parser as add_knowledge

    add_knowledge(sub)

    p = sub.add_parser("datagen")
    p.add_argument("--config", required=True)
    p.add_argument("--out", required=True)
    _common(p)
    p.set_defaults(func=cmd_datagen)

    p = sub.add_parser("train")
    p.add_argument("--config", required=True)
    p.add_argument("--data", required=True)
    p.add_argument("--out", required=True)
    _common(p)
    p.set_defaults(func=cmd_train)

    p = sub.add_parser("export")
    p.add_argument("--ckpt", required=True)
    p.add_argument("--out", required=True)
    p.add_argument("--facts", help="knowledge image whose hash and topic go into the model meta")
    _common(p)
    p.set_defaults(func=cmd_export)

    p = sub.add_parser("eval")
    p.add_argument("--model", required=True)
    p.add_argument("--data", required=True)
    p.add_argument("--out")
    p.add_argument("--limit", type=int)
    _common(p)
    p.set_defaults(func=cmd_eval)

    p = sub.add_parser("golden")
    p.add_argument("--model", required=True)
    p.add_argument("--prompts", required=True, help="jsonl with a 'prompt' field")
    p.add_argument("--out", required=True)
    p.add_argument("--n", type=int, default=32)
    p.add_argument("--max", type=int, default=200)
    _common(p)
    p.set_defaults(func=cmd_golden)

    p = sub.add_parser("pipeline")
    p.add_argument("--config", required=True)
    p.add_argument("--out", required=True)
    _common(p)
    p.set_defaults(func=cmd_pipeline)

    a = ap.parse_args(argv)
    return a.func(a)


if __name__ == "__main__":
    sys.exit(main())
