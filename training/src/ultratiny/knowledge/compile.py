"""UTKI v1 writer (specs/008-wissens-compiler/contracts/image-format.md, research R5).

`build(topic)` validates rules and reverse directions, lays out the image (16-bit offsets, objects
grouped by class, relation-local value IDs, 1/2-byte columns, posting lists, views with slot bytes),
checks every answer against the 100-byte limit and the budget, and returns the image bytes plus the
build report (`build.json`, data-model.md "Build report"). Deterministic: the same topic files give
the same bytes.
"""

from __future__ import annotations

import hashlib
import json
import struct
import zlib
from dataclasses import dataclass
from pathlib import Path

from .rules import apply_rules, check_reverse
from .topic import RENDER_MAX, Fact, Topic, TopicError, View, load_topic

MAGIC = b"UTKI"
VERSION = 1
HEADER_SIZE = 80
NONE16 = 0xFFFF
AREA_SIZE = 0x10000
HDR = "<4sHH16s14HIII12s"  # + u32 header_crc = 80 B
assert struct.calcsize(HDR) + 4 == HEADER_SIZE

TYPE_CODE = {"text": 0, "int": 1, "dec": 2, "enum": 3, "ref": 4}
KIND_CODE = {"forward": 0, "reverse": 1, "self": 2, "profile": 3}
F_CARD_MANY, F_REVERSE, F_REVERSE_MANY, F_VAL2, F_SUBJ2 = 1, 2, 4, 8, 16
SL_NAME, SL_KEY, SL_V, SL_REL, SL_N = 1, 2, 3, 4, 5


def _pad4(b: bytearray) -> None:
    while len(b) % 4:
        b.append(0)


class Strings:
    """String area: each distinct string once, NUL-terminated (FR-012)."""

    def __init__(self):
        self.data = bytearray()
        self.off: dict[bytes, int] = {}

    def add(self, s: bytes) -> int:
        if b"\0" in s:
            raise TopicError([f"string contains NUL: {s!r}"])
        if s not in self.off:
            self.off[s] = len(self.data)
            self.data += s + b"\0"
        return self.off[s]


def encode_template(text: str, rel_index: dict[str, int]) -> bytes:
    out = bytearray()
    i = 0
    while i < len(text):
        if text[i] == "{":
            j = text.index("}", i)
            slot = text[i + 1 : j]
            if slot == "name":
                out.append(SL_NAME)
            elif slot == "key":
                out.append(SL_KEY)
            elif slot == "v":
                out.append(SL_V)
            elif slot == "n":
                out.append(SL_N)
            else:  # r:<relation>; index + 1 so the byte is never NUL
                out += bytes((SL_REL, rel_index[slot[2:]] + 1))
            i = j + 1
        else:
            out += text[i].encode()
            i += 1
    return bytes(out)


@dataclass
class Layout:
    """Class order, object numbers and per-relation value tables (shared by writer and report)."""

    order: list[str]  # object keys in object-number order
    number: dict[str, int]
    class_ranges: list[tuple[int, int]]
    class_index: dict[str, int]


def layout(topic: Topic, facts: list[Fact]) -> Layout:
    order: list[str] = []
    ranges: list[tuple[int, int]] = []
    class_index = {c: i for i, c in enumerate(topic.classes)}
    for cname, cdef in topic.classes.items():
        objs = [o for o in topic.objects if o.cls == cname]
        if cdef.order_by:
            val = {f.subject: int(f.value) for f in facts if f.relation == cdef.order_by}
            missing = [o.key for o in objs if o.key not in val]
            if missing:
                raise TopicError(
                    [f"class {cname}: order_by {cdef.order_by!r} missing for {missing[:5]}"]
                )
            seen: dict[int, str] = {}
            for o in objs:
                if val[o.key] in seen:
                    raise TopicError(
                        [
                            f"class {cname}: order_by tie {val[o.key]} between "
                            f"{seen[val[o.key]]} and {o.key}"
                        ]
                    )
                seen[val[o.key]] = o.key
            objs.sort(key=lambda o: val[o.key])
        ranges.append((len(order), len(objs)))
        order += [o.key for o in objs]
    if len(order) > 65535:
        raise TopicError([f"more than 65535 objects ({len(order)})"])
    return Layout(order, {k: i for i, k in enumerate(order)}, ranges, class_index)


def _block(lists: list[list[int]], width: int) -> bytearray:
    """Posting-list block: u16 offsets[n+1] (in entries) + entries (contracts/image-format.md)."""
    b = bytearray()
    pos = 0
    offs = [0]
    for lst in lists:
        pos += len(lst)
        offs.append(pos)
    if pos > 65535:
        raise TopicError([f"posting list block with {pos} entries (max 65535)"])
    for o in offs:
        b += struct.pack("<H", o)
    for lst in lists:
        for x in lst:
            b += struct.pack("<B" if width == 1 else "<H", x)
    _pad4(b)
    return b


def write_image(
    topic: Topic, facts: list[Fact], lay: Layout, n_answerable: int = 0
) -> tuple[bytes, dict]:
    strings = Strings()
    objs = {o.key: o for o in topic.objects}
    rel_names = list(topic.relations)
    rel_index = {r: i for i, r in enumerate(rel_names)}
    by_rel: dict[str, list[Fact]] = {r: [] for r in rel_names}
    for f in facts:
        by_rel[f.relation].append(f)

    # string order: keys and names first, then values, then names of relations/views and texts
    for k in lay.order:
        strings.add(k.encode())
        strings.add(objs[k].name.encode())

    classes_b = bytearray()
    for first, count in lay.class_ranges:
        classes_b += struct.pack("<HH", first, count)
    objects_b = bytearray()
    for k in lay.order:
        objects_b += struct.pack("<HH", strings.off[k.encode()], strings.off[objs[k].name.encode()])
    keyidx = sorted(range(len(lay.order)), key=lambda i: lay.order[i].encode())
    keyidx_b = bytearray()
    for i in keyidx:
        keyidx_b += struct.pack("<H", i)
    _pad4(keyidx_b)

    # relation data: (entry fields, values bytes, forward bytes, reverse bytes)
    rel_data = []
    for name in rel_names:
        rel = topic.relations[name]
        sci = lay.class_index[rel.subject]
        first, n_subj = lay.class_ranges[sci]
        fl = by_rel[name]
        if rel.type == "ref":
            vals = sorted({f.value for f in fl}, key=lambda s: s.encode())
            entries = [lay.number[v] for v in vals]
        else:
            vals = sorted({f.value for f in fl}, key=lambda s: s.encode())
            entries = [strings.add(v.encode()) for v in vals]
        if len(vals) > 65534:
            raise TopicError([f"relation {name}: more than 65534 values"])
        vid = {v: i for i, v in enumerate(vals)}
        wv = 1 if len(vals) <= 254 else 2
        ws = 1 if n_subj <= 255 else 2
        flags = (F_VAL2 if wv == 2 else 0) | (F_SUBJ2 if ws == 2 else 0)
        values_b = bytearray()
        for e in entries:
            values_b += struct.pack("<H", e)
        _pad4(values_b)
        per_subj: list[list[int]] = [[] for _ in range(n_subj)]
        for f in fl:
            per_subj[lay.number[f.subject] - first].append(vid[f.value])
        if rel.card == "one":
            sentinel = 0xFF if wv == 1 else 0xFFFF
            fwd_b = bytearray()
            for lst in per_subj:
                fwd_b += struct.pack("<B" if wv == 1 else "<H", lst[0] if lst else sentinel)
            _pad4(fwd_b)
        else:
            flags |= F_CARD_MANY
            fwd_b = _block([sorted(lst) for lst in per_subj], wv)
        rev_b = None
        if rel.reverse != "none":
            flags |= F_REVERSE | (F_REVERSE_MANY if rel.reverse == "many" else 0)
            per_val: list[list[int]] = [[] for _ in vals]
            for f in fl:
                per_val[vid[f.value]].append(lay.number[f.subject] - first)
            rev_b = _block([sorted(set(lst)) for lst in per_val], ws)
        target = lay.class_index[rel.target] if rel.type == "ref" else 0xFF
        rel_data.append(
            (
                strings.add(name.encode()),
                TYPE_CODE[rel.type],
                flags,
                sci,
                target,
                len(vals),
                values_b,
                fwd_b,
                rev_b,
            )
        )

    views_s = []
    for v in topic.views.values():
        views_s.append(
            (
                strings.add(v.name.encode()),
                KIND_CODE[v.kind],
                ord(v.letter) if v.letter else 0,
                rel_index[v.relation] if v.relation else 0xFF,
                sum(1 << lay.class_index[c] for c in v.classes),
                strings.add(encode_template(v.template, rel_index)),
                strings.add(encode_template(v.not_applicable, rel_index))
                if v.not_applicable
                else NONE16,
                strings.add(encode_template(v.more, rel_index)) if v.more else NONE16,
            )
        )
    t = topic.texts
    texts_s = [
        strings.add(x.encode())
        for x in (t.unknown, t.not_applicable, t.fallback_sep, t.list_sep, t.list_last)
    ] + [NONE16]

    # layout: header | classes | objects | keyidx | relations | views | texts | rel data | strings
    off = HEADER_SIZE
    off_classes = off
    off += len(classes_b)
    off_objects = off
    off += len(objects_b)
    off_keyidx = off
    off += len(keyidx_b)
    off_relations = off
    off += 16 * len(rel_data)
    off_views = off
    off += 12 * len(views_s)
    off_texts = off
    off += 12
    data_b = bytearray()
    rel_entries = bytearray()
    sizes = {"values": 0, "columns": 0, "lists": 0}
    for name_s, tcode, flags, sci, target, n_vals, values_b, fwd_b, rev_b in rel_data:
        o_vals = off + len(data_b)
        data_b += values_b
        o_fwd = off + len(data_b)
        data_b += fwd_b
        o_rev = NONE16
        if rev_b is not None:
            o_rev = off + len(data_b)
            data_b += rev_b
        sizes["values"] += len(values_b)
        sizes["lists" if flags & F_CARD_MANY else "columns"] += len(fwd_b)
        sizes["lists"] += len(rev_b) if rev_b is not None else 0
        rel_entries += struct.pack(
            "<HBBBBHHHHH", name_s, tcode, flags, sci, target, n_vals, o_vals, o_fwd, o_rev, 0
        )
    off += len(data_b)
    off_strings = off
    strings_b = bytearray(strings.data)
    _pad4(strings_b)
    total = off_strings + len(strings_b)
    if total > 65535:
        raise TopicError([f"image {total} B does not fit 16-bit offsets"])
    views_b = bytearray()
    for vs in views_s:
        views_b += struct.pack("<HBBBBHHH", *vs)
    texts_b = struct.pack("<6H", *texts_s)
    payload = bytes(
        classes_b + objects_b + keyidx_b + rel_entries + views_b + texts_b + data_b + strings_b
    )
    data_sha = int.from_bytes(topic.data_sha[:4], "big")
    hdr = struct.pack(
        HDR,
        MAGIC,
        VERSION,
        HEADER_SIZE,
        topic.id.encode().ljust(16, b"\0"),
        topic.schema_version,
        len(lay.class_ranges),
        len(lay.order),
        len(rel_data),
        len(views_s),
        min(n_answerable, 65535),
        off_strings,
        len(strings_b),
        off_classes,
        off_objects,
        off_keyidx,
        off_relations,
        off_views,
        off_texts,
        len(payload),
        data_sha,
        zlib.crc32(payload) & 0xFFFFFFFF,
        b"\0" * 12,
    )
    image = hdr + struct.pack("<I", zlib.crc32(hdr) & 0xFFFFFFFF) + payload
    section = {
        "header": HEADER_SIZE,
        "classes": len(classes_b),
        "objects": len(objects_b),
        "keyidx": len(keyidx_b),
        "relations": len(rel_entries),
        "views": len(views_b),
        "texts": len(texts_b),
        "values": sizes["values"],
        "columns": sizes["columns"],
        "lists": sizes["lists"],
        "strings": len(strings_b),
    }
    return image, section


def check_answers(topic: Topic, img) -> list[str]:
    """Every answer the image can give fits RENDER_MAX bytes; lists fit with one item (FR-004)."""
    errors: list[str] = []
    for view in img.views:
        for key in img.candidate_keys(view):
            for text in (img.query_view(view, key), img.unknown_answer(view)):
                if len(text) > RENDER_MAX:
                    errors.append(
                        f"schema.toml:[views.{view.name}]: answer for {key!r} is "
                        f"{len(text)} B > {RENDER_MAX}: {text.decode()!r}"
                    )
        if errors:
            break
    return errors


def check_questions(topic: Topic, img) -> list[str]:
    errors = []
    for view in topic.views.values():
        v = img.view(view.name)
        for q in view.questions:
            outcome, _ = img.lookup(v, q.key.encode())
            got = img.query_view(v, q.key.encode()).decode()
            if q.expect in ("unknown", "na", "fact"):
                ok = outcome == q.expect
            else:
                ok = got == q.expect
            if not ok:
                errors.append(
                    f"schema.toml:[views.{view.name}]: question {q.question!r} key "
                    f"{q.key!r}: expected {q.expect!r}, got {outcome} {got!r}"
                )
    return errors


def build(topic: Topic, check: bool = True) -> tuple[bytes, dict]:
    """Compile a validated topic into UTKI bytes and the build report."""
    from .image import Image

    facts, per_rule = apply_rules(topic)
    check_reverse(topic, facts)
    lay = layout(topic, facts)
    image, section = write_image(topic, facts, lay)
    img = Image(image)
    if not img.ok:
        raise TopicError([f"internal: written image does not validate ({img.status})"])
    errors = check_answers(topic, img)
    if errors:
        raise TopicError(errors[:20])
    f7 = img.count_answerable()
    image, section = write_image(topic, facts, lay, f7)
    if len(image) > topic.budget_bytes:
        raise TopicError(
            [
                f"{topic.root / 'topic.toml'}: image {len(image)} B exceeds the budget "
                f"{topic.budget_bytes} B"
            ]
        )
    img = Image(image)
    if check:
        errors = check_questions(topic, img)
        if errors:
            raise TopicError(errors)
    explicit = len(topic.facts)
    report = {
        "topic": topic.id,
        "schema_version": topic.schema_version,
        "classes": {c: n for c, (_, n) in zip(topic.classes, lay.class_ranges, strict=True)},
        "objects": len(lay.order),
        "relations": len(topic.relations),
        "views": len(topic.views),
        "facts_explicit": explicit,
        "facts_derived": len(facts) - explicit,
        "derived_per_rule": per_rule,
        "facts_per_relation": {r: sum(f.relation == r for f in facts) for r in topic.relations},
        "answerable": f7,
        "answerable_per_view": {v.name: img.count_answerable(v) for v in img.views},
        "bytes": len(image),
        "budget_bytes": topic.budget_bytes,
        "bytes_per_answerable": round(len(image) / f7, 2) if f7 else None,
        "sections": section,
        "sha256": hashlib.sha256(image).hexdigest(),
        "data_sha256": topic.data_sha.hex(),
        "derived": [
            {"subject": f.subject, "relation": f.relation, "value": f.value, "origin": f.origin}
            for f in facts[explicit:]
        ],
    }
    return image, report


def build_topic(root: Path | str, out: Path | str | None = None) -> tuple[bytes, dict]:
    topic = load_topic(root)
    image, report = build(topic)
    if out is not None:
        out = Path(out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(image)
        out.with_suffix(".build.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=1, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    return image, report


__all__ = ["build", "build_topic", "View"]
