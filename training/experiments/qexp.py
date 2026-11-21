"""Quality experiments for specs/004-qualitaet (research only, NOT the production path).

Trains small variants of the UltraTiny decoder on the chemistry data produced by
`ut datagen` and evaluates them with int8 fake quantization (same rounding rules as the
device: per-row weights, per-vector activations, per-vector K/V cache). The evaluator is a
PyTorch approximation of the bit-exact reference; it is used only for *relative* comparisons
(a baseline cross-check against `ultratiny.reference` is in the report).

Nothing here changes the UTNY format, the runtime or the firmware.

Flags (all off = identical math to ultratiny.model.TinyLM):
  --tok char|bpe       character alphabet (96) or word-internal BPE learned on train text
  --ffn relu|swiglu    FFN type
  --pos learned|rope   positional encoding
  --unique N           number of distinct blocks (ALBERT-style cyclic sharing), 0 = all
  --ffn-bits 8|4       FFN weight precision (int4 uses group scales, QAT)
  --ema D              evaluate an EMA of the weights (decay D)
  --ls X               label smoothing
  --cls W              auxiliary answer-ID classifier on the <sep> hidden state (loss weight W)
  --kd-teacher PATH    logit distillation from a trained teacher checkpoint of this harness

Decoding modes evaluated on every run: greedy, trie (constrained to known answers),
centroid (nearest answer centroid of the <sep> embedding), cls (if trained),
and confidence thresholds for refusal.
"""

from __future__ import annotations

import argparse
import collections
import json
import math
import random
import sys
import time
from pathlib import Path

import numpy as np
import torch
import torch.nn.functional as F
from torch import nn

from ultratiny.alphabet import BOS, EOS, PAD, SEP, Alphabet
from ultratiny.evaluate import is_correct, normalize

REFUSAL = "abweisen"

# ----------------------------------------------------------------------------- tokenizers


class CharTok:
    def __init__(self):
        self.ab = Alphabet()
        self.vocab_size = self.ab.vocab_size

    def encode(self, s: str) -> list[int]:
        return self.ab.encode(s)

    def decode(self, ids) -> str:
        return self.ab.decode(ids)

    def to_json(self):
        return {"kind": "char"}


class BPETok:
    """Word-internal BPE over the character alphabet (a leading space is part of a word,
    GPT-2 style). Token ids 0..95 are the character alphabet, new merges follow."""

    def __init__(self, merges: list[tuple[int, int]] | None = None):
        self.ab = Alphabet()
        self.base = self.ab.vocab_size
        self.merges = merges or []
        self._build()

    def _build(self):
        self.rank = {pair: i for i, pair in enumerate(self.merges)}
        self.pieces = {i: self.ab.decode([i]) for i in range(self.base)}
        for i, (a, b) in enumerate(self.merges):
            self.pieces[self.base + i] = self.pieces[a] + self.pieces[b]
        self.vocab_size = self.base + len(self.merges)
        self._cache: dict[str, list[int]] = {}

    @staticmethod
    def words(s: str) -> list[str]:
        out, cur = [], ""
        for ch in s:
            if ch == " " and cur:
                out.append(cur)
                cur = " "
            elif ch.isalnum() or ch in "äöüÄÖÜß" or (ch == " " and not cur):
                cur += ch
            else:  # punctuation is its own word
                if cur:
                    out.append(cur)
                out.append(ch)
                cur = ""
        if cur:
            out.append(cur)
        return out

    def learn(self, texts: list[str], vocab_size: int) -> None:
        freq = collections.Counter(w for t in texts for w in self.words(t))
        seqs = {w: self.ab.encode(w) for w in freq}
        self.merges = []
        while self.base + len(self.merges) < vocab_size:
            pairs = collections.Counter()
            for w, ids in seqs.items():
                f = freq[w]
                for a, b in zip(ids, ids[1:], strict=False):
                    pairs[(a, b)] += f
            if not pairs:
                break
            (a, b), n = pairs.most_common(1)[0]
            if n < 2:
                break
            new = self.base + len(self.merges)
            self.merges.append((a, b))
            for w, ids in seqs.items():
                if len(ids) < 2:
                    continue
                out, i = [], 0
                while i < len(ids):
                    if i + 1 < len(ids) and ids[i] == a and ids[i + 1] == b:
                        out.append(new)
                        i += 2
                    else:
                        out.append(ids[i])
                        i += 1
                seqs[w] = out
        self._build()

    def _encode_word(self, w: str) -> list[int]:
        hit = self._cache.get(w)
        if hit is not None:
            return hit
        ids = self.ab.encode(w)
        while len(ids) > 1:
            best, bi = None, -1
            for i in range(len(ids) - 1):
                r = self.rank.get((ids[i], ids[i + 1]))
                if r is not None and (best is None or r < best):
                    best, bi = r, i
            if best is None:
                break
            ids = ids[:bi] + [self.base + best] + ids[bi + 2 :]
        self._cache[w] = ids
        return ids

    def encode(self, s: str) -> list[int]:
        return [i for w in self.words(s) for i in self._encode_word(w)]

    def decode(self, ids) -> str:
        return "".join(self.pieces.get(int(i), "") for i in ids if int(i) >= 5)

    def to_json(self):
        return {"kind": "bpe", "merges": self.merges}


# ----------------------------------------------------------------------------- fake quant


def _round_ste(x):
    return x + (torch.round(x) - x).detach()


def fq_rows(w, bits=8, group=0):
    qmax = 2 ** (bits - 1) - 1
    if group and w.shape[-1] % group == 0:
        shp = w.shape
        g = w.reshape(shp[0], shp[1] // group, group)
        s = g.detach().abs().amax(-1, keepdim=True).clamp_min(1e-12) / qmax
        return (torch.clamp(_round_ste(g / s), -qmax, qmax) * s).reshape(shp)
    s = w.detach().abs().amax(-1, keepdim=True).clamp_min(1e-12) / qmax
    return torch.clamp(_round_ste(w / s), -qmax, qmax) * s


def fq_vec(x):
    s = x.detach().abs().amax(-1, keepdim=True).clamp_min(1e-12) / 127.0
    return torch.clamp(_round_ste(x / s), -127, 127) * s


# ----------------------------------------------------------------------------- model


class RMSNorm(nn.Module):
    def __init__(self, d):
        super().__init__()
        self.weight = nn.Parameter(torch.ones(d))

    def forward(self, x):
        return x * torch.rsqrt(x.pow(2).mean(-1, keepdim=True) + 1e-5) * self.weight


def rope(x, pos, base=10000.0):
    # x: b h t hd ; pos: b t
    hd = x.shape[-1]
    inv = 1.0 / (base ** (torch.arange(0, hd, 2, device=x.device).float() / hd))
    ang = pos[:, None, :, None].float() * inv  # b 1 t hd/2
    c, s = ang.cos(), ang.sin()
    x1, x2 = x[..., 0::2], x[..., 1::2]
    out = torch.stack([x1 * c - x2 * s, x1 * s + x2 * c], -1)
    return out.flatten(-2)


class Block(nn.Module):
    def __init__(self, a, d, dff, dropout):
        super().__init__()
        self.a = a
        hd = d // a.n_heads
        self.attn_norm = RMSNorm(d)
        self.wq = nn.Linear(d, d, bias=False)
        self.wk = nn.Linear(d, hd, bias=False)
        self.wv = nn.Linear(d, hd, bias=False)
        self.wo = nn.Linear(d, d, bias=False)
        self.ffn_norm = RMSNorm(d)
        self.w1 = nn.Linear(d, dff, bias=False)
        self.w2 = nn.Linear(dff, d, bias=False)
        if a.ffn == "swiglu":
            self.w3 = nn.Linear(d, dff, bias=False)
        self.drop = nn.Dropout(dropout)

    def lin(self, layer, x, qat, ffn=False):
        if not qat:
            return layer(x)
        bits = self.a.ffn_bits if ffn else 8
        group = self.a.group if (ffn and bits < 8) else 0
        return F.linear(fq_vec(x), fq_rows(layer.weight, bits, group))

    def forward(self, x, pos, qat, cache=None, mask=None):
        b, t, d = x.shape
        nh = self.a.n_heads
        hd = d // nh
        h = self.attn_norm(x)
        q = self.lin(self.wq, h, qat).view(b, t, nh, hd).transpose(1, 2)
        k = self.lin(self.wk, h, qat).unsqueeze(1)
        v = self.lin(self.wv, h, qat).unsqueeze(1)
        if self.a.pos == "rope":
            q, k = rope(q, pos), rope(k, pos)
        if qat:
            q, k, v = fq_vec(q), fq_vec(k), fq_vec(v)
        if cache is not None:
            if "k" in cache:
                k = torch.cat([cache["k"], k], 2)
                v = torch.cat([cache["v"], v], 2)
            cache["k"], cache["v"] = k, v
        att = (q @ k.transpose(-1, -2)) / math.sqrt(hd)
        att = att.masked_fill(mask, float("-inf")).softmax(-1)
        o = (att @ v).transpose(1, 2).reshape(b, t, d)
        x = x + self.drop(self.lin(self.wo, o, qat))
        h = self.ffn_norm(x)
        if self.a.ffn == "swiglu":
            u = F.silu(self.lin(self.w1, h, qat, True)) * self.lin(self.w3, h, qat, True)
        else:
            u = F.relu(self.lin(self.w1, h, qat, True))
        return x + self.drop(self.lin(self.w2, u, qat, True))


class ExpLM(nn.Module):
    def __init__(self, a, vocab, n_answers=0):
        super().__init__()
        self.a = a
        d = a.d_model
        self.qat = False
        self.tok_emb = nn.Embedding(vocab, d)
        if a.pos == "learned":
            self.pos_emb = nn.Embedding(a.ctx_len, d)
        n_unique = a.unique or a.n_layers
        self.blocks = nn.ModuleList(Block(a, d, a.d_ff, a.dropout) for _ in range(n_unique))
        self.final_norm = RMSNorm(d)
        self.cls = nn.Linear(d, n_answers, bias=False) if n_answers else None
        for m in self.modules():
            if isinstance(m, (nn.Linear, nn.Embedding)):
                nn.init.normal_(m.weight, std=0.02)
        for blk in self.blocks:
            nn.init.normal_(blk.wo.weight, std=0.02 / math.sqrt(2 * a.n_layers))
            nn.init.normal_(blk.w2.weight, std=0.02 / math.sqrt(2 * a.n_layers))

    def hidden(self, idx, pos, mask, caches=None):
        tok_w = fq_rows(self.tok_emb.weight) if self.qat else self.tok_emb.weight
        x = tok_w[idx]
        if self.a.pos == "learned":
            pw = fq_rows(self.pos_emb.weight) if self.qat else self.pos_emb.weight
            x = x + pw[pos]
        n_unique = len(self.blocks)
        for i in range(self.a.n_layers):
            c = caches[i] if caches is not None else None
            x = self.blocks[i % n_unique](x, pos, self.qat, c, mask)
        h = self.final_norm(x)
        return fq_vec(h) if self.qat else h

    def head(self, h):
        tok_w = fq_rows(self.tok_emb.weight) if self.qat else self.tok_emb.weight
        return h @ tok_w.t()

    def cls_logits(self, h):
        w = fq_rows(self.cls.weight) if self.qat else self.cls.weight
        return h @ w.t()


def causal_mask(t, device):
    return torch.triu(torch.ones(t, t, dtype=torch.bool, device=device), 1)


def prefill_mask(valid):
    """Causal + key padding; the diagonal stays visible so left-pad rows remain finite."""
    t = valid.shape[1]
    m = causal_mask(t, valid.device)[None, None] | ~valid[:, None, None, :]
    return m & ~torch.eye(t, dtype=torch.bool, device=valid.device)[None, None]


def flash_bytes(model: ExpLM, a) -> dict:
    """Estimated on-device bytes: int8 (or int4) weights + float32 scale per row/group."""
    tot = emb = 0
    for name, p in model.named_parameters():
        if name.startswith("cls."):
            continue
        if p.dim() == 1:
            tot += 4 * p.numel()
            continue
        rows, cols = p.shape
        is_ffn = any(f".{w}." in name for w in ("w1", "w2", "w3")) and "blocks" in name
        bits = a.ffn_bits if is_ffn else 8
        n_scales = rows * (cols // a.group) if (bits < 8 and a.group) else rows
        b = rows * cols * bits // 8 + 4 * n_scales
        tot += b
        if "emb" in name:
            emb += b
    # bytes streamed per generated token: everything except unused embedding rows,
    # the tied output head reads the full token embedding once
    tok = model.tok_emb.weight
    per_token = tot - emb + tok.numel() + 4 * tok.shape[0]
    if a.unique and a.unique < a.n_layers:  # shared blocks are streamed once per use
        blk = sum(4 * p.numel() if p.dim() == 1 else p.numel() + 4 * p.shape[0]
                  for p in model.blocks[0].parameters())  # fmt: skip
        per_token += blk * (a.n_layers - a.unique)
    cls = 0
    if model.cls is not None:
        cls = model.cls.weight.numel() + 4 * model.cls.weight.shape[0]
    return {"model_bytes": tot, "per_token_bytes": per_token, "cls_bytes": cls}


# ----------------------------------------------------------------------------- data


def read_train(path):
    out = []
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        if line:
            q, a = line.split("\t")
            out.append((q, a))
    return out


def read_jsonl(path):
    return [json.loads(x) for x in Path(path).read_text(encoding="utf-8").splitlines() if x]


def eval_subset(held, seed=0, per_rel=25, frei=150, refusal=75):
    rng = random.Random(seed)
    by = collections.defaultdict(list)
    for r in held:
        by[r["relation"]].append(r)
    out = []
    for rel in sorted(by):
        rows = by[rel]
        n = frei if rel == "frei" else refusal if rel == REFUSAL else per_rel
        out += rng.sample(rows, min(n, len(rows)))
    return out


def encode(tok, q, a=None):
    ids = [BOS, *tok.encode(q), SEP]
    start = len(ids)
    if a is not None:
        ids += [*tok.encode(a), EOS]
    return ids, start


def make_batch(ex, idx, device):
    batch = [ex[i] for i in idx]
    t = max(len(e[0]) for e in batch) - 1
    x = torch.full((len(batch), t), PAD, dtype=torch.long)
    y = torch.full((len(batch), t), -100, dtype=torch.long)
    sep = torch.zeros(len(batch), dtype=torch.long)
    ans = torch.zeros(len(batch), dtype=torch.long)
    for b, (ids, start, aid) in enumerate(batch):
        n = len(ids) - 1
        x[b, :n] = torch.tensor(ids[:-1])
        y[b, start - 1 : n] = torch.tensor(ids[start:])
        sep[b] = start - 1
        ans[b] = aid
    return x.to(device), y.to(device), sep.to(device), ans.to(device)


# ----------------------------------------------------------------------------- decoding


class Trie:
    def __init__(self, seqs: list[list[int]]):
        self.nodes = [{}]
        self.ends: dict[int, int] = {}
        for k, s in enumerate(seqs):
            n = 0
            for t in s:
                nxt = self.nodes[n].get(t)
                if nxt is None:
                    nxt = len(self.nodes)
                    self.nodes.append({})
                    self.nodes[n][t] = nxt
                n = nxt
            self.ends[n] = k

    def size_bytes(self) -> int:
        # compact flash encoding estimate: per node 1 byte child count + 3 bytes/child
        # (token + 16-bit offset); single-child chains stored as 1 byte/token
        return sum(1 + (1 if len(c) == 1 else 3 * len(c)) for c in self.nodes)


@torch.no_grad()
def decode_batch(model, tok, prompts, device, max_new=170, trie=None, beam=1):
    """Greedy (optionally trie-constrained) decoding with KV cache and left padding.
    Returns texts and per-answer mean / min token log-prob."""
    model.eval()
    enc = [encode(tok, p)[0] for p in prompts]
    b = len(enc)
    t0 = max(len(e) for e in enc)
    x = torch.full((b, t0), PAD, dtype=torch.long)
    valid = torch.zeros((b, t0), dtype=torch.bool)
    for i, e in enumerate(enc):
        x[i, t0 - len(e) :] = torch.tensor(e)
        valid[i, t0 - len(e) :] = True
    pos = (valid.cumsum(1) - 1).clamp_min(0)
    x, valid, pos = x.to(device), valid.to(device), pos.to(device)
    caches = [{} for _ in range(model.a.n_layers)]
    keymask = valid.clone()
    h = model.hidden(x, pos, prefill_mask(keymask), caches)[:, -1]
    cur_pos = pos[:, -1]
    out = [[] for _ in range(b)]
    lps = [[] for _ in range(b)]
    done = torch.zeros(b, dtype=torch.bool)
    node = [0] * b
    for _ in range(max_new):
        logits = model.head(h).float()
        if trie is not None:
            allow = torch.full_like(logits, float("-inf"))
            for i in range(b):
                if done[i]:
                    allow[i, EOS] = 0
                    continue
                for t_ in trie.nodes[node[i]]:
                    allow[i, t_] = 0
                if node[i] in trie.ends:
                    allow[i, EOS] = 0
            logp_full = logits.log_softmax(-1)
            logits = logits + allow
        else:
            logp_full = logits.log_softmax(-1)
        nxt = logits.argmax(-1)
        for i in range(b):
            if done[i]:
                continue
            ti = int(nxt[i])
            lps[i].append(float(logp_full[i, ti]))
            if ti == EOS:
                done[i] = True
            else:
                out[i].append(ti)
                if trie is not None:
                    node[i] = trie.nodes[node[i]][ti]
        if bool(done.all()):
            break
        cur_pos = (cur_pos + 1).clamp_max(model.a.ctx_len - 1)
        keymask = torch.cat([keymask, torch.ones(b, 1, dtype=torch.bool, device=device)], 1)
        m = ~keymask[:, None, None, :]
        h = model.hidden(nxt[:, None].to(device), cur_pos[:, None], m, caches)[:, -1]
    texts = [tok.decode(o) for o in out]
    conf = [(float(np.mean(lp)) if lp else -99.0, float(np.min(lp)) if lp else -99.0)
            for lp in lps]  # fmt: skip
    return texts, conf


@torch.no_grad()
def sep_embed(model, tok, prompts, device, bs=256):
    model.eval()
    embs = []
    for k in range(0, len(prompts), bs):
        chunk = prompts[k : k + bs]
        enc = [encode(tok, p)[0] for p in chunk]
        t0 = max(len(e) for e in enc)
        x = torch.full((len(enc), t0), PAD, dtype=torch.long)
        valid = torch.zeros((len(enc), t0), dtype=torch.bool)
        for i, e in enumerate(enc):
            x[i, t0 - len(e) :] = torch.tensor(e)
            valid[i, t0 - len(e) :] = True
        pos = (valid.cumsum(1) - 1).clamp_min(0)
        h = model.hidden(x.to(device), pos.to(device), prefill_mask(valid.to(device)))[:, -1]
        embs.append(h.float().cpu())
    return torch.cat(embs)


def score(rows, answers, refusal_text, max_ratio=0.1):
    """rows: eval rows (with relation); answers: model outputs, same order."""
    ref_norm = normalize(refusal_text)
    chem, ref_ok, n_ref, false_ref = [], 0, 0, 0
    per_rel = collections.defaultdict(list)
    for r, a in zip(rows, answers, strict=True):
        ok = is_correct(a, r["expected"], max_ratio)
        per_rel[r.get("relation", "demo")].append(ok)
        if r.get("relation") == REFUSAL:
            n_ref += 1
            ref_ok += ok
        else:
            chem.append(ok)
            false_ref += normalize(a) == ref_norm
    return {
        "acc": sum(chem) / max(1, len(chem)),
        "n": len(chem),
        "refusal_rate": ref_ok / n_ref if n_ref else None,
        "false_refusal": false_ref / max(1, len(chem)),
        "per_rel": {k: round(sum(v) / len(v), 3) for k, v in sorted(per_rel.items())},
    }


# ----------------------------------------------------------------------------- main


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--tok", default="char", choices=["char", "bpe"])
    ap.add_argument("--bpe-vocab", type=int, default=384)
    ap.add_argument("--d-model", type=int, default=128)
    ap.add_argument("--n-layers", type=int, default=4)
    ap.add_argument("--n-heads", type=int, default=4)
    ap.add_argument("--d-ff", type=int, default=384)
    ap.add_argument("--ctx-len", type=int, default=192)
    ap.add_argument("--ffn", default="relu", choices=["relu", "swiglu"])
    ap.add_argument("--pos", default="learned", choices=["learned", "rope"])
    ap.add_argument("--unique", type=int, default=0)
    ap.add_argument("--ffn-bits", type=int, default=8, choices=[8, 4])
    ap.add_argument("--group", type=int, default=32)
    ap.add_argument("--steps", type=int, default=4000)
    ap.add_argument("--qat-steps", type=int, default=0)
    ap.add_argument("--batch", type=int, default=64)
    ap.add_argument("--lr", type=float, default=2e-3)
    ap.add_argument("--min-lr", type=float, default=1e-4)
    ap.add_argument("--warmup", type=int, default=200)
    ap.add_argument("--dropout", type=float, default=0.1)
    ap.add_argument("--wd", type=float, default=0.01)
    ap.add_argument("--ls", type=float, default=0.0)
    ap.add_argument("--ema", type=float, default=0.0)
    ap.add_argument("--cls", type=float, default=0.0)
    ap.add_argument("--kd-teacher", default="")
    ap.add_argument("--kd-alpha", type=float, default=0.5)
    ap.add_argument("--kd-temp", type=float, default=2.0)
    ap.add_argument("--threads", type=int, default=4)
    ap.add_argument("--seed", type=int, default=1234)
    ap.add_argument("--eval-only", action="store_true")
    a = ap.parse_args(argv)

    torch.set_num_threads(a.threads)
    random.seed(a.seed)
    np.random.seed(a.seed)
    torch.manual_seed(a.seed)
    device = torch.device("cpu")
    data, out = Path(a.data), Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    t_start = time.time()

    pairs = read_train(data / "train.txt")
    answers = sorted({ans for _, ans in pairs})
    aid = {ans: i for i, ans in enumerate(answers)}
    tok: CharTok | BPETok
    if a.tok == "bpe":
        tok = BPETok()
        uniq = sorted({q for q, _ in pairs} | set(answers))
        tok.learn(uniq, a.bpe_vocab)
    else:
        tok = CharTok()
    ex = []
    for q, ans in pairs:
        ids, start = encode(tok, q, ans)
        if len(ids) <= a.ctx_len:
            ex.append((ids, start, aid[ans]))
    chars = sum(len(ans) + 1 for _, ans in pairs)
    toks = sum(len(tok.encode(ans)) + 1 for _, ans in pairs)

    model = ExpLM(a, tok.vocab_size, len(answers) if a.cls else 0).to(device)
    n_params = sum(p.numel() for n, p in model.named_parameters() if not n.startswith("cls."))
    fb = flash_bytes(model, a)
    print(f"params {n_params}  flash {fb}  vocab {tok.vocab_size}  "
          f"chars/token {chars / toks:.2f}  examples {len(ex)}", flush=True)  # fmt: skip

    teacher = None
    if a.kd_teacher:
        tck = torch.load(a.kd_teacher, map_location="cpu", weights_only=False)
        ta = argparse.Namespace(**tck["args"])
        teacher = ExpLM(ta, tok.vocab_size, 0)
        teacher.load_state_dict({k: v for k, v in tck["state"].items()
                                 if not k.startswith("cls.")})  # fmt: skip
        teacher.eval()

    decay = [p for p in model.parameters() if p.dim() >= 2]
    no_decay = [p for p in model.parameters() if p.dim() < 2]
    opt = torch.optim.AdamW([{"params": decay, "weight_decay": a.wd},
                             {"params": no_decay, "weight_decay": 0.0}],
                            lr=a.lr, betas=(0.9, 0.98))  # fmt: skip
    ema = None
    if a.ema:
        ema = {k: v.detach().clone() for k, v in model.state_dict().items()}
    total = a.steps + a.qat_steps
    gen = np.random.default_rng(a.seed)
    losses = []
    ckpt = out / "ckpt.pt"
    if a.eval_only:
        ck = torch.load(ckpt, map_location="cpu", weights_only=False)
        model.load_state_dict(ck["state"])
        total = 0
    for step in range(total):
        if step < a.warmup:
            lr = a.lr * (step + 1) / a.warmup
        else:
            prog = (step - a.warmup) / max(1, total - a.warmup)
            lr = a.min_lr + 0.5 * (a.lr - a.min_lr) * (1 + math.cos(math.pi * prog))
        for g in opt.param_groups:
            g["lr"] = lr
        model.train()
        model.qat = step >= a.steps
        x, y, sep, ans = make_batch(ex, gen.integers(0, len(ex), size=a.batch), device)
        t = x.shape[1]
        pos = torch.arange(t)[None].expand(x.shape[0], t)
        h = model.hidden(x, pos, causal_mask(t, device)[None, None])
        logits = model.head(h)
        loss = F.cross_entropy(logits.reshape(-1, logits.size(-1)), y.reshape(-1),
                               label_smoothing=a.ls)  # fmt: skip
        if teacher is not None:
            with torch.no_grad():
                tl = teacher.head(teacher.hidden(x, pos, causal_mask(t, device)[None, None]))
            keep = (y != -100).reshape(-1)
            tt = a.kd_temp
            kd = F.kl_div((logits.reshape(-1, logits.size(-1))[keep] / tt).log_softmax(-1),
                          (tl.reshape(-1, tl.size(-1))[keep] / tt).log_softmax(-1),
                          log_target=True, reduction="batchmean") * tt * tt  # fmt: skip
            loss = (1 - a.kd_alpha) * loss + a.kd_alpha * kd
        if model.cls is not None:
            hs = h[torch.arange(h.shape[0]), sep]
            loss = loss + a.cls * F.cross_entropy(model.cls_logits(hs), ans)
        opt.zero_grad(set_to_none=True)
        loss.backward()
        torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
        opt.step()
        if ema is not None:
            with torch.no_grad():
                for k, v in model.state_dict().items():
                    ema[k].mul_(a.ema).add_(v.detach(), alpha=1 - a.ema)
        losses.append(float(loss))
        if step % 200 == 0 or step == total - 1:
            print(f"step {step:5d} loss {np.mean(losses[-200:]):.4f} lr {lr:.2e}"
                  f"{' qat' if model.qat else ''}  {time.time() - t_start:.0f}s",
                  flush=True)  # fmt: skip
    train_s = time.time() - t_start
    if not a.eval_only:
        torch.save({"args": vars(a), "state": model.state_dict(), "tok": tok.to_json()}, ckpt)
    variants = {"final": model.state_dict()}
    if ema is not None:
        variants = {"final": {k: v.clone() for k, v in model.state_dict().items()}, "ema": ema}

    # ---------------------------------------------------------------- evaluation
    held = eval_subset(read_jsonl(data / "heldout.jsonl"))
    demo = read_jsonl(data / "demo.jsonl")
    refusal_text = next(r["expected"] for r in held if r["relation"] == REFUSAL)
    trie = Trie([tok.encode(x) for x in answers])
    clean_q = {}
    for q, ans in pairs:
        clean_q.setdefault(q, ans)
    qs = list(clean_q)
    results = {"args": vars(a), "params": n_params, "flash": fb, "vocab": tok.vocab_size,
               "chars_per_token": round(chars / toks, 3), "train_s": round(train_s, 1),
               "final_loss": float(np.mean(losses[-200:])) if losses else None,
               "n_answers": len(answers), "trie_bytes": trie.size_bytes(),
               "answer_text_bytes": sum(len(x.encode()) + 1 for x in answers),
               "variants": {}}  # fmt: skip
    for vname, state in variants.items():
        model.load_state_dict(state)
        model.qat = True  # always evaluate with int8 (int4 FFN) numerics
        res = {}
        rows = {"demo": demo, "held": held}
        decoded = {}
        for mode in ("greedy", "trie"):
            for split, rr in rows.items():
                texts, conf = [], []
                for k in range(0, len(rr), 128):
                    t_, c_ = decode_batch(model, tok, [r["prompt"] for r in rr[k : k + 128]],
                                          device, trie=trie if mode == "trie" else None)
                    texts += t_
                    conf += c_
                decoded[(mode, split)] = (texts, conf)
                res[f"{mode}/{split}"] = score(rr, texts, refusal_text)
        # confidence threshold -> refusal (greedy mean log-prob)
        for thr in (-0.05, -0.1, -0.2, -0.4):
            for mode in ("greedy", "trie"):
                for split, rr in rows.items():
                    texts, conf = decoded[(mode, split)]
                    tt = [x if c[0] >= thr else refusal_text for x, c in zip(texts, conf)]
                    res[f"{mode}+conf{thr}/{split}"] = score(rr, tt, refusal_text)
        # centroid retrieval over <sep> embeddings (answer centroids of train questions)
        emb = F.normalize(sep_embed(model, tok, qs, device), dim=-1)
        lab = torch.tensor([aid[clean_q[q]] for q in qs])
        cent = torch.zeros(len(answers), emb.shape[1]).index_add_(0, lab, emb)
        cent = F.normalize(cent, dim=-1)
        for split, rr in rows.items():
            e = F.normalize(sep_embed(model, tok, [r["prompt"] for r in rr], device), dim=-1)
            sim = e @ cent.t()
            best = sim.argmax(-1)
            res[f"centroid/{split}"] = score(rr, [answers[int(i)] for i in best], refusal_text)
            if model.cls is not None:
                cl = model.cls_logits(sep_embed(model, tok, [r["prompt"] for r in rr], device))
                pr = cl.softmax(-1)
                p, ix = pr.max(-1)
                res[f"cls/{split}"] = score(rr, [answers[int(i)] for i in ix], refusal_text)
                # hybrid: classifier if confident, else trie-constrained generation
                tt, _ = decoded[("trie", split)]
                hy = [answers[int(i)] if float(pp) >= 0.5 else g
                      for i, pp, g in zip(ix, p, tt)]  # fmt: skip
                res[f"cls+trie/{split}"] = score(rr, hy, refusal_text)
        # examples of errors
        texts, _ = decoded[("greedy", "held")]
        res["errors_greedy"] = [
            {"prompt": r["prompt"], "expected": r["expected"], "answer": t_}
            for r, t_ in zip(held, texts) if not is_correct(t_, r["expected"])
        ][:25]  # fmt: skip
        results["variants"][vname] = res
        g, tr = res["greedy/held"], res["trie/held"]
        print(f"[{vname}] demo {res['greedy/demo']['acc']:.3f} held {g['acc']:.3f} "
              f"refusal {g['refusal_rate']:.3f} false {g['false_refusal']:.3f} | trie demo "
              f"{res['trie/demo']['acc']:.3f} held {tr['acc']:.3f} refusal "
              f"{tr['refusal_rate']:.3f} | centroid held {res['centroid/held']['acc']:.3f}",
              flush=True)  # fmt: skip
    results["total_s"] = round(time.time() - t_start, 1)
    (out / "result.json").write_text(json.dumps(results, indent=1, ensure_ascii=False) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
