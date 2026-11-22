"""Fact builder rules and checks (specs/006-hybrid-chemielehrer, tasks T010-T012)."""

from dataclasses import replace

import pytest

from ultratiny import factgen
from ultratiny import periodic as pt
from ultratiny.alphabet import Alphabet
from ultratiny.config import load_config
from ultratiny.datagen import TRAINING_ROOT, allowed_source_prefixes

AB = Alphabet(fn=True)


@pytest.fixture(scope="module")
def fs():
    cfg = load_config(TRAINING_ROOT / "configs" / "chemie-hybrid.toml")
    return factgen.build(cfg, TRAINING_ROOT)


def errors(fs):
    return factgen.check(fs, AB, allowed_source_prefixes())


def test_periodic_rules():
    assert pt.electron_arrangement(11) == [2, 8, 1]
    assert pt.electron_arrangement(20) == [2, 8, 8, 2]
    assert pt.electron_arrangement(35) == [2, 8, 18, 7]
    assert pt.electron_arrangement(26) is None  # transition metal: not in the school model
    assert pt.outer_electrons(16) == 6 and pt.outer_electrons(2) == 2
    assert pt.ion_charge(8) == -2 and pt.ion_charge(13) == 3 and pt.ion_charge(10) is None
    assert pt.ion_charge(6) is None  # group IV: no typical ion
    assert pt.valence(7) == 3 and pt.valence(6) == 4 and pt.valence(18) is None
    assert pt.neutrons(29, 63.55) == 35
    for z in range(1, 21):
        assert sum(pt.electron_arrangement(z)) == z


def test_real_data_passes_all_checks(fs):
    assert errors(fs) == []
    assert len(fs.types) >= 20  # SC-006
    assert fs.value("Cu", "O") == "29"
    assert fs.value("S", "a") == "6"
    assert fs.value("H2O", "m") == "18,0"
    assert fs.value("Al2O3", "b") == "Ionenbindung"
    assert fs.value("CO2", "b") == "Elektronenpaarbindung"
    assert fs.objects["Mg3N2"].name == "Magnesiumnitrid"  # computed ionic compound
    assert "Kochsalz" in fs.objects["NaCl"].aliases


def test_formula_and_equation_parser():
    assert factgen.parse_formula("Ca3(PO4)2") == {"Ca": 3, "P": 2, "O": 8}
    assert factgen.parse_formula("CO(NH2)2") == {"C": 1, "O": 1, "N": 2, "H": 4}
    left, right = factgen.parse_equation("2 H2 + O2 → 2 H2O")
    assert left == right == {"H": 4, "O": 2}


def broken(fs, key, code, value):
    records = dict(fs.records)
    records[(key, code)] = (value, records.get((key, code), ("", "own"))[1])
    return factgen.FactSet(fs.objects, fs.types, records)


def test_check_rejects_unbalanced_equation(fs):
    bad = broken(fs, "knallgas", "q", "H2 + O2 → H2O")
    assert any("not balanced" in e for e in errors(bad))


def test_check_rejects_wrong_molar_mass(fs):
    assert any("molar mass" in e for e in errors(broken(fs, "H2O", "m", "19,0")))


def test_check_rejects_inconsistent_atom(fs):
    assert any("protons" in e for e in errors(broken(fs, "Na", "p", "12")))
    assert any("arrangement" in e for e in errors(broken(fs, "Na", "v", "2, 8, 2")))


def test_check_rejects_ambiguous_reverse(fs):
    assert any("reverse values" in e for e in errors(broken(fs, "Fe", "O", "29")))


def test_check_rejects_long_value_and_bad_key(fs):
    assert any("> 50 B" in e for e in errors(broken(fs, "co2", "t", "x" * 51)))
    objects = dict(fs.objects)
    objects["Xq#"] = factgen.Obj("Xq#", "Komisch", "compound", "own")
    assert any("Object.key" in e for e in errors(factgen.FactSet(objects, fs.types, fs.records)))


def test_check_rejects_template_without_prefix(fs):
    types = dict(fs.types)
    types["O"] = replace(types["O"], template="{name} hat {v}.")
    assert any("prefix" in e for e in errors(factgen.FactSet(fs.objects, types, fs.records)))


def test_check_rejects_too_few_forms(fs):
    types = dict(fs.types)
    types["O"] = replace(types["O"], forms=types["O"].forms[:5])
    assert any(">= 12 forms" in e for e in errors(factgen.FactSet(fs.objects, types, fs.records)))
