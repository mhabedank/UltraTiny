from ultratiny.alphabet import Alphabet
from ultratiny.augment import Augment, sanitize
from ultratiny.datagen import (
    Fact,
    QTemplate,
    Relation,
    apply_template_augment,
    augmented_pairs,
    qa_pairs,
)

AB = Alphabet()
SRC = {"own", "llm"}
REF = "Das weiß ich leider nicht."


def _rel(name, answer, text, free):
    return Relation(name, [answer], [QTemplate(name, text, "train", None)], free)


def setup():
    rels = {
        "frei": _rel("frei", "{object}", "{subject}", True),
        "abweisen": _rel("abweisen", "{object}", "{subject}", True),
        "formel_von": _rel(
            "formel_von",
            "{subject} hat die Formel {object}.",
            "Welche Formel hat {subject}?",
            False,
        ),
    }
    facts = [
        ("f1", "chemie", "frei", "Was ist ein Ion?|Ion?|Was versteht man unter Ion?", "Ein Ion"),
        ("f2", "chemie", "frei", "Was ist ein Atom?|Atom?|Erkläre Atom.", "Ein Atom"),
        ("a1", "abweisen", "abweisen", "Wer ist Messi?|asdf|Was kostet ein Auto?", REF),
        ("v1", "chemie", "formel_von", "Wasser", "H2O"),
    ]
    return rels, [Fact(*f, "own") for f in facts]


def test_sanitize_typography():
    assert sanitize("„Säure“ – pH…\tx|y") == '"Säure" - pH... x y'


def test_augmented_pairs_filters_leaks_conflicts_and_sources():
    rels, facts = setup()
    train, held = qa_pairs(facts, rels)
    aug = Augment(
        phrasings={"f1": [
            ("Was genau ist ein Ion?", "llm:m"),             # ok
            ("Was versteht man unter Ion?", "llm:m"),        # held-out prompt -> dropped
            ("Was ist ein Atom?", "llm:m"),                  # belongs to f2 -> conflict, dropped
            ("Ion ☃?", "llm:m"),                             # invalid char -> dropped
            ("Ion erklären bitte", "wikipedia:x"),           # unknown source -> dropped
        ]},
        refusals=[("Wer gewinnt die Bundesliga?", "llm:m"), ("Was kostet ein Auto?", "llm:m")],
    )  # fmt: skip
    extra, stats = augmented_pairs(facts, rels, aug, train, held, AB, SRC, "abweisen")
    qs = {q: a for q, a, _ in extra}
    assert qs == {"Was genau ist ein Ion?": "Ein Ion", "Wer gewinnt die Bundesliga?": REF}
    assert stats["pairs_dropped"] == 5  # 4 phrasings + held-out refusal "Was kostet ein Auto?"


def test_template_augment_adds_train_templates_only():
    rels, _ = setup()
    aug = Augment(
        templates={
            "formel_von": [
                ("Wie lautet die Formel für {subject}?", None, "llm:m"),
                ("Welche Formel hat {subject}?", None, "llm:m"),  # duplicate
                ("Formel ohne Platzhalter?", None, "llm:m"),  # no placeholder
                ("Frag {subject}", None, "llm:m"),
            ],
            "frei": [("{subject} bitte", None, "llm:m")],
        }
    )  # free relations are not templated
    stats = apply_template_augment(rels, aug, AB, SRC)
    texts = [q.text for q in rels["formel_von"].questions]
    assert stats == {"templates_added": 2, "templates_dropped": 3}
    assert "Wie lautet die Formel für {subject}?" in texts
    assert all(q.split == "train" for q in rels["formel_von"].questions)
