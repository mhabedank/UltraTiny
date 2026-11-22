"""UTNY model file writer/reader (contracts/model-format.md).

Version 1: five special tokens. Version 2 (specs/006-hybrid-chemielehrer, research R12): the
alphabet table has a sixth special `<fn>` (id 5); the rest of the layout is unchanged.
"""

from __future__ import annotations

import json
import struct
import zlib
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from .alphabet import Alphabet
from .config import ModelConfig
from .quant import quantize_rows

MAGIC = b"UTNY"
FORMAT_VERSION = 2  # newest version written; v1 is still read and written for v1 alphabets
HEADER_SIZE = 64
FLAG_TIED = 1
# magic, 10 x u16, f32, 6 x u32, 8 reserved bytes  (header_crc32 appended separately)
_HEADER_FMT = "<4s10Hf6I8s"
assert struct.calcsize(_HEADER_FMT) == 60


def _align4(b: bytearray) -> None:
    while len(b) % 4:
        b.append(0)


def tensor_order(cfg: ModelConfig) -> list[tuple[str, str]]:
    """(state_dict key, kind) in file order; kind 'Q' (int8 rows + scales) or 'F' (f32 vector)."""
    order = [("tok_emb.weight", "Q"), ("pos_emb.weight", "Q")]
    for i in range(cfg.n_layers):
        p = f"blocks.{i}."
        order += [
            (p + "attn_norm.weight", "F"),
            (p + "wq.weight", "Q"),
            (p + "wk.weight", "Q"),
            (p + "wv.weight", "Q"),
            (p + "wo.weight", "Q"),
            (p + "ffn_norm.weight", "F"),
            (p + "w1.weight", "Q"),
            (p + "w2.weight", "Q"),
        ]
    order.append(("final_norm.weight", "F"))
    return order


def write_model(
    path: Path,
    cfg: ModelConfig,
    state: dict[str, np.ndarray],
    alphabet: Alphabet,
    meta: dict,
) -> int:
    """Write a UTNY file (v2 for alphabets with <fn>, else v1). Returns the file size."""
    if alphabet.vocab_size != cfg.vocab_size:
        raise ValueError("alphabet size does not match vocab_size")
    payload = bytearray()
    alphabet_offset = HEADER_SIZE
    cps = alphabet.code_points()
    payload += struct.pack(f"<I{len(cps)}I", len(cps), *cps)
    _align4(payload)

    meta_offset = HEADER_SIZE + len(payload)
    payload += json.dumps(meta, ensure_ascii=False, sort_keys=True).encode("utf-8") + b"\0"
    _align4(payload)

    tensors_offset = HEADER_SIZE + len(payload)
    n_params = 0
    for key, kind in tensor_order(cfg):
        w = np.asarray(state[key], dtype=np.float32)
        n_params += w.size
        if kind == "Q":
            q, s = quantize_rows(w)
            payload += s.astype("<f4").tobytes()
            payload += q.astype(np.int8).tobytes()
        else:
            payload += w.astype("<f4").tobytes()
        _align4(payload)

    header = struct.pack(
        _HEADER_FMT,
        MAGIC,
        2 if alphabet.fn else 1,
        HEADER_SIZE,
        cfg.vocab_size,
        cfg.d_model,
        cfg.n_layers,
        cfg.n_heads,
        cfg.n_kv_heads,
        cfg.d_ff,
        cfg.ctx_len,
        FLAG_TIED,
        cfg.norm_eps,
        alphabet_offset,
        meta_offset,
        tensors_offset,
        len(payload),
        zlib.crc32(payload) & 0xFFFFFFFF,
        n_params,
        b"\0" * 8,
    )
    header += struct.pack("<I", zlib.crc32(header) & 0xFFFFFFFF)
    data = header + payload
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return len(data)


@dataclass
class ModelFile:
    cfg: ModelConfig
    alphabet: Alphabet
    meta: dict
    n_params: int
    tensors: dict[str, tuple]  # key -> (q int8, scale f32) or (vector f32,)
    size: int


def read_model(path: Path | bytes) -> ModelFile:
    data = path if isinstance(path, bytes) else Path(path).read_bytes()
    if len(data) < HEADER_SIZE:
        raise ValueError("file too small")
    f = struct.unpack(_HEADER_FMT, data[:60])
    (magic, version, hsize, vocab, d, nl, nh, nkv, dff, ctx, flags, eps,
     a_off, m_off, t_off, p_size, p_crc, n_params, _res) = f  # fmt: skip
    if magic != MAGIC:
        raise ValueError("bad magic")
    if version not in (1, 2):
        raise ValueError(f"unsupported format version {version}")
    (h_crc,) = struct.unpack("<I", data[60:64])
    if zlib.crc32(data[:60]) & 0xFFFFFFFF != h_crc:
        raise ValueError("header CRC mismatch")
    if hsize + p_size != len(data):
        raise ValueError("size mismatch")
    if zlib.crc32(data[HEADER_SIZE:]) & 0xFFFFFFFF != p_crc:
        raise ValueError("payload CRC mismatch")
    cfg = ModelConfig(
        vocab_size=vocab, d_model=d, n_layers=nl, n_heads=nh, n_kv_heads=nkv,
        d_ff=dff, ctx_len=ctx, norm_eps=float(np.float32(eps)),
    )  # fmt: skip
    cfg.validate()
    (count,) = struct.unpack_from("<I", data, a_off)
    cps = list(struct.unpack_from(f"<{count}I", data, a_off + 4))
    alphabet = Alphabet.from_code_points(cps)
    if alphabet.fn != (version == 2):
        raise ValueError("alphabet does not match format version")
    meta_end = data.index(b"\0", m_off)
    meta = json.loads(data[m_off:meta_end].decode("utf-8"))

    shapes = {
        "tok_emb.weight": (vocab, d),
        "pos_emb.weight": (ctx, d),
        "final_norm.weight": (d,),
    }
    for i in range(nl):
        p = f"blocks.{i}."
        hd = d // nh
        shapes.update({
            p + "attn_norm.weight": (d,), p + "ffn_norm.weight": (d,),
            p + "wq.weight": (d, d), p + "wk.weight": (hd * nkv, d),
            p + "wv.weight": (hd * nkv, d), p + "wo.weight": (d, d),
            p + "w1.weight": (dff, d), p + "w2.weight": (d, dff),
        })  # fmt: skip
    off = t_off
    tensors: dict[str, tuple] = {}
    for key, kind in tensor_order(cfg):
        shp = shapes[key]
        if kind == "Q":
            rows, cols = shp
            s = np.frombuffer(data, dtype="<f4", count=rows, offset=off).astype(np.float32)
            off += 4 * rows
            q = np.frombuffer(data, dtype=np.int8, count=rows * cols, offset=off).reshape(shp)
            off += rows * cols
            tensors[key] = (q, s)
        else:
            v = np.frombuffer(data, dtype="<f4", count=shp[0], offset=off).astype(np.float32)
            off += 4 * shp[0]
            tensors[key] = (v,)
        off = (off + 3) & ~3
    if off != len(data):
        raise ValueError("tensor block size mismatch")
    return ModelFile(cfg, alphabet, meta, n_params, tensors, len(data))
