"""Verified fact set for the hybrid chemistry teacher (specs/006-hybrid-chemielehrer, research R6).

Builds Objects, question types and Fact records (data-model.md) from
- the element base data (Wikidata snapshot, CC0),
- deterministic rules (ultratiny.periodic: atomic structure, ions, valence, neutrons),
- computed binary ionic compounds (formula from ion charges, German name, molar mass),
- curated, sourced lists (compounds, acids/bases, equations, test reactions, aliases).

No value comes from a language model (FR-005). `check()` enforces the validation rules of
data-model.md "Fact record"; any failure stops the build.
"""

from __future__ import annotations

import csv
import math
import re
import tomllib
from collections import Counter
from dataclasses import dataclass, field
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

from . import periodic as pt
from .alphabet import Alphabet
from .config import Config

KINDS = {"element": 1, "compound": 2, "acidbase": 4, "reaction": 8, "test": 16}
KEY_MAX = 12
NAME_MAX = 40
VALUE_MAX = 60
VALUE_MAX_LONG_TEMPLATE = 50  # types q and t (data-model.md Fact record.value)
FORMS_MIN = 12
FAMILIES_MIN = 4
SLOT = re.compile(r"\{(name|key|v|[A-Za-z])\}")

IONIC_METALS = ["Li", "Na", "K", "Rb", "Cs", "Mg", "Ca", "Sr", "Ba", "Al"]
ANIONS = {"F": "fluorid", "Cl": "chlorid", "Br": "bromid", "I": "iodid",
          "O": "oxid", "S": "sulfid", "N": "nitrid", "P": "phosphid"}  # fmt: skip
CHARGE_WORD = {1: "einfach", 2: "zweifach", 3: "dreifach"}


class FactError(ValueError):
    pass


@dataclass
class Obj:
    """data-model.md Object."""

    key: str
    name: str
    kind: str
    source: str
    aliases: list[str] = field(default_factory=list)


@dataclass
class QType:
    """data-model.md Question type."""

    code: str
    name: str
    kinds: list[str]
    needs_value: bool
    reverse_of: str
    template: str
    not_applicable: str
    forms: list[tuple[str, str]]  # (text, family)


@dataclass
class FactSet:
    objects: dict[str, Obj]  # key -> object
    types: dict[str, QType]  # code -> type
    records: dict[tuple[str, str], tuple[str, str]]  # (key, code) -> (value, source)

    def value(self, key: str, code: str) -> str | None:
        r = self.records.get((key, code))
        return r[0] if r else None


# ---------------------------------------------------------------- formulas and numbers


_TOKEN = re.compile(r"([A-Z][a-z]?)(\d*)|(\()|(\))(\d*)")


def parse_formula(formula: str) -> Counter:
    """Atom counts of a formula like `Ca3(PO4)2` or `CO(NH2)2`."""
    stack: list[Counter] = [Counter()]
    pos = 0
    while pos < len(formula):
        m = _TOKEN.match(formula, pos)
        if not m:
            raise FactError(f"cannot parse formula {formula!r} at {formula[pos:]!r}")
        if m.group(1):
            stack[-1][m.group(1)] += int(m.group(2) or 1)
        elif m.group(3):
            stack.append(Counter())
        else:
            if len(stack) < 2:
                raise FactError(f"unbalanced ')' in {formula!r}")
            inner = stack.pop()
            for el, n in inner.items():
                stack[-1][el] += n * int(m.group(5) or 1)
        pos = m.end()
    if len(stack) != 1:
        raise FactError(f"unbalanced '(' in {formula!r}")
    return stack[0]


def parse_equation(eq: str) -> tuple[Counter, Counter]:
    """Atom counts of both sides of `2 H2 + O2 → 2 H2O`."""
    if eq.count("→") != 1:
        raise FactError(f"equation needs exactly one '→': {eq!r}")
    sides = []
    for side in eq.split("→"):
        total: Counter = Counter()
        for term in side.split(" + "):
            term = term.strip()
            m = re.fullmatch(r"(\d+) (.+)", term)
            coef, formula = (int(m.group(1)), m.group(2)) if m else (1, term)
            for el, n in parse_formula(formula).items():
                total[el] += coef * n
        sides.append(total)
    return sides[0], sides[1]


def _dec(s: str) -> Decimal:
    return Decimal(s.replace(",", "."))


def school_mass(mass: str) -> Decimal:
    """Atomic mass rounded to 0.1 u, as in school tables."""
    return _dec(mass).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)


def fmt_dec(d: Decimal) -> str:
    return f"{d:.1f}".replace(".", ",")


def molar_mass(formula: str, masses: dict[str, str]) -> str:
    total = sum((school_mass(masses[el]) * n for el, n in parse_formula(formula).items()),
                Decimal(0))  # fmt: skip
    return fmt_dec(total)


def ion_text(symbol: str, charge: int) -> str:
    sign = "+" if charge > 0 else "-"
    n = abs(charge)
    word = "positiv" if charge > 0 else "negativ"
    return f"{symbol}{n if n > 1 else ''}{sign} ({CHARGE_WORD[n]} {word} geladen)"


def bond_type(formula: str, categories: dict[str, str]) -> str:
    if "NH4" in formula:
        return "Ionenbindung"  # ammonium salts
    cats = {categories.get(el) for el in parse_formula(formula)}
    metal = "Metall" in cats
    nonmetal = bool(cats & {"Nichtmetall", "Halbmetall"})
    if metal and nonmetal:
        return "Ionenbindung"
    if nonmetal:
        return "Elektronenpaarbindung"
    return "Metallbindung"


# ---------------------------------------------------------------- loading


def _read_tsv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as f:
        return [{k: (v or "").strip() for k, v in row.items()}
                for row in csv.DictReader(f, delimiter="\t", quoting=csv.QUOTE_NONE)]  # fmt: skip


def load_types(path: Path) -> dict[str, QType]:
    raw = tomllib.loads(path.read_text(encoding="utf-8"))
    types: dict[str, QType] = {}
    for code, t in raw.get("types", {}).items():
        types[code] = QType(
            code=code, name=t["name"], kinds=list(t["kinds"]),
            needs_value=bool(t["needs_value"]), reverse_of=t.get("reverse_of", ""),
            template=t["template"], not_applicable=t.get("not_applicable", ""),
            forms=[(f["text"], f["family"]) for f in t["forms"]],
        )  # fmt: skip
    return types


def build(cfg: Config, base: Path) -> FactSet:
    """Compute the full fact set from the configured data files (FR-004, FR-005)."""
    d = cfg.data
    types = load_types(base / d.hybrid_templates)
    objects: dict[str, Obj] = {}
    records: dict[tuple[str, str], tuple[str, str]] = {}

    def add_obj(o: Obj) -> None:
        if o.key in objects:
            raise FactError(f"duplicate Object.key {o.key!r}")
        objects[o.key] = o

    def put(key: str, code: str, value, source: str) -> None:
        if value is None:
            return
        if (key, code) in records:
            raise FactError(f"duplicate fact ({key}, {code})")
        records[(key, code)] = (str(value), source)

    # Elements: base data per element name.
    el: dict[str, dict[str, str]] = {}
    for row in _read_tsv(base / d.element_facts):
        rel = row["relation"].removeprefix("element_")
        el.setdefault(row["subject"], {"source": row["source"]})[rel] = row["object"]
    masses: dict[str, str] = {}
    categories: dict[str, str] = {}
    names: dict[str, str] = {}
    for name, e in sorted(el.items(), key=lambda kv: int(kv[1]["ordnungszahl"])):
        sym, z, src = e["symbol"], int(e["ordnungszahl"]), e["source"]
        add_obj(Obj(sym, name, "element", src))
        masses[sym] = e["atommasse"]
        names[sym] = name
        if "kategorie" in e:
            categories[sym] = e["kategorie"]
        put(sym, "O", z, src)
        put(sym, "M", e["atommasse"], src)
        put(sym, "P", e.get("periode"), src)
        put(sym, "F", e.get("familie"), src)
        put(sym, "K", e.get("kategorie"), src)
        put(sym, "Z", e.get("zustand"), src)
        g, mg = pt.iupac_group(z), pt.main_group(z)
        if g is not None:
            put(sym, "G", f"{mg}. Hauptgruppe (Gruppe {g})" if mg else f"Gruppe {g} (Nebengruppe)",
                "computed")  # fmt: skip
        put(sym, "p", z, "computed")
        put(sym, "e", z, "computed")
        if z <= 103:
            put(sym, "n", pt.neutrons(z, float(_dec(e["atommasse"]))), "computed")
        put(sym, "a", pt.outer_electrons(z), "computed")
        put(sym, "h", pt.shells(z), "computed")
        arr = pt.electron_arrangement(z)
        if arr:
            put(sym, "v", ", ".join(map(str, arr)), "computed")
        q = pt.ion_charge(z)
        if q is not None:
            put(sym, "i", ion_text(sym, q), "computed")
        put(sym, "w", pt.valence(z), "computed")

    # Compounds: curated first (their names win), then computed binary ionic compounds.
    for path in d.compound_facts:
        for row in _read_tsv(base / path):
            add_obj(Obj(row["object"], row["subject"], "compound", row["source"]))
    by_symbol = {o.key: o for o in objects.values() if o.kind == "element"}
    for msym in IONIC_METALS:
        for asym, stem in ANIONS.items():
            cm = pt.ion_charge(int(records[(msym, "O")][0]))
            ca = pt.ion_charge(int(records[(asym, "O")][0]))
            lcm = math.lcm(cm, -ca)
            nm, na = lcm // cm, lcm // -ca
            if nm * cm + na * ca != 0:
                raise FactError(f"ionic formula of {msym}/{asym} not neutral")
            formula = f"{msym}{nm if nm > 1 else ''}{asym}{na if na > 1 else ''}"
            if formula not in objects:
                add_obj(Obj(formula, by_symbol[msym].name + stem, "compound", "computed"))
    for o in list(objects.values()):
        if o.kind == "compound":
            put(o.key, "m", molar_mass(o.key, masses), "computed")
            put(o.key, "b", bond_type(o.key, categories), "computed")
    if d.acidbase_facts:
        for row in _read_tsv(base / d.acidbase_facts):
            if row["formula"] not in objects:
                raise FactError(f"acid/base {row['formula']} is not a known compound")
            put(row["formula"], "c", row["value"], row["source"])
    for path, kind, code in ((d.equation_facts, "reaction", "q"), (d.test_facts, "test", "t")):
        if not path:
            continue
        for row in _read_tsv(base / path):
            add_obj(Obj(row["key"], row["name"], kind, row["source"]))
            put(row["key"], code, row["value"], row["source"])
    if d.alias_facts:
        for row in _read_tsv(base / d.alias_facts):
            if row["key"] not in objects:
                raise FactError(f"alias for unknown key {row['key']!r}")
            objects[row["key"]].aliases.append(row["alias"])
    return FactSet(objects, types, records)


# ---------------------------------------------------------------- validation


def check(fs: FactSet, alphabet: Alphabet, sources: set[str]) -> list[str]:
    """Validation rules of data-model.md (Object, Question type, Fact record). Returns errors."""
    errors: list[str] = []
    names_seen: set[tuple[str, str]] = set()
    for o in fs.objects.values():
        if not o.key or len(o.key.encode()) > KEY_MAX or alphabet.invalid_chars(o.key):
            errors.append(f"Object.key {o.key!r}: empty, > {KEY_MAX} B or outside the alphabet")
        if o.kind in ("reaction", "test") and not re.fullmatch(r"[a-z0-9]+", o.key):
            errors.append(f"Object.key {o.key!r}: slugs must be [a-z0-9]+")
        if len(o.name.encode()) > NAME_MAX or alphabet.invalid_chars(o.name):
            errors.append(f"Object.name {o.name!r}: > {NAME_MAX} B or outside the alphabet")
        if (o.kind, o.name) in names_seen:
            errors.append(f"Object.name {o.name!r} not unique for kind {o.kind}")
        names_seen.add((o.kind, o.name))
        if o.kind not in KINDS:
            errors.append(f"Object.kind {o.kind!r} unknown")
        if o.source.split(":", 1)[0] not in sources:
            errors.append(f"Object.source {o.source!r} of {o.key} not in DATA_LICENSES.md")
        for a in o.aliases:
            if alphabet.invalid_chars(a):
                errors.append(f"Object.aliases {a!r} outside the alphabet")
    for code, t in fs.types.items():
        if not re.fullmatch(r"[A-Za-z]", code):
            errors.append(f"Question type.code {code!r} must be one ASCII letter")
        if any(k not in KINDS for k in t.kinds):
            errors.append(f"type {code}: unknown kinds {t.kinds}")
        if t.reverse_of and t.reverse_of not in fs.types:
            errors.append(f"type {code}: reverse_of {t.reverse_of!r} unknown")
        first = SLOT.search(t.template)
        if first is None or first.start() == 0 or t.template[first.start() - 1] != " ":
            errors.append(f"type {code}: template needs a non-empty fixed prefix ending in ' '")
        for m in SLOT.finditer(t.template):
            s = m.group(1)
            if len(s) == 1 and s not in fs.types:
                errors.append(f"type {code}: slot {{{s}}} names no type")
            if s == "v" and not t.needs_value:
                errors.append(f"type {code}: {{v}} without needs_value")
        if any(m.group(1) not in ("name", "key") for m in SLOT.finditer(t.not_applicable)):
            errors.append(f"type {code}: not_applicable may only use {{name}}/{{key}}")
        fams = Counter(f for _, f in t.forms)
        if len(t.forms) < FORMS_MIN or len([f for f in fams if f != "multi"]) < FAMILIES_MIN:
            errors.append(f"type {code}: needs >= {FORMS_MIN} forms in >= {FAMILIES_MIN} families")
        if not any(n >= 2 for f, n in fams.items() if f != "multi"):
            errors.append(f"type {code}: needs a family with >= 2 forms to hold back")
        slot = "{key}" if code in ("s", "f", "o") else "{name}"
        for text, _fam in t.forms:
            if slot not in text:
                errors.append(f"type {code}: form without {slot}: {text!r}")
            if alphabet.invalid_chars(text.replace("{name}", "").replace("{key}", "")):
                errors.append(f"type {code}: form outside the alphabet: {text!r}")
    for (key, code), (value, src) in fs.records.items():
        o, t = fs.objects.get(key), fs.types.get(code)
        if o is None or t is None:
            errors.append(f"fact ({key}, {code}): unknown object or type")
            continue
        if not t.needs_value or o.kind not in t.kinds:
            errors.append(f"fact ({key}, {code}): type does not take a value for kind {o.kind}")
        limit = VALUE_MAX_LONG_TEMPLATE if code in ("q", "t") else VALUE_MAX
        if not value or len(value.encode()) > limit:
            errors.append(f"fact ({key}, {code}): value empty or > {limit} B: {value!r}")
        if src.split(":", 1)[0] not in sources:
            errors.append(f"fact ({key}, {code}): source {src!r} not in DATA_LICENSES.md")
    masses = {k: fs.value(k, "M") for k, o in fs.objects.items() if o.kind == "element"}
    for k, o in fs.objects.items():
        if o.kind == "element":
            z = fs.value(k, "O")
            if fs.value(k, "p") != z or fs.value(k, "e") != z:
                errors.append(f"{k}: protons/electrons differ from the atomic number")
            arr = fs.value(k, "v")
            if arr:
                shells_ = [int(x) for x in arr.split(", ")]
                if sum(shells_) != int(z):
                    errors.append(f"{k}: electron arrangement does not sum to Z")
                if fs.value(k, "h") and int(fs.value(k, "h")) != len(shells_):
                    errors.append(f"{k}: shells differ from the arrangement")
                if fs.value(k, "a") and int(fs.value(k, "a")) != shells_[-1]:
                    errors.append(f"{k}: outer electrons differ from the arrangement")
        elif o.kind == "compound":
            try:
                if fs.value(k, "m") != molar_mass(k, masses):
                    errors.append(f"{k}: molar mass inconsistent")
            except (FactError, KeyError) as exc:
                errors.append(f"{k}: formula not computable ({exc})")
        elif o.kind == "reaction":
            try:
                left, right = parse_equation(fs.value(k, "q") or "")
                if left != right:
                    errors.append(f"{k}: equation not balanced ({dict(left)} vs {dict(right)})")
                unknown = [e for e in left | right if e not in masses]
                if unknown:
                    errors.append(f"{k}: unknown elements {unknown}")
            except FactError as exc:
                errors.append(f"{k}: {exc}")
    for code, t in fs.types.items():
        if t.reverse_of:
            vals = [v for (k, c), (v, _) in fs.records.items() if c == t.reverse_of]
            dup = [v for v, n in Counter(vals).items() if n > 1]
            if dup:
                errors.append(f"type {code}: reverse values not unique: {dup[:5]}")
    return errors
