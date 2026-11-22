"""Fixed character alphabet (data-model.md Alphabet, research.md R2).

Token IDs 0-4 are reserved special tokens; the remaining IDs map to Unicode code points.
The alphabet is stored inside every model file, so device and reference always agree.

Hybrid models (UTNY v2, specs/006-hybrid-chemielehrer/contracts/function-output.md) add a sixth
special token `<fn>` (id 5): the model emits `<fn>` + type letter + object key for factual
questions. In training text files `<fn>` is written as the control character `\x01` (FN_CHAR).
"""

from __future__ import annotations

PAD, BOS, SEP, EOS, UNK, FN = 0, 1, 2, 3, 4, 5
SPECIAL_NAMES = ["<pad>", "<bos>", "<sep>", "<eos>", "<unk>", "<fn>"]
N_SPECIAL = 5  # specials of a v1 alphabet (without <fn>)
FN_CHAR = "\x01"  # <fn> in training text files
SPECIAL_CODE_BASE = 0xFFFF0000  # how specials are encoded in the model file
MAX_VOCAB = 96

_LETTERS = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ"
_DIGITS = "0123456789"
_UMLAUTS = "äöüÄÖÜß"
_PUNCT = ".,;:!?-'\"()/%+=&°"

DEFAULT_SYMBOLS = " " + _LETTERS + _DIGITS + _UMLAUTS + _PUNCT


class Alphabet:
    def __init__(self, symbols: str = DEFAULT_SYMBOLS, fn: bool = False):
        if len(set(symbols)) != len(symbols):
            raise ValueError("alphabet symbols must be unique")
        self.fn = fn
        self.n_special = N_SPECIAL + (1 if fn else 0)
        if self.n_special + len(symbols) > MAX_VOCAB:
            raise ValueError(f"vocab too large: {self.n_special + len(symbols)} > {MAX_VOCAB}")
        self.symbols = symbols
        self._to_id = {ch: self.n_special + i for i, ch in enumerate(symbols)}

    @classmethod
    def for_vocab(cls, vocab_size: int) -> Alphabet:
        """Default alphabet matching a model's vocab size (with or without <fn>)."""
        for fn in (False, True):
            ab = cls(fn=fn)
            if ab.vocab_size == vocab_size:
                return ab
        raise ValueError(f"no default alphabet with vocab size {vocab_size}")

    @property
    def vocab_size(self) -> int:
        return self.n_special + len(self.symbols)

    def __contains__(self, ch: str) -> bool:
        return ch in self._to_id

    def invalid_chars(self, text: str) -> set[str]:
        return {ch for ch in text if ch not in self._to_id}

    def encode(self, text: str) -> list[int]:
        fn = FN if self.fn else UNK
        return [fn if ch == FN_CHAR else self._to_id.get(ch, UNK) for ch in text]

    def decode(self, ids) -> str:
        out = []
        for i in ids:
            i = int(i)
            if i >= self.n_special:
                out.append(self.symbols[i - self.n_special])
            elif self.fn and i == FN:
                out.append(FN_CHAR)
        return "".join(out)

    def prompt_ids(self, question: str) -> list[int]:
        """Token sequence fed before generation: <bos> question <sep>."""
        return [BOS, *self.encode(question), SEP]

    def code_points(self) -> list[int]:
        """Alphabet table as stored in the model file (index = token ID)."""
        specials = [SPECIAL_CODE_BASE + k for k in range(self.n_special)]
        return specials + [ord(c) for c in self.symbols]

    @classmethod
    def from_code_points(cls, cps: list[int]) -> Alphabet:
        n = 0
        while n < len(cps) and n <= FN and cps[n] == SPECIAL_CODE_BASE + n:
            n += 1
        if n not in (N_SPECIAL, N_SPECIAL + 1):
            raise ValueError("invalid special token table")
        return cls("".join(chr(c) for c in cps[n:]), fn=(n == N_SPECIAL + 1))
