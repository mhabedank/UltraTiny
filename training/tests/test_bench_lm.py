"""S1 and S2 measurement (specs/007-benchmark-kpi-bericht T009, research R6/R7)."""

import math
from pathlib import Path

import numpy as np

from ultratiny.alphabet import Alphabet
from ultratiny.bench.lm import s1, s2, sliding_bits
from ultratiny.bench.subject import TransformerSubject
from ultratiny.bench.suite import Probe, load_suite

FIX = Path(__file__).parent / "fixtures"
TINY_V2 = Path(__file__).parents[2] / "runtime" / "tests" / "fixtures" / "tiny_v2.utny"


class CopySubject:
    """Predicts the token that followed the last earlier occurrence of the last two tokens."""

    def __init__(self, window):
        self.alphabet = Alphabet()
        self.window = window
        self.hist: list[int] = []
        self.feeds = 0

    def reset(self):
        self.hist = []

    def feed(self, tok):
        self.feeds += 1
        self.hist.append(tok)
        if self.window is not None:
            assert len(self.hist) <= self.window, "fed more tokens than the window"
        z = np.zeros(self.alphabet.vocab_size, dtype=np.float32)
        h = self.hist
        for i in range(len(h) - 2, 0, -1):  # match the last two tokens
            if h[i] == tok and len(h) >= 2 and h[i - 1] == h[-2]:
                z[h[i + 1]] = 12.0
                break
        return z


def test_sliding_scores_every_position_once():
    ab = Alphabet()
    toks = ab.encode("abcdefghij" * 30)
    a = sliding_bits(CopySubject(None), toks)
    b = sliding_bits(CopySubject(40), toks)
    assert len(a) == len(b) == len(toks) - 1
    assert all(math.isfinite(x) for x in b)
    # after the first period the copy model is certain, in both modes (history >= window/2)
    assert max(a[20:]) < 0.01 and max(b[20:]) < 0.01


def _probe(d, word="Brolmik", other="Zavutek"):
    head = "Ein Ding hieß "
    body = (" und so weiter" * 40)[: d - 8] + " wieder "
    text = head + word + body + word + "."
    ctrl = head + other + body + word + "."
    return Probe(f"p{d}", d, len(head) + len(word) + len(body), len(word), text, ctrl)


def test_s2_recall_within_window_only():
    probes = [_probe(d) for d in (16, 32, 64, 128)]
    res = s2(CopySubject(64), probes, {"recall_ratio": 0.5, "recall_min": 0.8})
    curve = res["detail"]["curve"]
    assert curve["16"] == 1.0 and curve["32"] == 1.0
    assert curve["128"] == 0.0
    assert res["value"] in (32, 64)
    unbounded = s2(CopySubject(None), probes, {})
    assert unbounded["value"] == 128 and unbounded["detail"]["at_least"] is True


def test_s1_on_real_model():
    subj = TransformerSubject(TINY_V2)
    suite = load_suite(FIX / "bench_mini")
    res = s1(subj, suite.s1)
    assert res["status"] == "measured" and 0 < res["value"] < 20
    assert set(res["detail"]) >= {"topic", "general", "coverage"}
    assert res["detail"]["coverage"] > 95.0


def test_s1_coverage_counts_unknown_characters():
    res = s1(CopySubject(32), {"general": "abc€abc€abcabc"})
    assert res["detail"]["coverage"] < 100.0
