"""Fixed character alphabet (data-model.md Alphabet, research.md R2).

Token IDs 0-4 are reserved special tokens; the remaining IDs map to Unicode code points.
The alphabet is stored inside every model file, so device and reference always agree.
"""

from __future__ import annotations

PAD, BOS, SEP, EOS, UNK = 0, 1, 2, 3, 4
SPECIAL_NAMES = ["<pad>", "<bos>", "<sep>", "<eos>", "<unk>"]
N_SPECIAL = len(SPECIAL_NAMES)
SPECIAL_CODE_BASE = 0xFFFF0000  # how specials are encoded in the model file
MAX_VOCAB = 96

_LETTERS = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ"
_DIGITS = "0123456789"
_UMLAUTS = "äöüÄÖÜß"
_PUNCT = ".,;:!?-'\"()/%+=&°"

DEFAULT_SYMBOLS = " " + _LETTERS + _DIGITS + _UMLAUTS + _PUNCT


class Alphabet:
    def __init__(self, symbols: str = DEFAULT_SYMBOLS):
        if len(set(symbols)) != len(symbols):
            raise ValueError("alphabet symbols must be unique")
        if N_SPECIAL + len(symbols) > MAX_VOCAB:
            raise ValueError(f"vocab too large: {N_SPECIAL + len(symbols)} > {MAX_VOCAB}")
        self.symbols = symbols
        self._to_id = {ch: N_SPECIAL + i for i, ch in enumerate(symbols)}

    @property
    def vocab_size(self) -> int:
        return N_SPECIAL + len(self.symbols)

    def __contains__(self, ch: str) -> bool:
        return ch in self._to_id

    def invalid_chars(self, text: str) -> set[str]:
        return {ch for ch in text if ch not in self._to_id}

    def encode(self, text: str) -> list[int]:
        return [self._to_id.get(ch, UNK) for ch in text]

    def decode(self, ids) -> str:
        out = []
        for i in ids:
            i = int(i)
            if i >= N_SPECIAL:
                out.append(self.symbols[i - N_SPECIAL])
        return "".join(out)

    def prompt_ids(self, question: str) -> list[int]:
        """Token sequence fed before generation: <bos> question <sep>."""
        return [BOS, *self.encode(question), SEP]

    def code_points(self) -> list[int]:
        """Alphabet table as stored in the model file (index = token ID)."""
        return [SPECIAL_CODE_BASE + k for k in range(N_SPECIAL)] + [ord(c) for c in self.symbols]

    @classmethod
    def from_code_points(cls, cps: list[int]) -> Alphabet:
        for k in range(N_SPECIAL):
            if cps[k] != SPECIAL_CODE_BASE + k:
                raise ValueError("invalid special token table")
        return cls("".join(chr(c) for c in cps[N_SPECIAL:]))
