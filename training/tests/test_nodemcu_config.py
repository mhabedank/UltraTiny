"""NodeMCU PoC config (specs/005-nodemcu-port, data-model.md "NodeMCU model configuration")."""

from pathlib import Path

from ultratiny.config import load_config
from ultratiny.datagen import _expand, load_facts, load_relations, qa_pairs
from ultratiny.reference import arena_size

ROOT = Path(__file__).resolve().parents[1]
ARENA_MAX = 36 * 1024  # 40 KB budget minus 10 % headroom (constitution v2.0.0)


def _cfg():
    return load_config(ROOT / "configs/nodemcu.toml")


def test_arena_fits_nodemcu_budget():
    cfg = _cfg()
    assert cfg.model.ctx_len == 104
    assert arena_size(cfg.model) <= ARENA_MAX


def test_starter_architecture_kept():
    cfg, starter = _cfg(), load_config(ROOT / "configs/starter.toml")
    for f in ("d_model", "n_layers", "n_heads", "n_kv_heads", "d_ff"):
        assert getattr(cfg.model, f) == getattr(starter.model, f)


def test_context_keeps_almost_all_pairs():
    cfg = _cfg()
    facts = load_facts(_expand(cfg.data.facts, ROOT))
    rels = load_relations(_expand(cfg.data.templates, ROOT))
    train, held = qa_pairs(facts, rels)
    pairs = train + held

    def fits(q: str, a: str) -> bool:
        return len(q) + len(a) + 3 <= cfg.model.ctx_len and len(a) <= cfg.data.max_answer_len

    kept = sum(fits(q, a) for q, a, _ in pairs)
    assert kept / len(pairs) >= 0.99


def test_no_esp32_in_self_description():
    text = (ROOT / "data/facts/starter.tsv").read_text(encoding="utf-8")
    assert "ESP32" not in text
    assert "ESP8266" in text and "NodeMCU" in text
