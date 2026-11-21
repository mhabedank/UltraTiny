"""Cross-check: export a baseline qexp checkpoint (char, ReLU, learned positions, int8) to the
real UTNY v1 format and evaluate it with the bit-exact NumPy reference on the same eval subset.
Shows how close the PyTorch fake-quant evaluator in qexp.py is to the production numbers."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import torch

from qexp import REFUSAL, eval_subset, read_jsonl, score
from ultratiny.alphabet import Alphabet
from ultratiny.config import ModelConfig
from ultratiny.export import write_model
from ultratiny.reference import Reference


def main(run: str, data: str) -> int:
    run_p, data_p = Path(run), Path(data)
    ck = torch.load(run_p / "ckpt.pt", map_location="cpu", weights_only=False)
    a = ck["args"]
    assert a["tok"] == "char" and a["ffn"] == "relu" and a["pos"] == "learned"
    assert a["ffn_bits"] == 8 and not a["unique"]
    ab = Alphabet()
    mcfg = ModelConfig(vocab_size=ab.vocab_size, d_model=a["d_model"], n_layers=a["n_layers"],
                       n_heads=a["n_heads"], n_kv_heads=1, d_ff=a["d_ff"],
                       ctx_len=a["ctx_len"])  # fmt: skip
    state = {k: v.float().numpy() for k, v in ck["state"].items() if not k.startswith("cls.")}
    path = run_p / "model.utny"
    size = write_model(path, mcfg, state, ab, {"name": "qexp-baseline"})
    ref = Reference(path)
    held = eval_subset(read_jsonl(data_p / "heldout.jsonl"))
    demo = read_jsonl(data_p / "demo.jsonl")
    refusal_text = next(r["expected"] for r in held if r["relation"] == REFUSAL)
    out = {"model_bytes": size}
    for name, rows in (("demo", demo), ("held", held)):
        texts = [ref.generate(r["prompt"], max_len=200)["text"] for r in rows]
        out[name] = score(rows, texts, refusal_text)
        print(name, json.dumps({k: v for k, v in out[name].items() if k != "per_rel"}))
    (run_p / "crosscheck.json").write_text(json.dumps(out, indent=1, ensure_ascii=False) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1], sys.argv[2]))
