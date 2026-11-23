"""Language KPIs: S1 bits per character and S2 usable context (research R6, R7).

Both use only the subject's reset()/feed() and its history window, so any language model can be
measured without being trained for the test.
"""

from __future__ import annotations

import math

import numpy as np

from .suite import Probe


def _bits(logits: np.ndarray, target: int) -> float:
    z = logits.astype(np.float64)
    m = float(z.max())
    lse = m + math.log(float(np.exp(z - m).sum()))
    return (lse - float(z[target])) / math.log(2.0)


def clean_text(text: str, alphabet) -> tuple[str, int]:
    """Remove characters outside the model alphabet; return the text and how many were removed."""
    kept = [ch for ch in text if ch in alphabet]
    return "".join(kept), len(text) - len(kept)


def sliding_bits(subject, tokens: list[int], step=None) -> list[float]:
    """Bits for tokens[1:]: windows of `window` tokens, stride window/2; only the second half of
    each window is scored (the first window scores all of it). Unbounded subjects: one pass."""
    n = len(tokens)
    out = [0.0] * n
    win = subject.window
    if win is None or win >= n:
        subject.reset()
        logits = subject.feed(tokens[0])
        for i in range(1, n):
            out[i] = _bits(logits, tokens[i])
            if step:
                step()
            if i < n - 1:
                logits = subject.feed(tokens[i])
        return out[1:]
    stride = max(1, win // 2)
    start, scored = 0, 0  # positions <= scored are done
    while scored < n - 1:
        subject.reset()
        end = min(n - 1, start + win)  # feeding tokens[start:end] predicts start+1 .. end
        for i in range(start, end):
            logits = subject.feed(tokens[i])
            if i + 1 > scored:
                out[i + 1] = _bits(logits, tokens[i + 1])
                if step:
                    step()
        scored = end
        start += stride
    return out[1:]


def s1(subject, sections: dict[str, str], step=None) -> dict:
    """S1 per section (topic, general) and for both; coverage = share of characters kept."""
    ab = subject.alphabet
    detail: dict = {}
    tot_bits, tot_n, tot_chars, tot_removed = 0.0, 0, 0, 0
    for name in sorted(sections):
        raw = sections[name]
        text, removed = clean_text(raw, ab)
        if len(text) < 2:
            continue
        bits = sliding_bits(subject, ab.encode(text), step)
        detail[name] = round(sum(bits) / len(bits), 4)
        tot_bits += sum(bits)
        tot_n += len(bits)
        tot_chars += len(raw)
        tot_removed += removed
    if not tot_n:
        return {"value": None, "status": "not_measured", "reason": "no S1 text"}
    detail["coverage"] = round(100.0 * (tot_chars - tot_removed) / tot_chars, 2)
    detail["chars"] = tot_n
    return {"value": round(tot_bits / tot_n, 4), "status": "measured", "detail": detail}


def span_bits(subject, tokens: list[int], start: int, length: int) -> float:
    """Bits of tokens[start:start+length] with as much history as the window allows; the window
    ends at the end of the span (research R7)."""
    if start <= 0:
        raise ValueError("span must not start at position 0")
    end = start + length  # exclusive
    win = subject.window
    first = 0 if win is None else max(0, end - 1 - win)
    subject.reset()
    total = 0.0
    logits = None
    for i in range(first, end - 1):
        logits = subject.feed(tokens[i])
        if i + 1 >= start:
            total += _bits(logits, tokens[i + 1])
    return total


def s2(subject, probes: list[Probe], cfg: dict, step=None) -> dict:
    ratio = float(cfg.get("recall_ratio", 0.5))
    need = float(cfg.get("recall_min", 0.8))
    ab = subject.alphabet
    per: dict[int, list[bool]] = {}
    for p in probes:
        t = ab.encode(p.text)
        c = ab.encode(p.control)
        b = span_bits(subject, t, p.target_start, p.target_len)
        bc = span_bits(subject, c, p.target_start, p.target_len)
        per.setdefault(p.distance, []).append(b <= ratio * bc)
        if step:
            step()
    if not per:
        return {"value": None, "status": "not_measured", "reason": "no S2 probes"}
    curve = {str(d): round(sum(v) / len(v), 3) for d, v in sorted(per.items())}
    passed = [d for d, v in sorted(per.items()) if sum(v) / len(v) >= need]
    best = max(passed) if passed else 0
    largest = max(per)
    value = best
    detail: dict = {"curve": curve}
    if best == largest:
        detail["at_least"] = True  # reported as ">= largest distance" (spec FR-003 f)
    return {"value": value, "status": "measured", "detail": detail, "n": len(probes)}
