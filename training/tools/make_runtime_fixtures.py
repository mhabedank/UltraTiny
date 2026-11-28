"""Write runtime test fixtures for the knowledge engine (specs/006 T009/T019, specs/008 T019).

- runtime/tests/fixtures/kb_mini.utki + kb_mini_cases.tsv: the `mini` fixture topic
  (training/tests/fixtures/topics/mini) compiled to UTKI v1, and its golden query cases from the
  Python reference (every view kind, lists, not-applicable, unknown keys)
- runtime/tests/fixtures/tiny_v2.utny + tiny_v2_golden.json: a random tiny UTNY v2 model (with
  <fn>) and golden cases incl. the printed text with the chemistry image (models/chemie.utki)

    cd training && uv run python tools/make_runtime_fixtures.py [--check]

--check regenerates the knowledge fixtures and fails if the committed ones differ (used by
pytest); the tiny model is trained here and only has to agree with its own golden file.
"""

from __future__ import annotations

import argparse
import json
import sys

import numpy as np
import torch

from ultratiny.alphabet import FN, Alphabet
from ultratiny.config import ModelConfig
from ultratiny.datagen import TRAINING_ROOT
from ultratiny.export import write_model
from ultratiny.golden import make_golden
from ultratiny.knowledge.commands import make_cases
from ultratiny.knowledge.compile import build as build_image
from ultratiny.knowledge.image import Image
from ultratiny.knowledge.topic import load_topic
from ultratiny.model import TinyLM

FIXTURES = TRAINING_ROOT.parent / "runtime" / "tests" / "fixtures"
MINI = TRAINING_ROOT / "tests" / "fixtures" / "topics" / "mini"
CHEMIE = TRAINING_ROOT.parent / "topics" / "chemie"


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


def build(train: bool = True) -> dict[str, bytes]:
    data, _ = build_image(load_topic(MINI))
    cases = make_cases(Image(data))
    lines = ["view\tkey\toutcome\tanswer"]
    lines += [f"{v}\t{k.decode()}\t{o}\t{ans.decode()}" for v, k, o, ans in cases]
    files = {"kb_mini.utki": data, "kb_mini_cases.tsv": ("\n".join(lines) + "\n").encode()}
    if not train:
        return files
    ab = Alphabet(fn=True)
    chem, _ = build_image(load_topic(CHEMIE))

    model, cfg = train_tiny(ab)
    state = {k: v.detach().numpy() for k, v in model.state_dict().items()}
    tmp = FIXTURES / ".tiny_v2.tmp"
    write_model(tmp, cfg, state, ab, {"name": "tiny-v2"})
    prompts = [q for q, _ in TINY_PAIRS] + ["Ordnungszahl Eisen?", "abc", "Was ist Na?"]
    golden = make_golden(tmp, prompts, max_len=40, facts_bytes=chem)
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
    ap.add_argument(
        "--kb-only", action="store_true", help="only the knowledge fixtures (no training)"
    )
    a = ap.parse_args()
    files = build(train=not (a.check or a.kb_only))
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
