"""Training loop (research.md R10): MPS (Apple GPU) when available, else CPU.

Writes ckpt.pt and run.json (data-model.md RunMetadata: config, seed, data hash,
git commit, device, wall time) so every run is reproducible (constitution IV).
"""

from __future__ import annotations

import json
import math
import os
import platform
import random
import subprocess
import time
from dataclasses import replace
from pathlib import Path

import numpy as np
import torch
import torch.nn.functional as F

from .alphabet import BOS, EOS, PAD, SEP, Alphabet
from .config import Config, ModelConfig
from .datagen import read_train
from .model import TinyLM


def pick_device(requested: str = "auto") -> torch.device:
    if requested == "cpu":
        return torch.device("cpu")
    mps_ok = getattr(torch.backends, "mps", None) and torch.backends.mps.is_available()
    if requested == "mps":
        if not mps_ok:
            raise RuntimeError("MPS requested but not available")
        return torch.device("mps")
    return torch.device("mps") if mps_ok else torch.device("cpu")


def seed_everything(seed: int, device: torch.device) -> None:
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    if device.type == "mps":
        torch.mps.manual_seed(seed)
    else:
        torch.use_deterministic_algorithms(True)


def git_commit() -> str:
    try:
        out = subprocess.run(
            ["git", "rev-parse", "HEAD"], capture_output=True, text=True, check=True,
            cwd=Path(__file__).parent,
        )  # fmt: skip
        dirty = subprocess.run(
            ["git", "status", "--porcelain"], capture_output=True, text=True,
            cwd=Path(__file__).parent,
        ).stdout.strip()  # fmt: skip
        return out.stdout.strip() + ("-dirty" if dirty else "")
    except (OSError, subprocess.CalledProcessError):
        return "unknown"


def encode_pairs(pairs: list[tuple[str, str]], ab: Alphabet) -> list[tuple[list[int], int]]:
    """Each example -> (token ids, index of first answer token)."""
    out = []
    for q, a in pairs:
        ids = [BOS, *ab.encode(q), SEP]
        start = len(ids)
        ids += [*ab.encode(a), EOS]
        out.append((ids, start))
    return out


def make_batch(examples, idx, device):
    batch = [examples[i] for i in idx]
    t = max(len(ids) for ids, _ in batch) - 1
    x = torch.full((len(batch), t), PAD, dtype=torch.long)
    y = torch.full((len(batch), t), -100, dtype=torch.long)  # -100 = ignored by the loss
    for b, (ids, start) in enumerate(batch):
        ids_t = torch.tensor(ids, dtype=torch.long)
        n = len(ids) - 1
        x[b, :n] = ids_t[:-1]
        y[b, start - 1 : n] = ids_t[start:]  # loss only on answer tokens + <eos>
    return x.to(device), y.to(device)


def lr_at(step: int, cfg: Config) -> float:
    tc = cfg.train
    if step < tc.warmup_steps:
        return tc.lr * (step + 1) / tc.warmup_steps
    total = max(1, tc.steps + tc.qat_steps - tc.warmup_steps)
    prog = min(1.0, (step - tc.warmup_steps) / total)
    return tc.min_lr + 0.5 * (tc.lr - tc.min_lr) * (1 + math.cos(math.pi * prog))


def model_config_for(cfg: Config, ab: Alphabet) -> ModelConfig:
    return replace(cfg.model, vocab_size=ab.vocab_size)


def train(
    cfg: Config,
    data_dir: Path,
    out_dir: Path,
    seed: int,
    device_name: str = "auto",
    qat_steps: int | None = None,
    log=print,
) -> dict:
    t0 = time.time()
    device = pick_device(device_name)
    if device.type == "cpu":
        torch.set_num_threads(cfg.train.num_threads)
    seed_everything(seed, device)
    ab = Alphabet()
    mcfg = model_config_for(cfg, ab)
    pairs = read_train(data_dir / "train.txt")
    examples = encode_pairs(pairs, ab)
    model = TinyLM(mcfg, cfg.train.dropout).to(device)
    decay = [p for n, p in model.named_parameters() if p.dim() >= 2]
    no_decay = [p for n, p in model.named_parameters() if p.dim() < 2]
    opt = torch.optim.AdamW(
        [{"params": decay, "weight_decay": cfg.train.weight_decay},
         {"params": no_decay, "weight_decay": 0.0}],
        lr=cfg.train.lr, betas=(0.9, 0.98),
    )  # fmt: skip
    gen = np.random.default_rng(seed)
    losses: list[float] = []

    def run_steps(start: int, stop: int, qat: bool) -> None:
        model.train()
        model.qat = qat
        for step in range(start, stop):
            for g in opt.param_groups:
                g["lr"] = lr_at(step, cfg)
            idx = gen.integers(0, len(examples), size=cfg.train.batch_size)
            x, y = make_batch(examples, idx, device)
            logits = model(x)
            loss = F.cross_entropy(logits.reshape(-1, logits.size(-1)), y.reshape(-1))
            opt.zero_grad(set_to_none=True)
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), cfg.train.grad_clip)
            opt.step()
            losses.append(float(loss.detach()))
            if step % 100 == 0 or step == stop - 1:
                tag = " (qat)" if qat else ""
                log(f"step {step:6d}  loss {np.mean(losses[-100:]):.4f}{tag}")

    run_steps(0, cfg.train.steps, qat=False)

    # Quantization-aware fine-tuning only if int8 numerics cost > qat_trigger_pp points
    # (research.md R10). Compared with greedy decoding: float vs. fake-quant model.
    qat_steps = cfg.train.qat_steps if qat_steps is None else qat_steps
    qat_check = None
    if qat_steps > 0:
        probe = read_probe(data_dir)
        acc_f = greedy_accuracy(model, probe, ab, mcfg, device, qat=False)
        acc_q = greedy_accuracy(model, probe, ab, mcfg, device, qat=True)
        drop_pp = 100.0 * (acc_f - acc_q)
        qat_check = {"float": acc_f, "fake_quant": acc_q, "drop_pp": round(drop_pp, 2)}
        log(f"quantization check: float {acc_f:.3f}, int8 {acc_q:.3f} ({drop_pp:.1f} pp)")
        if drop_pp > cfg.train.qat_trigger_pp:
            run_steps(cfg.train.steps, cfg.train.steps + qat_steps, qat=True)
        else:
            qat_steps = 0
    total = cfg.train.steps + qat_steps
    out_dir.mkdir(parents=True, exist_ok=True)
    state = {k: v.detach().cpu() for k, v in model.state_dict().items()}
    torch.save({"model_config": mcfg.__dict__, "state_dict": state}, out_dir / "ckpt.pt")
    meta = {
        "config": cfg.to_dict(),
        "seed": seed,
        "data_sha256": (data_dir / "dataset.sha256").read_text().strip(),
        "git_commit": git_commit(),
        "device": device.type,
        "torch": torch.__version__,
        "host": platform.platform(),
        "threads": torch.get_num_threads(),
        "steps": total,
        "qat_steps": qat_steps,
        "qat_check": qat_check,
        "final_loss": float(np.mean(losses[-100:])),
        "wall_time_s": round(time.time() - t0, 1),
        "n_params": model.n_params(),
        "train_examples": len(examples),
        "date": time.strftime("%Y-%m-%d"),
    }
    (out_dir / "run.json").write_text(json.dumps(meta, indent=2, ensure_ascii=False) + "\n")
    (out_dir / "loss.txt").write_text("\n".join(f"{v:.5f}" for v in losses) + "\n")
    return meta


def read_probe(data_dir: Path, n: int = 200) -> list[tuple[str, str]]:
    """Small fixed set (demo + held-out) for the quantization check."""
    rows = []
    for name in ("demo.jsonl", "heldout.jsonl"):
        p = data_dir / name
        if p.exists():
            rows += [json.loads(x) for x in p.read_text(encoding="utf-8").splitlines() if x]
    return [(r["prompt"], r["expected"]) for r in rows[:n]]


@torch.no_grad()
def greedy_accuracy(model, probe, ab: Alphabet, mcfg: ModelConfig, device, qat: bool) -> float:
    if not probe:
        return 0.0
    model.eval()
    model.qat = qat
    good = 0
    for q, expected in probe:
        ids = [BOS, *ab.encode(q), SEP]
        out: list[int] = []
        while len(ids) < mcfg.ctx_len and len(out) < 200:
            nxt = int(model(torch.tensor([ids], device=device))[0, -1].argmax())
            if nxt == EOS:
                break
            out.append(nxt)
            ids.append(nxt)
        good += ab.decode(out) == expected
    model.qat = False
    return good / len(probe)


def load_checkpoint(path: Path) -> tuple[ModelConfig, dict[str, np.ndarray]]:
    ck = torch.load(path, map_location="cpu", weights_only=True)
    mcfg = ModelConfig(**ck["model_config"])
    state = {k: v.float().numpy() for k, v in ck["state_dict"].items()}
    return mcfg, state


os.environ.setdefault("PYTORCH_ENABLE_MPS_FALLBACK", "1")  # CPU fallback for unsupported ops
