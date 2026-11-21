"""Bit-exact NumPy reference of the on-device math (research.md R4/R5).

Every operation mirrors runtime/src/{mathx,forward}.c in float32, in the same order:
- int8 x int8 -> int32 matmuls (exact), rescaled as ((float)acc * w_scale) * x_scale
- activations quantized per vector right before each matmul (quant.quantize_vector)
- K/V cache in int8 with one float32 scale per position (n_kv_heads = 1)
- RMSNorm / softmax / attention-weighted V sums with *sequential* float32 accumulation
- project-owned exp polynomial (`ut_exp`), no libm transcendental functions
"""

from __future__ import annotations

from pathlib import Path

import numpy as np

from .alphabet import EOS
from .export import ModelFile, read_model
from .quant import quantize_vector

F32 = np.float32

# exp(x) for x <= 0, see runtime/src/mathx.c ut_expf
# Exact float32 constants (hex), identical to the hex literals in mathx.c.
_LOG2E = F32(float.fromhex("0x1.715476p+0"))
_LN2_HI = F32(float.fromhex("0x1.62e4p-1"))
_LN2_LO = F32(float.fromhex("0x1.7f7d1cp-20"))
_EXP_C = [
    F32(float.fromhex("0x1.6c16c2p-10")),  # 1/720
    F32(float.fromhex("0x1.111112p-7")),  # 1/120
    F32(float.fromhex("0x1.555556p-5")),  # 1/24
    F32(float.fromhex("0x1.555556p-3")),  # 1/6
    F32(0.5),
]
_EXP_MIN = F32(-80.0)


def seq_sum(x: np.ndarray, axis: int = 0) -> np.ndarray:
    """Sequential (left-to-right) float32 sum, like a plain C loop."""
    return np.cumsum(np.asarray(x, dtype=F32), axis=axis, dtype=F32).take(-1, axis=axis)


def ut_exp(x: np.ndarray) -> np.ndarray:
    x = np.asarray(x, dtype=F32)
    n = np.floor(x * _LOG2E + F32(0.5)).astype(F32)
    r = (x - n * _LN2_HI).astype(F32)
    r = (r - n * _LN2_LO).astype(F32)
    p = _EXP_C[0]
    for c in _EXP_C[1:]:
        p = (p * r + c).astype(F32)
    p = (p * r + F32(1.0)).astype(F32)
    p = (p * r + F32(1.0)).astype(F32)
    out = np.ldexp(p, n.astype(np.int32)).astype(F32)
    return np.where(x < _EXP_MIN, F32(0.0), out).astype(F32)


def rmsnorm(x: np.ndarray, g: np.ndarray, eps: np.float32) -> np.ndarray:
    ss = seq_sum(x * x)
    ms = F32(ss / F32(x.shape[0]))
    inv = F32(F32(1.0) / np.sqrt(F32(ms + eps)))
    return ((x * inv).astype(F32) * g).astype(F32)


def matvec(w: tuple[np.ndarray, np.ndarray], xq: np.ndarray, xs: np.float32) -> np.ndarray:
    q, s = w
    acc = q.astype(np.int32) @ xq.astype(np.int32)
    return ((acc.astype(F32) * s).astype(F32) * xs).astype(F32)


def qmatvec(w: tuple[np.ndarray, np.ndarray], x: np.ndarray) -> np.ndarray:
    xq, xs = quantize_vector(x)
    return matvec(w, xq, xs)


def softmax(z: np.ndarray) -> np.ndarray:
    m = F32(np.max(z))
    e = ut_exp((z - m).astype(F32))
    total = seq_sum(e)
    return (e / total).astype(F32)


def xorshift32(state: int) -> int:
    x = state & 0xFFFFFFFF
    x ^= (x << 13) & 0xFFFFFFFF
    x ^= x >> 17
    x ^= (x << 5) & 0xFFFFFFFF
    return x


def sample(logits: np.ndarray, temperature: float, state: int) -> tuple[int, int]:
    """Returns (token, new_state). Mirrors ut_sample in forward.c."""
    z = (logits / F32(temperature)).astype(F32)
    m = F32(np.max(z))
    e = ut_exp((z - m).astype(F32))
    total = seq_sum(e)
    state = xorshift32(state)
    u = F32(F32(state >> 8) * F32(float.fromhex("0x1p-24")))
    target = F32(u * total)
    cum = np.cumsum(e, dtype=F32)
    idx = np.nonzero(cum > target)[0]
    tok = int(idx[0]) if idx.size else len(e) - 1
    return tok, state


class Reference:
    def __init__(self, model: ModelFile | str | Path):
        self.m = model if isinstance(model, ModelFile) else read_model(model)
        c = self.m.cfg
        self.cfg = c
        self.eps = F32(c.norm_eps)
        self.inv_sqrt_hd = F32(F32(1.0) / np.sqrt(F32(c.head_dim)))
        hd = c.head_dim
        self.kq = np.zeros((c.n_layers, c.ctx_len, hd), dtype=np.int8)
        self.ks = np.zeros((c.n_layers, c.ctx_len), dtype=F32)
        self.vq = np.zeros_like(self.kq)
        self.vs = np.zeros_like(self.ks)
        self.pos = 0
        self.logits: np.ndarray | None = None

    def t(self, key: str):
        return self.m.tensors[key]

    def reset(self) -> None:
        self.pos = 0
        self.logits = None

    def rewind(self, n: int) -> None:
        self.pos = max(0, self.pos - n)

    def _row(self, key: str, i: int) -> np.ndarray:
        q, s = self.t(key)
        return (q[i].astype(F32) * s[i]).astype(F32)

    def feed(self, token: int) -> np.ndarray:
        c = self.cfg
        if self.pos >= c.ctx_len:
            raise RuntimeError("context full")
        p = self.pos
        x = (self._row("tok_emb.weight", token) + self._row("pos_emb.weight", p)).astype(F32)
        hd, nh = c.head_dim, c.n_heads
        for li in range(c.n_layers):
            pre = f"blocks.{li}."
            h = rmsnorm(x, self.t(pre + "attn_norm.weight")[0], self.eps)
            hq, hs = quantize_vector(h)
            q = matvec(self.t(pre + "wq.weight"), hq, hs)
            k = matvec(self.t(pre + "wk.weight"), hq, hs)
            v = matvec(self.t(pre + "wv.weight"), hq, hs)
            self.kq[li, p], self.ks[li, p] = quantize_vector(k)
            self.vq[li, p], self.vs[li, p] = quantize_vector(v)
            kq = self.kq[li, : p + 1].astype(np.int32)
            ks = self.ks[li, : p + 1]
            vterm = (self.vq[li, : p + 1].astype(F32) * self.vs[li, : p + 1, None]).astype(F32)
            att = np.empty(c.d_model, dtype=F32)
            for head in range(nh):
                qh_q, qh_s = quantize_vector(q[head * hd : (head + 1) * hd])
                acc = kq @ qh_q.astype(np.int32)
                s = ((acc.astype(F32) * qh_s).astype(F32) * ks).astype(F32) * self.inv_sqrt_hd
                pr = softmax(s.astype(F32))
                att[head * hd : (head + 1) * hd] = seq_sum((pr[:, None] * vterm).astype(F32))
            x = (x + qmatvec(self.t(pre + "wo.weight"), att)).astype(F32)
            h = rmsnorm(x, self.t(pre + "ffn_norm.weight")[0], self.eps)
            a = np.maximum(qmatvec(self.t(pre + "w1.weight"), h), F32(0.0)).astype(F32)
            x = (x + qmatvec(self.t(pre + "w2.weight"), a)).astype(F32)
        h = rmsnorm(x, self.t("final_norm.weight")[0], self.eps)
        self.logits = qmatvec(self.t("tok_emb.weight"), h)
        self.pos += 1
        return self.logits

    def generate(
        self,
        prompt: str,
        max_len: int = 200,
        temperature: float | None = None,
        seed: int = 1,
        record_logits: bool = False,
    ) -> dict:
        """Greedy (default) or sampled answer for one prompt, from a fresh context."""
        self.reset()
        ab = self.m.alphabet
        prompt_ids = ab.prompt_ids(prompt)
        if len(prompt_ids) >= self.cfg.ctx_len:
            raise ValueError("prompt too long")
        for tok in prompt_ids:
            logits = self.feed(tok)
        out, all_logits, state = [], [], seed
        while True:
            if record_logits:
                all_logits.append(logits.copy())
            if temperature is None:
                tok = int(np.argmax(logits))
            else:
                tok, state = sample(logits, temperature, state)
            out.append(tok)
            if tok == EOS or len(out) >= max_len or self.pos >= self.cfg.ctx_len:
                break
            logits = self.feed(tok)
        return {
            "prompt_tokens": prompt_ids,
            "tokens": out,
            "text": ab.decode([t for t in out if t != EOS]),
            "logits": all_logits,
        }


def arena_size(cfg) -> int:
    """Bytes of static arena needed; mirrors ut_arena_size() in runtime/src/model.c."""

    def a16(n: int) -> int:
        return (n + 15) & ~15

    kvd = cfg.head_dim * cfg.n_kv_heads
    lt = cfg.n_layers * cfg.ctx_len
    size = 0
    size += 2 * a16(lt * kvd)  # K, V int8
    size += 2 * a16(4 * lt)  # K, V scales
    for n in (cfg.d_model,) * 5 + (kvd, kvd, cfg.d_ff, cfg.vocab_size, cfg.ctx_len):
        size += a16(4 * n)  # x, h, q, att, tmp, k, v, ff, logits, scores
    size += a16(max(cfg.d_model, cfg.d_ff))  # int8 activation buffer
    size += a16(cfg.head_dim)  # int8 per-head query
    return size
