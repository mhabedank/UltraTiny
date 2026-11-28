"""UTKI v1 reader: the Python reference of runtime/src/knowledge.c (constitution III).

Layout: specs/008-wissens-compiler/contracts/image-format.md. Lookup, rendering, lists and the
console mirror: contracts/query.md. Both readers MUST render identical bytes.
"""

from __future__ import annotations

import struct
import zlib
from dataclasses import dataclass
from pathlib import Path

from ..alphabet import EOS, FN, Alphabet

MAGIC = b"UTKI"
VERSION = 1
HEADER_SIZE = 80
AREA_SIZE = 0x10000
MAX_SIZE = int(AREA_SIZE * 0.9)  # 58,982 B (UT_FACTS_MAX)
NONE16 = 0xFFFF
RENDER_MAX = 100
HDR = "<4sHH16s14HIII12s"

F_CARD_MANY, F_REVERSE, F_REVERSE_MANY, F_VAL2, F_SUBJ2 = 1, 2, 4, 8, 16
K_FORWARD, K_REVERSE, K_SELF, K_PROFILE = 0, 1, 2, 3
SL_NAME, SL_KEY, SL_V, SL_REL, SL_N = 1, 2, 3, 4, 5

# The only built-in text (topic-neutral, unchanged from spec 006; FR-013).
MISSING = b"Die Faktentabelle fehlt, Faktenfragen gehen gerade nicht."


@dataclass
class Rel:
    index: int
    name: bytes
    type: int
    flags: int
    subject: int
    target: int
    n_values: int
    off_values: int
    off_forward: int
    off_reverse: int


@dataclass
class ViewEntry:
    index: int
    name: str
    kind: int
    letter: str
    relation: int
    mask: int
    template: int
    na: int
    more: int


class Image:
    """Validated knowledge image with lookup and rendering."""

    def __init__(self, data: bytes | None):
        self.data = bytes(data or b"")
        self.status = self._validate()
        self.views: list[ViewEntry] = []
        if self.ok:
            self._load()

    # ---------------------------------------------------------------- validation

    @property
    def ok(self) -> bool:
        return self.status == "OK"

    def _validate(self) -> str:
        d = self.data
        if len(d) < HEADER_SIZE or d[:4] != MAGIC:
            return "MISSING"
        h = struct.unpack(HDR, d[:76])
        (
            _,
            ver,
            hsize,
            topic,
            self.schema_version,
            nc,
            no,
            nr,
            nv,
            self.n_answerable,
            self.off_strings,
            self.size_strings,
            self.off_classes,
            self.off_objects,
            self.off_keyidx,
            self.off_relations,
            self.off_views,
            self.off_texts,
            psize,
            self.data_sha,
            pcrc,
            _r,
        ) = h
        if ver != VERSION or hsize != HEADER_SIZE:
            return "CORRUPT"
        if zlib.crc32(d[:76]) & 0xFFFFFFFF != struct.unpack("<I", d[76:80])[0]:
            return "CORRUPT"
        end = HEADER_SIZE + psize
        if end > len(d) or end > AREA_SIZE:
            return "CORRUPT"
        self.end = end
        if not (1 <= nc <= 8 and 1 <= no and nr <= 254 and 1 <= nv <= 254):
            return "CORRUPT"
        secs = [
            (self.off_classes, 4 * nc),
            (self.off_objects, 4 * no),
            (self.off_keyidx, 2 * no),
            (self.off_relations, 16 * nr),
            (self.off_views, 12 * nv),
            (self.off_texts, 12),
            (self.off_strings, self.size_strings),
        ]
        for off, size in secs:
            if off < HEADER_SIZE or off % 4 or off + size > end:
                return "CORRUPT"
        if zlib.crc32(d[HEADER_SIZE:end]) & 0xFFFFFFFF != pcrc:
            return "CORRUPT"
        self.topic = topic.rstrip(b"\0").decode("utf-8", "replace")
        self.n_classes, self.n_objects, self.n_relations, self.n_views = nc, no, nr, nv
        nxt = 0
        for i in range(nc):
            first, count = (
                self._u16(self.off_classes + 4 * i),
                self._u16(self.off_classes + 4 * i + 2),
            )
            if first != nxt:
                return "CORRUPT"
            nxt += count
        if nxt != no:
            return "CORRUPT"
        return "OK"

    def _load(self) -> None:
        self.classes = [
            (self._u16(self.off_classes + 4 * i), self._u16(self.off_classes + 4 * i + 2))
            for i in range(self.n_classes)
        ]
        self.rels = []
        for i in range(self.n_relations):
            o = self.off_relations + 16 * i
            name, t, fl, subj, tgt, nv, ov, of, orv, _ = struct.unpack_from(
                "<HBBBBHHHHH", self.data, o
            )
            self.rels.append(Rel(i, self.str(name), t, fl, subj, tgt, nv, ov, of, orv))
        for i in range(self.n_views):
            o = self.off_views + 12 * i
            name, kind, letter, rel, mask, tpl, na, more = struct.unpack_from(
                "<HBBBBHHH", self.data, o
            )
            self.views.append(
                ViewEntry(
                    i,
                    self.str(name).decode(),
                    kind,
                    chr(letter) if letter else "",
                    rel,
                    mask,
                    tpl,
                    na,
                    more,
                )
            )
        tx = struct.unpack_from("<6H", self.data, self.off_texts)
        self.t_unknown, self.t_na, self.t_sep, self.t_list_sep, self.t_list_last = (
            self.str(x) for x in tx[:5]
        )

    # ---------------------------------------------------------------- primitives

    def _u8(self, off: int) -> int:
        return self.data[off]

    def _u16(self, off: int) -> int:
        return struct.unpack_from("<H", self.data, off)[0]

    def str(self, off: int) -> bytes:
        if off == NONE16 or off >= self.size_strings:
            return b""
        a = self.off_strings + off
        return self.data[a : self.data.index(b"\0", a, self.end)]

    def obj_key(self, n: int) -> bytes:
        return self.str(self._u16(self.off_objects + 4 * n))

    def obj_name(self, n: int) -> bytes:
        return self.str(self._u16(self.off_objects + 4 * n + 2))

    def obj_class(self, n: int) -> int:
        for i, (first, count) in enumerate(self.classes):
            if first <= n < first + count:
                return i
        return -1

    def find_object(self, key: bytes) -> int | None:
        lo, hi = 0, self.n_objects
        while lo < hi:
            mid = (lo + hi) // 2
            n = self._u16(self.off_keyidx + 2 * mid)
            k = self.obj_key(n)
            if k == key:
                return n
            if k < key:
                lo = mid + 1
            else:
                hi = mid
        return None

    # ---------------------------------------------------------------- relations

    def _val_entry(self, r: Rel, vid: int) -> int:
        return self._u16(r.off_values + 2 * vid)

    def value_key(self, r: Rel, vid: int) -> bytes:
        """What a reverse query compares with: the value string, or the target object's key."""
        e = self._val_entry(r, vid)
        return self.obj_key(e) if r.type == 4 else self.str(e)

    def value_text(self, r: Rel, vid: int) -> bytes:
        """What is printed: the value string, or the target object's name."""
        e = self._val_entry(r, vid)
        return self.obj_name(e) if r.type == 4 else self.str(e)

    def find_value(self, r: Rel, key: bytes) -> int | None:
        lo, hi = 0, r.n_values
        while lo < hi:
            mid = (lo + hi) // 2
            k = self.value_key(r, mid)
            if k == key:
                return mid
            if k < key:
                lo = mid + 1
            else:
                hi = mid
        return None

    def forward_values(self, r: Rel, local: int) -> list[int]:
        wv = 2 if r.flags & F_VAL2 else 1
        if not r.flags & F_CARD_MANY:
            off = r.off_forward + wv * local
            v = self._u16(off) if wv == 2 else self._u8(off)
            return [] if v == (0xFFFF if wv == 2 else 0xFF) else [v]
        return self._posting(r.off_forward, self.classes[r.subject][1], local, wv)

    def reverse_subjects(self, r: Rel, vid: int) -> list[int]:
        ws = 2 if r.flags & F_SUBJ2 else 1
        return self._posting(r.off_reverse, r.n_values, vid, ws)

    def _posting(self, block: int, n: int, i: int, width: int) -> list[int]:
        a, b = self._u16(block + 2 * i), self._u16(block + 2 * i + 2)
        base = block + 2 * (n + 1)
        if width == 1:
            return [self._u8(base + j) for j in range(a, b)]
        return [self._u16(base + 2 * j) for j in range(a, b)]

    # ---------------------------------------------------------------- views

    def view(self, letter_or_name: str) -> ViewEntry | None:
        if not self.ok or not letter_or_name:
            return None
        for v in self.views:
            if (
                len(letter_or_name) == 1 and v.letter == letter_or_name
            ) or v.name == letter_or_name:
                return v
        return None

    def view_by_letter(self, letter: str) -> ViewEntry | None:
        if not self.ok:
            return None
        return next((v for v in self.views if v.letter == letter), None)

    def prefix(self, v: ViewEntry) -> bytes:
        tpl = self.str(v.template)
        for i, b in enumerate(tpl):
            if b <= SL_N:
                return tpl[:i]
        return tpl

    # ---------------------------------------------------------------- lookup

    def _subject(self, v: ViewEntry, key: bytes):
        """(outcome, object number or None, items or None) — steps 2–3 of query.md "Lookup"."""
        if v.kind == K_REVERSE:
            r = self.rels[v.relation]
            vid = self.find_value(r, key)
            if vid is None:
                return "unknown", None, None
            first = self.classes[r.subject][0]
            subs = [first + s for s in self.reverse_subjects(r, vid)]
            if not subs:
                return "unknown", None, None
            return "fact", subs[0], [self.obj_name(n) for n in subs]
        n = self.find_object(key)
        if n is None:
            return "unknown", None, None
        if not (v.mask >> self.obj_class(n)) & 1:
            return "na", n, None
        if v.kind == K_FORWARD:
            r = self.rels[v.relation]
            vals = self.forward_values(r, n - self.classes[r.subject][0])
            if not vals:
                return "na", n, None
            return "fact", n, [self.value_text(r, x) for x in vals]
        if v.kind == K_PROFILE:
            for _i, rel in self._rel_slots(self.str(v.template)):
                if self._single(rel, n) is None:
                    return "na", n, None
        return "fact", n, None

    def _rel_slots(self, tpl: bytes):
        i = 0
        while i < len(tpl):
            if tpl[i] == SL_REL:
                yield i, self.rels[tpl[i + 1] - 1]
                i += 2
            else:
                i += 1

    def _single(self, r: Rel, n: int) -> bytes | None:
        if self.obj_class(n) != r.subject:
            return None
        vals = self.forward_values(r, n - self.classes[r.subject][0])
        return self.value_text(r, vals[0]) if vals else None

    def _expand(
        self, tpl: bytes, name: bytes, key: bytes, n: int | None, v: bytes, more_n=0
    ) -> bytes:
        out = bytearray()
        i = 0
        while i < len(tpl):
            b = tpl[i]
            if b == SL_NAME:
                out += name
            elif b == SL_KEY:
                out += key
            elif b == SL_V:
                out += v
            elif b == SL_N:
                out += str(more_n).encode()
            elif b == SL_REL:
                i += 1
                if n is not None:
                    out += self._single(self.rels[tpl[i] - 1], n) or b""
            else:
                out.append(b)
            i += 1
        return bytes(out)

    def _list_text(self, v: ViewEntry, items: list[bytes], budget: int) -> bytes:
        """query.md "Lists": full list if it fits, else the longest prefix plus `more`."""
        if len(items) == 1:
            return items[0]
        full = self.t_list_sep.join(items[:-1]) + self.t_list_last + items[-1]
        if len(full) <= budget:
            return full
        more_tpl = self.str(v.more)
        best = None
        for k in range(1, len(items)):
            cand = self.t_list_sep.join(items[:k]) + self._expand(
                more_tpl, b"", b"", None, b"", len(items) - k
            )
            if len(cand) <= budget:
                best = cand
            else:
                break
        if best is None:  # the compiler guarantees L(1) fits; keep the first item regardless
            best = items[0] + self._expand(more_tpl, b"", b"", None, b"", len(items) - 1)
        return best

    def lookup(self, v: ViewEntry, key: bytes) -> tuple[str, bytes]:
        """(outcome, bytes to print after the prefix) for outcomes fact / na / unknown."""
        if not self.ok:
            return "missing", MISSING
        outcome, n, items = self._subject(v, key)
        if outcome == "unknown":
            return "unknown", self.t_sep + self.t_unknown
        name = self.obj_name(n)
        if outcome == "na":
            if v.na == NONE16:
                return "na", name + self.t_na
            return "na", self._expand(self.str(v.na), name, key, n, b"")
        tpl = self.str(v.template)
        pre = self.prefix(v)
        if items is None:
            vtext = b""
        elif len(items) == 1:
            vtext = items[0]
        else:
            a = len(self._expand(tpl, name, key, n, b""))
            vtext = self._list_text(v, items, RENDER_MAX - a)
        full = self._expand(tpl, name, key, n, vtext)
        return "fact", full[len(pre) :]

    # ---------------------------------------------------------------- full answers

    def query_view(self, v: ViewEntry | None, key: bytes) -> bytes:
        """Full answer (prefix + rest) as the console prints it for a known view."""
        if not self.ok:
            return MISSING
        if v is None:
            return self.t_unknown
        _, rest = self.lookup(v, key)
        return self.prefix(v) + rest

    def unknown_answer(self, v: ViewEntry) -> bytes:
        return self.prefix(v) + self.t_sep + self.t_unknown

    def legacy_answer(self, letter: str, key: bytes) -> bytes:
        """What the console prints for the function output <fn> letter key <eos>."""
        if not self.ok:
            return MISSING
        return self.query_view(self.view_by_letter(letter), key)

    def query(self, text: str) -> bytes:
        """`/wissen <view-or-letter> <key>` (query.md "Direct query command")."""
        if not self.ok:
            return MISSING
        head, _, key = text.partition(" ")
        v = self.view_by_letter(head) if len(head) == 1 else self.view(head)
        if v is not None and len(head) > 1 and v.name != head:
            v = None
        return self.query_view(v, key.encode())

    # ---------------------------------------------------------------- coverage

    def candidate_keys(self, v: ViewEntry) -> list[bytes]:
        if v.kind == K_REVERSE:
            r = self.rels[v.relation]
            return [self.value_key(r, i) for i in range(r.n_values)]
        return [self.obj_key(n) for n in range(self.n_objects) if (v.mask >> self.obj_class(n)) & 1]

    def count_answerable(self, v: ViewEntry | None = None) -> int:
        """F7: distinct (view, key) whose outcome is "fact" (research R9)."""
        views = [v] if v is not None else self.views
        return sum(
            1 for w in views for k in self.candidate_keys(w) if self._subject(w, k)[0] == "fact"
        )


def read(path: Path | str | None) -> Image:
    if path is None or not Path(path).exists():
        return Image(None)
    return Image(Path(path).read_bytes())


# ---------------------------------------------------------------- console mirror


def answer_bytes(tokens: list[int], ab: Alphabet, image: Image | None) -> bytes:
    """Bytes the console prints for one generated answer (006 function-output.md behaviour)."""
    if not tokens or tokens[0] != FN or not ab.fn:
        text = "".join(ab.symbols[t - ab.n_special] for t in tokens if t >= ab.n_special)
        return text.encode()
    letter = None
    if len(tokens) > 1 and tokens[1] >= ab.n_special:
        ch = ab.symbols[tokens[1] - ab.n_special]
        if ch.isascii() and ch.isalpha():
            letter = ch
    key = bytearray()
    for tok in tokens[2:]:
        if tok in (EOS, FN):
            break
        if tok >= ab.n_special:
            key += ab.symbols[tok - ab.n_special].encode()
    if image is None or not image.ok:
        return MISSING
    if letter is None:
        return image.t_unknown
    return image.legacy_answer(letter, bytes(key))


def function_output(tokens: list[int], ab: Alphabet) -> str | None:
    """`type + key` of a function output (without <fn>), or None for a text answer."""
    if not tokens or tokens[0] != FN:
        return None
    return ab.decode([t for t in tokens[1:] if t not in (EOS, FN)])
