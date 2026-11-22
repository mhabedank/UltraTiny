"""UTFT writer/reader and answer rendering (specs/006-hybrid-chemielehrer, T016/T019)."""

import subprocess
import sys

import pytest

from ultratiny import factgen
from ultratiny import facttable as ft
from ultratiny.alphabet import EOS, FN, Alphabet
from ultratiny.config import load_config
from ultratiny.datagen import TRAINING_ROOT

AB = Alphabet(fn=True)


@pytest.fixture(scope="module")
def table():
    cfg = load_config(TRAINING_ROOT / "configs" / "chemie-hybrid.toml")
    fs = factgen.build(cfg, TRAINING_ROOT)
    data = ft.build_bytes(fs)
    t = ft.Table(data)
    t.check_rendered(fs)
    return t, data


def say(t, s, eos=True):
    return ft.answer_bytes([FN, *AB.encode(s)] + ([EOS] if eos else []), AB, t).decode()


def test_size_and_determinism(table):
    t, data = table
    assert t.ok and len(data) <= ft.MAX_SIZE
    cfg = load_config(TRAINING_ROOT / "configs" / "chemie-hybrid.toml")
    assert ft.build_bytes(factgen.build(cfg, TRAINING_ROOT)) == data


def test_contract_examples(table):
    t, _ = table
    assert say(t, "OCu") == "Die Ordnungszahl von Kupfer ist 29."
    assert say(t, "sN") == "Das Symbol N steht für Stickstoff."
    assert say(t, "o29") == "Die Ordnungszahl 29 hat Kupfer."
    assert say(t, "RAl2O3") == "Die Formel von Aluminiumoxid ist Al2O3."
    assert say(t, "mH2O") == "Die molare Masse von Wasser beträgt 18,0 g/mol."
    assert say(t, "iNe") == "Das typische Ion von Neon gibt es nicht."
    assert say(t, "EC").startswith("Das Element Kohlenstoff (C) ist ein Nichtmetall")
    assert say(t, "sCo") == "Das Symbol Co steht für Cobalt."
    assert say(t, "fCO") == "Die Formel CO steht für Kohlenstoffmonooxid."


def test_fallbacks(table):
    t, _ = table
    assert say(t, "OXx") == "Die Ordnungszahl von – Das weiß ich leider nicht."
    assert say(t, "QCu") == ft.UNKNOWN.decode()
    assert ft.answer_bytes([FN, EOS], AB, t) == ft.UNKNOWN
    assert ft.answer_bytes([FN, *AB.encode("OCu"), EOS], AB, ft.Table(None)) == ft.MISSING
    corrupt = bytearray(t.data)
    corrupt[-1] ^= 1
    assert ft.Table(bytes(corrupt)).status == "CORRUPT"
    assert ft.Table(b"\xff" * 64).status == "MISSING"
    # text answers are printed as they are, a later <fn> ends them
    assert ft.answer_bytes([*AB.encode("Hallo"), FN], AB, t) == b"Hallo"


def test_function_output_helper():
    assert ft.function_output([FN, *AB.encode("OCu"), EOS], AB) == "OCu"
    assert ft.function_output([*AB.encode("Hi"), EOS], AB) is None


def test_runtime_fact_fixtures_up_to_date():
    tool = TRAINING_ROOT / "tools" / "make_runtime_fixtures.py"
    r = subprocess.run([sys.executable, str(tool), "--check"], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
