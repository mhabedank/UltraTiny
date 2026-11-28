"""UTKI v1 writer + reader (specs/008-wissens-compiler contracts/image-format.md, query.md)."""

from __future__ import annotations

import hashlib
import struct
import zlib
from pathlib import Path

import pytest

from ultratiny.alphabet import EOS, Alphabet
from ultratiny.knowledge.compile import build
from ultratiny.knowledge.image import MISSING, Image, answer_bytes
from ultratiny.knowledge.topic import load_topic

MINI = Path(__file__).parent / "fixtures" / "topics" / "mini"


@pytest.fixture(scope="module")
def image() -> bytes:
    return build(load_topic(MINI))[0]


@pytest.fixture(scope="module")
def img(image) -> Image:
    im = Image(image)
    assert im.ok
    return im


def test_header(image, img):
    assert image[:4] == b"UTKI" and struct.unpack_from("<H", image, 4)[0] == 1
    assert img.topic == "mini" and img.schema_version == 3
    assert img.n_answerable == img.count_answerable()
    assert len(image) % 4 == 0


def test_deterministic():
    a, ra = build(load_topic(MINI))
    b, rb = build(load_topic(MINI))
    assert a == b and ra == rb  # SC-007


def test_competency_questions(img):
    topic = load_topic(MINI)
    for view in topic.views.values():
        v = img.view(view.name)
        for q in view.questions:
            outcome, _ = img.lookup(v, q.key.encode())
            if q.expect in ("fact", "na", "unknown"):
                assert outcome == q.expect, q
            else:
                assert img.query_view(v, q.key.encode()).decode() == q.expect, q


@pytest.mark.parametrize(
    "query, expect",
    [
        ("R Aa", "Rang von Aastadt: 1."),
        ("r 102", "Platz 102 hat Langstadt Nummer 02."),
        ("rang< 2", "Platz 2 hat Bestadt."),
        ("K Xx", "Das Kürzel von – Unbekannt."),  # unknown key after the prefix
        ("rang NL", "Rang von Nordland: keine Angabe."),  # generic not-applicable
        ("X Aa", "Unbekannt."),  # unmapped letter
        ("gibtsnicht Aa", "Unbekannt."),  # unknown view name
        ("farben NL", "Farben von Nordland: Blau und Rot."),  # card=many, value order
        ("farben< Blau", "Die Farbe Blau haben Nordland und Südland."),  # reverse, class order
        ("land< NL", "In NL liegen Aastadt, Bestadt und Cestadt."),  # ordered by rang
        (
            "land< LL",
            "In LL liegen Langstadt Nummer 01, Langstadt Nummer 02, Langstadt Nummer 03"
            " und 9 weitere.",
        ),  # fmt: skip
        ("erdteil Zz", "Erdteil: Zettstadt liegt auf Westia."),  # chain rule
        ("gruss SL", "Gruß in Südland: Hallo."),  # table rule
        ("land< Xy", "In – Unbekannt."),
    ],
)
def test_queries(img, query, expect):
    assert img.query(query).decode() == expect


def test_lists_never_exceed_100_bytes(img):
    for v in img.views:
        for k in img.candidate_keys(v):
            assert len(img.query_view(v, k)) <= 100


def test_shortened_list_is_longest_fitting_prefix(img):
    v = img.view("land<")
    text = img.query_view(v, b"LL")
    # one more item would not fit
    longer = text.replace(b" und 9 weitere.", b", Langstadt Nummer 04 und 8 weitere.")
    assert len(text) <= 100 < len(longer)


def test_status_missing_and_corrupt(image):
    assert Image(None).status == "MISSING"
    assert Image(b"\xff" * 200).status == "MISSING"
    bad = bytearray(image)
    bad[-5] ^= 0xFF  # payload CRC
    assert Image(bytes(bad)).status == "CORRUPT"
    bad = bytearray(image)
    bad[24] ^= 1  # header CRC
    assert Image(bytes(bad)).status == "CORRUPT"
    bad = bytearray(image)
    struct.pack_into("<H", bad, 40, 0xFFF0)  # offset outside the file, CRCs fixed
    struct.pack_into("<I", bad, 76, zlib.crc32(bytes(bad[:76])) & 0xFFFFFFFF)
    assert Image(bytes(bad)).status == "CORRUPT"
    assert Image(None).query("R Aa") == MISSING


def test_answer_bytes_console_mirror(img):
    ab = Alphabet(fn=True)
    toks = ab.encode("\x01RAa") + [EOS]
    assert answer_bytes(toks, ab, img) == b"Rang von Aastadt: 1."
    assert answer_bytes(toks, ab, Image(None)) == MISSING
    assert answer_bytes(ab.encode("Hallo") + [EOS], ab, img) == b"Hallo"


def test_build_report_sizes_add_up(image):
    _, report = build(load_topic(MINI))
    assert sum(report["sections"].values()) == len(image)
    assert report["sha256"] == hashlib.sha256(image).hexdigest()
    assert all(d["origin"].startswith("rule ") for d in report["derived"])
