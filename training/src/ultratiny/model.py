"""PyTorch model (research.md R1): decoder-only, character-level transformer.

Tied token embedding (also output head), learned absolute positions, pre-RMSNorm,
multi-query attention (1 shared K/V head), ReLU FFN, no biases.

Optional fake quantization (`model.qat = True`) mirrors the device numerics closely enough
for quantization-aware fine-tuning: int8 per-row weights, int8 per-vector activations
before every matmul, int8 K/V cache. Straight-through estimator for gradients.
"""

from __future__ import annotations

import math

import torch
import torch.nn.functional as F
from torch import nn

from .config import ModelConfig


def _round_ste(x: torch.Tensor) -> torch.Tensor:
    return x + (torch.round(x) - x).detach()


def fq_rows(w: torch.Tensor) -> torch.Tensor:
    scale = w.detach().abs().amax(dim=-1, keepdim=True).clamp_min(1e-12) / 127.0
    return torch.clamp(_round_ste(w / scale), -127, 127) * scale


def fq_vec(x: torch.Tensor) -> torch.Tensor:
    scale = x.detach().abs().amax(dim=-1, keepdim=True).clamp_min(1e-12) / 127.0
    return torch.clamp(_round_ste(x / scale), -127, 127) * scale


class RMSNorm(nn.Module):
    def __init__(self, d: int, eps: float):
        super().__init__()
        self.eps = eps
        self.weight = nn.Parameter(torch.ones(d))

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return x * torch.rsqrt(x.pow(2).mean(-1, keepdim=True) + self.eps) * self.weight


class Block(nn.Module):
    def __init__(self, cfg: ModelConfig, dropout: float = 0.0):
        super().__init__()
        d, hd = cfg.d_model, cfg.head_dim
        self.cfg = cfg
        self.drop = nn.Dropout(dropout)  # training only; inference math is unchanged
        self.attn_norm = RMSNorm(d, cfg.norm_eps)
        self.wq = nn.Linear(d, d, bias=False)
        self.wk = nn.Linear(d, hd * cfg.n_kv_heads, bias=False)
        self.wv = nn.Linear(d, hd * cfg.n_kv_heads, bias=False)
        self.wo = nn.Linear(d, d, bias=False)
        self.ffn_norm = RMSNorm(d, cfg.norm_eps)
        self.w1 = nn.Linear(d, cfg.d_ff, bias=False)
        self.w2 = nn.Linear(cfg.d_ff, d, bias=False)

    def _lin(self, layer: nn.Linear, x: torch.Tensor, qat: bool) -> torch.Tensor:
        if qat:
            return F.linear(fq_vec(x), fq_rows(layer.weight))
        return layer(x)

    def forward(self, x: torch.Tensor, qat: bool) -> torch.Tensor:
        b, t, d = x.shape
        nh, hd = self.cfg.n_heads, self.cfg.head_dim
        h = self.attn_norm(x)
        q = self._lin(self.wq, h, qat).view(b, t, nh, hd).transpose(1, 2)  # b nh t hd
        k = self._lin(self.wk, h, qat)  # b t hd
        v = self._lin(self.wv, h, qat)
        if qat:
            k, v, q = fq_vec(k), fq_vec(v), fq_vec(q)
        k = k.unsqueeze(1)  # b 1 t hd (shared by all heads)
        v = v.unsqueeze(1)
        att = (q @ k.transpose(-1, -2)) / math.sqrt(hd)
        mask = torch.triu(torch.ones(t, t, dtype=torch.bool, device=x.device), 1)
        att = att.masked_fill(mask, float("-inf")).softmax(-1)
        o = (att @ v).transpose(1, 2).reshape(b, t, d)
        x = x + self.drop(self._lin(self.wo, o, qat))
        h = self.ffn_norm(x)
        x = x + self.drop(self._lin(self.w2, F.relu(self._lin(self.w1, h, qat)), qat))
        return x


class TinyLM(nn.Module):
    def __init__(self, cfg: ModelConfig, dropout: float = 0.0):
        super().__init__()
        self.cfg = cfg
        self.qat = False
        self.tok_emb = nn.Embedding(cfg.vocab_size, cfg.d_model)
        self.pos_emb = nn.Embedding(cfg.ctx_len, cfg.d_model)
        self.blocks = nn.ModuleList(Block(cfg, dropout) for _ in range(cfg.n_layers))
        self.final_norm = RMSNorm(cfg.d_model, cfg.norm_eps)
        self.apply(self._init)
        for blk in self.blocks:  # scaled init of residual projections
            nn.init.normal_(blk.wo.weight, std=0.02 / math.sqrt(2 * cfg.n_layers))
            nn.init.normal_(blk.w2.weight, std=0.02 / math.sqrt(2 * cfg.n_layers))

    @staticmethod
    def _init(m: nn.Module) -> None:
        if isinstance(m, (nn.Linear, nn.Embedding)):
            nn.init.normal_(m.weight, std=0.02)

    def forward(self, idx: torch.Tensor) -> torch.Tensor:
        _, t = idx.shape
        pos = torch.arange(t, device=idx.device)
        tok_w = fq_rows(self.tok_emb.weight) if self.qat else self.tok_emb.weight
        pos_w = fq_rows(self.pos_emb.weight) if self.qat else self.pos_emb.weight
        x = tok_w[idx] + pos_w[pos]
        for blk in self.blocks:
            x = blk(x, self.qat)
        h = self.final_norm(x)
        if self.qat:
            h = fq_vec(h)
        return h @ tok_w.t()

    def n_params(self) -> int:
        return sum(p.numel() for p in self.parameters())
