"""Write runtime test fixtures for the hybrid chemistry teacher (specs/006, tasks T009/T019).

- runtime/tests/fixtures/facts_small.utft: a subset of the real fact table
- runtime/tests/fixtures/facts_cases.tsv: type, key, expected printed bytes (hex) from the Python
  renderer (facttable.answer_bytes), covering forward, reverse, not applicable, unknown key/type
- runtime/tests/fixtures/tiny_v2.utny + tiny_v2_golden.json: a random tiny UTNY v2 model (with
  <fn>) and golden cases incl. the printed text with facts_small.utft

    cd training && uv run python tools/make_runtime_fixtures.py [--check]

--check regenerates the fact fixtures and fails if the committed ones differ (used by pytest);
the tiny model is trained here and only has to agree with its own golden file.
"""

from __future__ import annotations

import argparse
import json
import sys

import numpy as np
import torch

from ultratiny import factgen
from ultratiny import facttable as ft
from ultratiny.alphabet import EOS, FN, Alphabet
from ultratiny.config import ModelConfig, load_config
from ultratiny.datagen import TRAINING_ROOT
from ultratiny.export import write_model
from ultratiny.golden import make_golden
from ultratiny.model import TinyLM

FIXTURES = TRAINING_ROOT.parent / "runtime" / "tests" / "fixtures"
KEYS = ["C", "Cu", "N", "Na", "Ne", "S", "Co", "Og", "La", "Fe", "H2O", "CO", "NaCl", "Al2O3",
        "HCl", "knallgas", "co2"]  # fmt: skip
CASES = [
    ("O", "Cu"),
    ("S", "Na"),
    ("s", "N"),
    ("s", "Co"),
    ("o", "29"),
    ("o", "7"),
    ("o", "200"),
    ("a", "S"),
    ("a", "Fe"),
    ("v", "Na"),
    ("v", "Fe"),
    ("i", "Ne"),
    ("i", "S"),
    ("E", "C"),
    ("E", "Og"),
    ("G", "La"),
    ("R", "Al2O3"),
    ("f", "CO"),
    ("m", "H2O"),
    ("b", "NaCl"),
    ("c", "HCl"),
    ("c", "H2O"),
    ("q", "knallgas"),
    ("t", "co2"),
    ("O", "Xx"),
    ("O", ""),
    ("S", "H2O"),
    ("s", "H2O"),
    ("Q", "Cu"),
    ("-", "Cu"),
    ("O", "Cuu"),
    ("O", "C"),
]


def small_factset() -> factgen.FactSet:
    cfg = load_config(TRAINING_ROOT / "configs" / "chemie-hybrid.toml")
    fs = factgen.build(cfg, TRAINING_ROOT)
    objects = {k: fs.objects[k] for k in KEYS}
    records = {kc: v for kc, v in fs.records.items() if kc[0] in objects}
    return factgen.FactSet(objects, fs.types, records)


def case_tokens(ab: Alphabet, code: str, key: str) -> list[int]:
    head = [FN] if code == "-" else [FN, *ab.encode(code)]
    if code == "-":
        head.append(ab.encode(" ")[0])  # non-letter type character
    return head + ab.encode(key) + [EOS]


# A few question -> target pairs so the tiny model really emits function outputs; the golden file
# then covers forward/reverse lookups, not-applicable, unknown keys and text answers end to end.
TINY_PAIRS = [
    ("Ordnungszahl Kupfer?", "\x01OCu"),
    ("Was ist N?", "\x01sN"),
    ("Hi", "Hallo!"),
    ("Was ist CO?", "\x01fCO"),
    ("Ion von Neon?", "\x01iNe"),
    ("Element 29?", "\x01o29"),
    ("Formel Xyz?", "\x01RXq3"),
    ("Wasser molar?", "\x01mH2O"),
    ("Profil C?", "\x01EC"),
    ("Schalen Eisen?", "\x01hFe"),
    ("Typ Q?", "\x01QCu"),
    ("Wetter?", "Das weiß ich leider nicht."),
]


def train_tiny(ab: Alphabet) -> tuple[TinyLM, ModelConfig]:
    """Tiny v2 model overfitted on TINY_PAIRS (fixture only; not bit-reproducible across torch
    versions, which is fine: the golden file is generated from the written model)."""
    from ultratiny.train import encode_pairs, make_batch

    torch.manual_seed(6)
    torch.set_num_threads(1)
    cfg = ModelConfig(vocab_size=ab.vocab_size, d_model=64, n_layers=2, n_heads=4, d_ff=128,
                      ctx_len=64)  # fmt: skip
    model = TinyLM(cfg)
    ex = encode_pairs(TINY_PAIRS, ab)
    opt = torch.optim.Adam(model.parameters(), lr=3e-3)
    idx = np.arange(len(ex))
    for _ in range(600):
        x, y = make_batch(ex, idx, torch.device("cpu"))
        logits = model(x)
        loss = torch.nn.functional.cross_entropy(logits.reshape(-1, logits.size(-1)), y.reshape(-1))
        opt.zero_grad()
        loss.backward()
        opt.step()
    model.eval()
    return model, cfg


def build() -> dict[str, bytes]:
    fs = small_factset()
    data = ft.build_bytes(fs)
    table = ft.Table(data)
    ab = Alphabet(fn=True)
    lines = ["# code\tkey\texpected (hex); code '-' = non-letter type character"]
    for code, key in CASES:
        out = ft.answer_bytes(case_tokens(ab, code, key), ab, table)
        lines.append(f"{code}\t{key}\t{out.hex()}")
    lines.append(f"MISSING\t\t{ft.MISSING.hex()}")
    files = {"facts_small.utft": data, "facts_cases.tsv": ("\n".join(lines) + "\n").encode()}

    model, cfg = train_tiny(ab)
    state = {k: v.detach().numpy() for k, v in model.state_dict().items()}
    tmp = FIXTURES / ".tiny_v2.tmp"
    write_model(tmp, cfg, state, ab, {"name": "tiny-v2"})
    prompts = [q for q, _ in TINY_PAIRS] + ["Ordnungszahl Eisen?", "abc", "Was ist Na?"]
    golden = make_golden(tmp, prompts, max_len=40, facts_bytes=data)
    files["tiny_v2.utny"] = tmp.read_bytes()
    tmp.unlink()
    files["tiny_v2_golden.json"] = (json.dumps(golden, ensure_ascii=False,
                                               separators=(",", ":")) + "\n").encode()  # fmt: skip
    n_fn = sum(c["tokens"][:1] == [FN] for c in golden["cases"])
    print(f"tiny_v2: {n_fn}/{len(prompts)} golden cases start with <fn>", file=sys.stderr)
    return files


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    a = ap.parse_args()
    files = build()
    bad = []
    for name, data in files.items():
        path = FIXTURES / name
        if a.check and name.startswith("tiny_v2"):
            continue
        if a.check:
            if not path.exists() or path.read_bytes() != data:
                bad.append(name)
        else:
            path.write_bytes(data)
            print(f"wrote {path} ({len(data)} B)")
    if bad:
        print("fixtures out of date: " + ", ".join(bad), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    np.set_printoptions(linewidth=200)
    sys.exit(main())
