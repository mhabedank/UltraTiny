import numpy as np
import pytest

from ultratiny.alphabet import BOS, EOS, N_SPECIAL, SEP, UNK, Alphabet
from ultratiny.quant import quantize_rows, quantize_vector, round_half_away


def test_alphabet_roundtrip_with_umlauts():
    ab = Alphabet()
    text = "Größe: Äpfel, Öl & Übermaß? 42%"
    ids = ab.encode(text)
    assert UNK not in ids
    assert ab.decode(ids) == text
    assert ab.vocab_size <= 96
    for ch in "äöüÄÖÜß":
        assert ch in ab


def test_alphabet_unknown_and_specials():
    ab = Alphabet()
    assert ab.encode("a😀b")[1] == UNK
    assert ab.decode([BOS, *ab.encode("ok"), SEP, EOS]) == "ok"
    assert ab.prompt_ids("x")[0] == BOS and ab.prompt_ids("x")[-1] == SEP
    cps = ab.code_points()
    assert len(cps) == ab.vocab_size
    assert Alphabet.from_code_points(cps).symbols == ab.symbols
    assert all(i < N_SPECIAL for i in (BOS, SEP, EOS, UNK))


def test_alphabet_rejects_duplicates():
    with pytest.raises(ValueError):
        Alphabet("aa")


def test_round_half_away_from_zero():
    v = np.array([0.5, 1.5, 2.5, -0.5, -2.5, 0.49999997, 126.5], dtype=np.float32)
    assert round_half_away(v).tolist() == [1, 2, 3, -1, -3, 1, 127]


def test_quantize_vector_edge_cases():
    q, s = quantize_vector(np.zeros(4, dtype=np.float32))
    assert s == 1.0 and not q.any()
    q, s = quantize_vector(np.array([1.0, -2.0, 0.5, 2.0], dtype=np.float32))
    assert q.tolist() == [64, -127, 32, 127]
    assert s == np.float32(2.0) / np.float32(127.0)


def test_quantize_rows_zero_row_and_max():
    w = np.array([[0, 0, 0], [3, -1.5, 0.75]], dtype=np.float32)
    q, s = quantize_rows(w)
    assert s[0] == 1.0 and not q[0].any()
    assert q[1, 0] == 127 and q[1, 1] == -64 and abs(int(q[1].max())) <= 127
