"""UTFT v1 fact table: writer, reader, lookup and answer rendering.

Binary layout and lookup rules: specs/006-hybrid-chemielehrer/contracts/fact-table-format.md.
Console behaviour for function output: contracts/function-output.md.

This module is the parity twin of runtime/src/facts.c (+ the fn part of console.c): both MUST
produce byte-identical answers for the same table and token sequence (constitution III).
"""

from __future__ import annotations

import hashlib
import re
import struct
import zlib
from dataclasses import dataclass
from pathlib import Path

from .alphabet import EOS, FN, Alphabet
from .factgen import KINDS, SLOT, FactSet

MAGIC = b"UTFT"
VERSION = 1
HEADER_SIZE = 64
AREA_SIZE = 0x10000
MAX_SIZE = int(AREA_SIZE * 0.9)  # 58,982 B: 10 % headroom (UT_FACTS_MAX)
RENDER_MAX = 100
NONE = 0xFFFFFFFF

F_NEEDS_VALUE = 1
F_REVERSE = 2

SL_NAME, SL_KEY, SL_VALUE, SL_OTHER = 1, 2, 3, 4

# Fixed texts (identical in runtime/src/facts.c).
UNKNOWN = "Das weiß ich leider nicht.".encode()
MISSING = b"Die Faktentabelle fehlt, Faktenfragen gehen gerade nicht."
GENERIC_NA = b": dazu habe ich keine Angabe."  # after the name, continues the prefix
FALLBACK_SEP = "– ".encode()  # every prefix ends with a space (factgen.check)

_HDR = "<4s14I"  # magic + 14 u32 = 60 B, header CRC appended
assert struct.calcsize(_HDR) == 60


class TableError(ValueError):
    pass


def encode_template(t: str) -> bytes:
    """`{name}`/`{key}`/`{v}`/`{X}` -> control bytes 0x01/0x02/0x03/0x04 X."""
    out = bytearray()
    pos = 0
    for m in SLOT.finditer(t):
        out += t[pos : m.start()].encode()
        s = m.group(1)
        if s == "name":
            out.append(SL_NAME)
        elif s == "key":
            out.append(SL_KEY)
        elif s == "v":
            out.append(SL_VALUE)
        else:
            out += bytes([SL_OTHER, ord(s)])
        pos = m.end()
    out += t[pos:].encode()
    return bytes(out)


# ---------------------------------------------------------------- writer


def build_bytes(fs: FactSet) -> bytes:
    """Serialize a checked FactSet to UTFT v1 (deterministic)."""
    strings = bytearray()
    index: dict[bytes, int] = {}

    def s_off(b: bytes) -> int:
        if b not in index:
            index[b] = len(strings)
            strings.extend(b + b"\0")
        return index[b]

    codes = sorted(fs.types)
    keys = sorted(fs.objects, key=lambda k: k.encode())
    obj_idx = {k: i for i, k in enumerate(keys)}
    types_b = bytearray()
    for c in codes:
        t = fs.types[c]
        flags = (F_NEEDS_VALUE if t.needs_value else 0) | (F_REVERSE if t.reverse_of else 0)
        kinds = sum(KINDS[k] for k in t.kinds)
        na = s_off(encode_template(t.not_applicable)) if t.not_applicable else NONE
        types_b += struct.pack("<BBBBIII", ord(c), flags, kinds,
                               ord(t.reverse_of) if t.reverse_of else 0,
                               s_off(encode_template(t.template)), na, 0)  # fmt: skip
    objs_b = bytearray()
    for k in keys:
        o = fs.objects[k]
        objs_b += struct.pack("<IIB3x", s_off(k.encode()), s_off(o.name.encode()), KINDS[o.kind])
    recs = sorted(((obj_idx[k], c, v) for (k, c), (v, _) in fs.records.items()),
                  key=lambda r: (r[0], r[1]))  # fmt: skip
    recs_b = bytearray()
    for oi, c, v in recs:
        recs_b += struct.pack("<HBxI", oi, ord(c), s_off(v.encode()))
    while len(strings) % 4:
        strings.append(0)
    types_off = HEADER_SIZE
    objects_off = types_off + len(types_b)
    records_off = objects_off + len(objs_b)
    strings_off = records_off + len(recs_b)
    payload = bytes(types_b + objs_b + recs_b + strings)
    sha4 = int.from_bytes(hashlib.sha256(payload).digest()[:4], "little")
    hdr = struct.pack(_HDR, MAGIC, VERSION, HEADER_SIZE, len(codes), len(keys), len(recs),
                      types_off, objects_off, records_off, strings_off, len(strings),
                      len(payload), zlib.crc32(payload) & 0xFFFFFFFF, sha4, 0)  # fmt: skip
    data = hdr + struct.pack("<I", zlib.crc32(hdr) & 0xFFFFFFFF) + payload
    if len(data) > MAX_SIZE:
        raise TableError(f"fact table {len(data)} B > {MAX_SIZE} B (90 % of the 64 KB area)")
    return data


def write(fs: FactSet, path: Path) -> bytes:
    data = build_bytes(fs)
    Table(data).check_rendered(fs)
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return data


# ---------------------------------------------------------------- reader / lookup


@dataclass
class TypeEntry:
    code: str
    flags: int
    kinds: int
    reverse_of: str
    template: int
    not_applicable: int


class Table:
    """UTFT reader mirroring runtime/src/facts.c (status, lookup, rendering)."""

    def __init__(self, data: bytes | None):
        self.data = data or b""
        self.status = self._validate()

    @property
    def ok(self) -> bool:
        return self.status == "OK"

    def _validate(self) -> str:
        d = self.data
        if len(d) < HEADER_SIZE or d[:4] != MAGIC:
            return "MISSING"
        h = struct.unpack(_HDR, d[:60])
        (_, ver, hsize, nt, no, nr, t_off, o_off, r_off, s_off, s_size, p_size, p_crc,
         self.sha4, _r) = h  # fmt: skip
        if ver != VERSION or hsize != HEADER_SIZE:
            return "CORRUPT"
        if zlib.crc32(d[:60]) & 0xFFFFFFFF != struct.unpack("<I", d[60:64])[0]:
            return "CORRUPT"
        end = HEADER_SIZE + p_size
        if (end > len(d) or end > AREA_SIZE or not 1 <= nt <= 52 or not 1 <= no <= 4096
                or nr > 65535 or t_off != HEADER_SIZE or o_off != t_off + 16 * nt
                or r_off != o_off + 12 * no or s_off != r_off + 8 * nr
                or s_off + s_size != end or (p_size | s_size) & 3):  # fmt: skip
            return "CORRUPT"
        if zlib.crc32(d[HEADER_SIZE:end]) & 0xFFFFFFFF != p_crc:
            return "CORRUPT"
        self.nt, self.no, self.nr = nt, no, nr
        self.t_off, self.o_off, self.r_off = t_off, o_off, r_off
        self.s_off, self.s_size = s_off, s_size
        self.n_bytes = end
        return "OK"

    def _str(self, off: int) -> bytes:
        if off >= self.s_size:
            return b""
        a = self.s_off + off
        b = self.data.index(b"\0", a, self.n_bytes)
        return self.data[a:b]

    def find_type(self, code: str | None) -> TypeEntry | None:
        if not self.ok or code is None:
            return None
        for i in range(self.nt):
            c, fl, kinds, rev, tpl, na, _ = struct.unpack_from("<BBBBIII", self.data,
                                                               self.t_off + 16 * i)  # fmt: skip
            if chr(c) == code:
                return TypeEntry(chr(c), fl, kinds, chr(rev) if rev else "", tpl, na)
        return None

    def _obj(self, i: int) -> tuple[bytes, bytes, int]:
        k, n, kind = struct.unpack_from("<IIB", self.data, self.o_off + 12 * i)
        return self._str(k), self._str(n), kind

    def find_object(self, key: bytes) -> int | None:
        lo, hi = 0, self.no
        while lo < hi:
            mid = (lo + hi) // 2
            k = self._obj(mid)[0]
            if k == key:
                return mid
            if k < key:
                lo = mid + 1
            else:
                hi = mid
        return None

    def _rec(self, i: int) -> tuple[int, str, int]:
        oi, c, v = struct.unpack_from("<HBxI", self.data, self.r_off + 8 * i)
        return oi, chr(c), v

    def find_value(self, oi: int, code: str) -> bytes | None:
        lo, hi = 0, self.nr
        while lo < hi:
            mid = (lo + hi) // 2
            roi, rc, v = self._rec(mid)
            if (roi, rc) == (oi, code):
                return self._str(v)
            if (roi, ord(rc)) < (oi, ord(code)):
                lo = mid + 1
            else:
                hi = mid
        return None

    def prefix(self, t: TypeEntry) -> bytes:
        tpl = self._str(t.template)
        m = re.search(rb"[\x01-\x04]", tpl)
        return tpl[: m.start()] if m else tpl

    def _expand(self, tpl: bytes, name: bytes, key: bytes, value: bytes | None, oi: int) -> bytes:
        out = bytearray()
        i = 0
        while i < len(tpl):
            b = tpl[i]
            if b == SL_NAME:
                out += name
            elif b == SL_KEY:
                out += key
            elif b == SL_VALUE:
                out += value or b""
            elif b == SL_OTHER:
                i += 1
                out += self.find_value(oi, chr(tpl[i])) or b""
            else:
                out.append(b)
            i += 1
        return bytes(out)

    def _not_applicable(self, t: TypeEntry, name: bytes, key: bytes) -> bytes:
        if t.not_applicable == NONE:
            return name + GENERIC_NA
        return self._expand(self._str(t.not_applicable), name, key, None, 0)

    def resolve(self, t: TypeEntry, key: bytes) -> tuple[bool, bytes]:
        """Lookup rules 2-6 for a known type. Returns (True, bytes to print after the prefix):
        the template rest or the not-applicable continuation; or (False, UNKNOWN) when the key
        is unknown (printed after FALLBACK_SEP if a prefix is already out)."""
        kind, out = self.lookup(t, key)
        return kind != "unknown", out

    def lookup(self, t: TypeEntry, key: bytes) -> tuple[str, bytes]:
        """Like resolve(), with the outcome: "fact", "na" (not applicable) or "unknown"."""
        if t.flags & F_REVERSE:
            oi = None
            for i in range(self.nr):
                roi, rc, v = self._rec(i)
                if rc == t.reverse_of and self._str(v) == key:
                    oi = roi
                    break
        else:
            oi = self.find_object(key)
        if oi is None:
            return "unknown", UNKNOWN
        _, name, kind = self._obj(oi)
        if not kind & t.kinds:
            return "na", self._not_applicable(t, name, key)
        value = None
        if t.flags & F_NEEDS_VALUE:
            value = self.find_value(oi, t.code)
            if value is None:
                return "na", self._not_applicable(t, name, key)
        tpl = self._str(t.template)
        for m in re.finditer(rb"\x04(.)", tpl, flags=re.S):
            if self.find_value(oi, chr(m.group(1)[0])) is None:
                return "na", self._not_applicable(t, name, key)
        rest = tpl[len(self.prefix(t)) :]
        return "fact", self._expand(rest, name, key, value, oi)

    def outcome(self, fo: str | None) -> str:
        """Outcome of a function output `type+key` (without <fn>): "fact", "na", "unknown";
        "text" for None."""
        if fo is None:
            return "text"
        t = self.find_type(fo[:1]) if fo else None
        if t is None:
            return "unknown"
        return self.lookup(t, fo[1:].encode())[0]

    def check_rendered(self, fs: FactSet) -> None:
        """Every applicable (type, object) and every fallback renders <= RENDER_MAX bytes."""
        if not self.ok:
            raise TableError(f"fact table invalid: {self.status}")
        errors = []
        for code, qt in fs.types.items():
            t = self.find_type(code)
            for k, o in fs.objects.items():
                if o.kind not in qt.kinds:
                    continue
                key = (fs.value(k, qt.reverse_of) if qt.reverse_of else k) or ""
                if not key:
                    continue
                ok, rest = self.resolve(t, key.encode())
                text = (self.prefix(t) + rest) if ok else (self.prefix(t) + FALLBACK_SEP + rest)
                if len(text) > RENDER_MAX:
                    errors.append(f"({code}, {k}) renders {len(text)} B: {text.decode()!r}")
        if errors:
            raise TableError("\n".join(errors[:20]))


def read(path: Path | None) -> Table:
    if path is None or not Path(path).exists():
        return Table(None)
    return Table(Path(path).read_bytes())


# ---------------------------------------------------------------- answers (console mirror)


def answer_bytes(tokens: list[int], ab: Alphabet, table: Table | None) -> bytes:
    """Bytes the console prints for one generated answer (contracts/function-output.md)."""
    if not tokens or tokens[0] != FN or not ab.fn:
        text = "".join(ab.symbols[t - ab.n_special] for t in tokens if t >= ab.n_special)
        return text.encode()
    code = None
    if len(tokens) > 1 and tokens[1] >= ab.n_special:
        ch = ab.symbols[tokens[1] - ab.n_special]
        if ch.isascii() and ch.isalpha():
            code = ch
    key = bytearray()
    for tok in tokens[2:]:
        if tok in (EOS, FN):
            break
        if tok >= ab.n_special:
            key += ab.symbols[tok - ab.n_special].encode()
    out = bytearray()
    ok_table = table is not None and table.ok
    t = table.find_type(code) if ok_table else None
    prefix = table.prefix(t) if t else b""
    out += prefix
    if not ok_table:
        out += MISSING
    elif t is None:
        out += UNKNOWN
    else:
        ok, rest = table.resolve(t, bytes(key))
        out += rest if ok else ((FALLBACK_SEP if prefix else b"") + rest)
    return bytes(out)


def function_output(tokens: list[int], ab: Alphabet) -> str | None:
    """`type + key` of a function output (without <fn>), or None for a text answer."""
    if not tokens or tokens[0] != FN:
        return None
    return ab.decode([t for t in tokens[1:] if t not in (EOS, FN)])
