from pathlib import Path

import pytest

from ultratiny.alphabet import Alphabet
from ultratiny.config import load_config
from ultratiny.datagen import (
    DataError,
    Fact,
    QTemplate,
    Relation,
    allowed_source_prefixes,
    generate,
    load_relations,
    qa_pairs,
    read_jsonl,
    read_train,
    validate,
)

ROOT = Path(__file__).resolve().parents[1]
TOPICS = {"geografie", "ueber_mich"}
SOURCES = {"own", "wikidata"}


def rel(name="r", n_train=6, n_held=2):
    qs = [QTemplate(name, f"Frage {i} {{subject}}?", "train", None) for i in range(n_train)]
    qs += [QTemplate(name, f"Anders {i} {{subject}}?", "heldout", None) for i in range(n_held)]
    return Relation(name, ["{subject} ist {object}."], qs, False)


def fact(**kw):
    base = dict(id="x/1", topic="geografie", relation="r", subject="Paris", object="Frankreich",
                source="own")  # fmt: skip
    base.update(kw)
    return Fact(**base)


def test_valid_minimal_set_passes():
    validate([fact()], {"r": rel()}, TOPICS, SOURCES, Alphabet())


@pytest.mark.parametrize(
    "f, msg",
    [
        (fact(topic="mode"), "Fact.topic"),
        (fact(relation="nix"), "has no templates"),
        (fact(subject="Paris😀"), "Fact.subject"),
        (fact(object=""), "Fact.object"),
        (fact(source="wikipedia:1"), "Fact.source"),
    ],
)
def test_invalid_facts_rejected(f, msg):
    rels = {"r": rel(), "nix2": rel("nix2")}
    with pytest.raises(DataError, match=msg):
        validate([f, fact(id="y/1", relation="nix2")], rels, TOPICS, SOURCES, Alphabet())


def test_duplicate_ids_and_template_rules():
    with pytest.raises(DataError, match="duplicate"):
        validate([fact(), fact()], {"r": rel()}, TOPICS, SOURCES, Alphabet())
    with pytest.raises(DataError, match=">= 8"):
        validate([fact()], {"r": rel(n_train=5)}, TOPICS, SOURCES, Alphabet())
    with pytest.raises(DataError, match=">= 8"):
        validate([fact()], {"r": rel(n_train=8, n_held=1)}, TOPICS, SOURCES, Alphabet())
    bad = Relation("r", ["x"], [QTemplate("r", "ohne Platzhalter", "train", None)] * 8, False)
    with pytest.raises(DataError, match="placeholder"):
        validate([fact()], {"r": bad}, TOPICS, SOURCES, Alphabet())
    with pytest.raises(DataError, match="matches no Fact.relation"):
        validate([fact()], {"r": rel(), "leer": rel("leer")}, TOPICS, SOURCES, Alphabet())


def test_heldout_templates_never_in_train(tmp_path):
    cfg = load_config(ROOT / "configs/starter.toml")
    generate(cfg, tmp_path, seed=1)
    train_q = {q for q, _ in read_train(tmp_path / "train.txt")}
    held = read_jsonl(tmp_path / "heldout.jsonl")
    assert held and train_q

    def norm(s):
        return " ".join(s.lower().replace("?", " ").replace(".", " ").replace("!", " ").split())

    assert not {norm(h["prompt"]) for h in held} & {norm(q) for q in train_q}
    rels = load_relations([ROOT / "data/templates/starter.toml"])
    for r in rels.values():
        if not r.free:
            assert len(r.questions) >= 8
            assert sum(q.split == "heldout" for q in r.questions) >= 2


def test_free_relation_holds_out_last_phrasing():
    r = Relation("frei", ["{object}"], [QTemplate("frei", "{subject}", "train", None)], True)
    f = fact(relation="frei", subject="A?|B?|C?", object="Antwort.")
    train, held = qa_pairs([f], {"frei": r})
    assert [q for q, _, _ in train] == ["A?", "B?"]
    assert [q for q, _, _ in held] == ["C?"]


def test_licenses_file_lists_sources():
    assert {"own", "wikidata"} <= allowed_source_prefixes()


def test_datagen_is_deterministic(tmp_path):
    cfg = load_config(ROOT / "configs/starter.toml")
    a = generate(cfg, tmp_path / "a", seed=5)
    b = generate(cfg, tmp_path / "b", seed=5)
    assert a["sha256"] == b["sha256"]
