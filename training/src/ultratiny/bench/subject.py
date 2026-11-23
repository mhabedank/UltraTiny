"""Model adapters ("subjects") for the benchmark (research R2).

The benchmark talks to a model only through:

    answer(question) -> (visible text, too_long)   what the board prints, fact table included
    reset() / feed(token) -> logits                  for S1/S2 bit costs
    window                                            max tokens of history (None = unbounded)
    alphabet, identity()

A new model core (specs 011-013) adds one adapter here; the benchmark stays unchanged.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import numpy as np

from .. import facttable as ft
from ..reference import Reference, arena_size

ANSWER_RESERVE = 32  # UT_ANSWER_RESERVE in runtime/include/utiny_console.h


def file_identity(path: Path | None) -> dict | None:
    if path is None:
        return None
    data = Path(path).read_bytes()
    return {"sha256": hashlib.sha256(data).hexdigest(), "size": len(data), "file": Path(path).name}


class TransformerSubject:
    """Today's transformer (UTNY v1/v2) through the bit-exact Python reference."""

    def __init__(self, model_path: Path | str, facts_path: Path | str | None = None):
        self.model_path = Path(model_path)
        self.facts_path = Path(facts_path) if facts_path else None
        self.ref = Reference(self.model_path)
        self.alphabet = self.ref.m.alphabet
        self.ctx_len = self.ref.cfg.ctx_len
        self.window = self.ctx_len
        self.table = None
        if self.facts_path is not None:
            self.table = ft.read(self.facts_path)
            if not self.table.ok:
                raise ValueError(f"{self.facts_path}: fact table invalid or missing")
        elif self.alphabet.fn:
            self.table = ft.Table(None)  # v2 model without table: prints the "missing" text

    # ---------------------------------------------------------------- answers

    def max_question(self) -> int:
        """Console limit: <bos> + question + <sep> + 32 reserved answer positions (console.c)."""
        return self.ctx_len - 2 - ANSWER_RESERVE

    def console_text(self, question: str) -> str:
        """What the console keeps of a typed question: characters outside the alphabet are
        ignored (console.c "Zeichen ... unbekannt, ignoriert"), so the reference drops them too."""
        return "".join(ch for ch in question if ch in self.alphabet)

    def answer(self, question: str) -> tuple[str, bool]:
        question = self.console_text(question)
        if len(question) > self.max_question():
            return "", True  # the console refuses the extra characters
        toks = self.ref.generate(question, max_len=self.ctx_len - 3)["tokens"]
        text = ft.answer_bytes(toks, self.alphabet, self.table).decode("utf-8", "replace")
        return text, False

    # ---------------------------------------------------------------- bits

    def reset(self) -> None:
        self.ref.reset()

    def feed(self, token: int) -> np.ndarray:
        return self.ref.feed(token)

    # ---------------------------------------------------------------- identity

    def identity(self) -> dict:
        m = self.ref.m
        out = file_identity(self.model_path) or {}
        meta = m.meta or {}
        out.update(
            {
                "params": int(m.n_params),
                "ctx_len": int(self.ctx_len),
                "vocab": int(m.cfg.vocab_size),
                "arena": int(arena_size(m.cfg)),
                "arch": "transformer",
                "name": meta.get("name"),
                "git": meta.get("git"),
                "date": meta.get("date"),
                "seed": meta.get("seed"),
                "data": meta.get("data"),
            }
        )
        return out

    def knowledge(self) -> dict | None:
        return file_identity(self.facts_path)


def load_subject(model: Path | str, facts: Path | str | None = None) -> TransformerSubject:
    return TransformerSubject(model, facts)
