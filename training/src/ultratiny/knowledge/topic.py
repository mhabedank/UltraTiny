"""Topic loading and validation (specs/008-wissens-compiler/contracts/topic-format.md,
data-model.md "Topic" … "Competency question").

A topic is data only: `topic.toml`, `schema.toml`, object files and fact files. Nothing here names a
topic, a class or a relation. Every error names the file, the line (or the TOML key) and the rule;
validation stops after the first class of errors (FR-004).
"""

from __future__ import annotations

import glob
import hashlib
import re
import tomllib
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from pathlib import Path

from ..alphabet import Alphabet
from ..datagen import allowed_source_prefixes

KEY_MAX = 12
NAME_MAX = 40
VALUE_MAX = 60
RENDER_MAX = 100
TOPIC_ID_MAX = 15
IDENT_MAX = 20
MAX_CLASSES = 8
MAX_RELATIONS = 254
MAX_VIEWS = 254
DEFAULT_BUDGET = 58982  # fact area 64 KB - 10 % (specs/006 fact-table-format.md)

TYPES = ("text", "int", "dec", "enum", "ref")
CARDS = ("one", "many")
REVERSES = ("none", "one", "many")
KINDS = ("forward", "reverse", "self", "profile")

IDENT = re.compile(r"[a-z][a-z0-9_]*")
VIEW_NAME = re.compile(r"[a-z][a-z0-9_]+<?")
SLOT = re.compile(r"\{(name|key|v|n|r:[a-z][a-z0-9_]*)\}")
INT_RE = re.compile(r"-?\d+")
SLOTS_BY_KIND = {
    "forward": {"name", "key", "v", "r"},
    "reverse": {"name", "key", "v"},
    "self": {"name", "key"},
    "profile": {"name", "key", "r"},
}


class TopicError(ValueError):
    """Validation failed; `errors` lists every error of the first failing class."""

    def __init__(self, errors: list[str]):
        self.errors = errors
        super().__init__("\n".join(errors))


@dataclass
class Texts:
    unknown: str
    not_applicable: str
    fallback_sep: str
    list_sep: str
    list_last: str


@dataclass
class ClassDef:
    name: str
    order_by: str = ""


@dataclass
class Relation:
    name: str
    subject: str
    type: str
    card: str = "one"
    reverse: str = "none"
    values: list[str] = field(default_factory=list)
    decimals: int = 0
    target: str = ""


@dataclass
class Question:
    view: str
    question: str
    key: str
    expect: str


@dataclass
class View:
    name: str
    kind: str
    template: str
    relation: str = ""
    classes: list[str] = field(default_factory=list)
    not_applicable: str = ""
    more: str = ""
    letter: str = ""
    questions: list[Question] = field(default_factory=list)


@dataclass
class Rule:
    id: str
    kind: str
    add_relation: str
    if_relation: str = ""
    equals: str | None = None
    between: tuple[str, str] | None = None
    except_: list[str] = field(default_factory=list)
    add_value: str = ""
    first: str = ""
    then: str = ""
    from_: str = ""
    map: dict[str, str] = field(default_factory=dict)


@dataclass
class Obj:
    key: str
    name: str
    cls: str
    source: str
    origin: str


@dataclass
class Fact:
    subject: str
    relation: str
    value: str
    source: str
    origin: str


@dataclass
class Topic:
    root: Path
    id: str
    schema_version: int
    title: str
    budget_bytes: int
    compat_oracle: Path | None
    compat_changes: Path | None
    texts: Texts
    classes: dict[str, ClassDef]
    relations: dict[str, Relation]
    views: dict[str, View]
    rules: list[Rule]
    objects: list[Obj]
    facts: list[Fact]
    source_files: list[Path]

    @property
    def data_sha(self) -> bytes:
        """SHA-256 over every source file (relative name + bytes) in read order."""
        h = hashlib.sha256()
        for p in self.source_files:
            h.update(p.relative_to(self.root).as_posix().encode() + b"\0")
            h.update(p.read_bytes())
        return h.digest()

    def class_of(self) -> dict[str, str]:
        return {o.key: o.cls for o in self.objects}


# ---------------------------------------------------------------- values


def parse_number(s: str) -> Decimal | None:
    try:
        return Decimal(s.replace(",", "."))
    except InvalidOperation:
        return None


def check_value(rel: Relation, value: str, obj_class: dict[str, str]) -> str | None:
    """Error text if `value` does not fit the relation's type (data-model.md Relation.type)."""
    if not value:
        return "empty value"
    if len(value.encode()) > VALUE_MAX:
        return f"value longer than {VALUE_MAX} B"
    if "\t" in value or "\n" in value or any(0 < ord(c) < 6 for c in value):
        return "value contains a tab, newline or control byte"
    if rel.type == "int" and not INT_RE.fullmatch(value):
        return f"{value!r} is not an int"
    if rel.type == "dec":
        pat = rf"-?\d+,\d{{{rel.decimals}}}" if rel.decimals else r"-?\d+"
        if not re.fullmatch(pat, value):
            return f"{value!r} is not a decimal with {rel.decimals} decimals (German comma)"
    if rel.type == "enum" and value not in rel.values:
        return f"{value!r} is not one of the enum values"
    if rel.type == "ref":
        if value not in obj_class:
            return f"{value!r} is not an object key"
        if obj_class[value] != rel.target:
            return f"{value!r} is a {obj_class[value]}, expected {rel.target}"
    return None


def source_error(source: str, allowed: set[str]) -> str | None:
    if not source:
        return "missing source"
    prefix = source.split(":", 1)[0]
    if prefix == "llm":
        return f"source {source!r}: llm sources are not allowed for facts (research R14)"
    if prefix not in allowed:
        return f"source {source!r}: prefix {prefix!r} not allowed (DATA_LICENSES.md)"
    return None


# ---------------------------------------------------------------- TSV


def read_tsv(path: Path, columns: tuple[str, ...]) -> list[tuple[int, dict[str, str]]]:
    """Rows with their 1-based line numbers; `#` lines are comments; header required."""
    rows: list[tuple[int, dict[str, str]]] = []
    header: list[str] | None = None
    with open(path, encoding="utf-8", newline="") as f:
        for lineno, line in enumerate(f, 1):
            line = line.rstrip("\n").rstrip("\r")
            if not line or line.startswith("#"):
                continue
            cells = line.split("\t")
            if header is None:
                header = cells
                missing = [c for c in columns if c not in header]
                if missing:
                    raise TopicError([f"{path}:{lineno}: header lacks columns {missing}"])
                continue
            if len(cells) != len(header):
                raise TopicError([f"{path}:{lineno}: {len(cells)} cells, header has {len(header)}"])
            rows.append((lineno, dict(zip(header, cells, strict=True))))
    return rows


# ---------------------------------------------------------------- loading


def _expand(root: Path, patterns: list[str]) -> list[Path]:
    out: list[Path] = []
    for pat in patterns:
        hits = sorted(glob.glob(str(root / pat)))
        if not hits and not glob.has_magic(pat):
            raise TopicError([f"{root / 'topic.toml'}: file {pat!r} not found"])
        for h in hits:
            p = Path(h)
            if p not in out:
                out.append(p)
    return out


def _ident(name: str, what: str, where: str, errors: list[str], pattern=IDENT) -> None:
    if not pattern.fullmatch(name) or len(name.encode()) > IDENT_MAX:
        errors.append(
            f"{where}: {what} name {name!r} must match {pattern.pattern}, ≤ {IDENT_MAX} B"
        )


def _load_schema(root: Path, raw: dict, errors: list[str]):
    sf = root / "schema.toml"
    t = raw.get("texts", {})
    texts = Texts(
        unknown=t.get("unknown", ""),
        not_applicable=t.get("not_applicable", ""),
        fallback_sep=t.get("fallback_sep", ""),
        list_sep=t.get("list_sep", ", "),
        list_last=t.get("list_last", " und "),
    )
    for k in ("unknown", "not_applicable", "fallback_sep"):
        if not getattr(texts, k):
            errors.append(f"{sf}:[texts]: '{k}' is required")
    classes: dict[str, ClassDef] = {}
    for name, c in raw.get("classes", {}).items():
        _ident(name, "class", f"{sf}:[classes.{name}]", errors)
        classes[name] = ClassDef(name, (c or {}).get("order_by", ""))
    if not 1 <= len(classes) <= MAX_CLASSES:
        errors.append(f"{sf}:[classes]: 1–{MAX_CLASSES} classes required, got {len(classes)}")
    relations: dict[str, Relation] = {}
    for name, r in raw.get("relations", {}).items():
        where = f"{sf}:[relations.{name}]"
        _ident(name, "relation", where, errors)
        rel = Relation(
            name=name,
            subject=r.get("subject", ""),
            type=r.get("type", ""),
            card=r.get("card", "one"),
            reverse=r.get("reverse", "none"),
            values=list(r.get("values", [])),
            decimals=int(r.get("decimals", 0)),
            target=r.get("target", ""),
        )
        if rel.subject not in classes:
            errors.append(f"{where}: subject class {rel.subject!r} unknown")
        if rel.type not in TYPES:
            errors.append(f"{where}: type {rel.type!r} not in {TYPES}")
        if rel.card not in CARDS:
            errors.append(f"{where}: card {rel.card!r} not in {CARDS}")
        if rel.reverse not in REVERSES:
            errors.append(f"{where}: reverse {rel.reverse!r} not in {REVERSES}")
        if rel.type == "enum" and not rel.values:
            errors.append(f"{where}: enum needs 'values'")
        if rel.type == "dec" and not 0 <= rel.decimals <= 6:
            errors.append(f"{where}: decimals must be 0–6")
        if rel.type == "ref" and rel.target not in classes:
            errors.append(f"{where}: ref target class {rel.target!r} unknown")
        relations[name] = rel
    if len(relations) > MAX_RELATIONS:
        errors.append(f"{sf}:[relations]: at most {MAX_RELATIONS} relations")
    for c in classes.values():
        if c.order_by:
            r = relations.get(c.order_by)
            if r is None or r.type != "int" or r.subject != c.name or r.card != "one":
                errors.append(
                    f"{sf}:[classes.{c.name}]: order_by {c.order_by!r} must be a "
                    f"card=one int relation of the class"
                )
    rules = _load_rules(sf, raw.get("rules", []), relations, errors)
    views = _load_views(sf, raw.get("views", {}), classes, relations, errors)
    used = {v.relation for v in views.values() if v.relation}
    for v in views.values():
        used |= {m[2:] for m in SLOT.findall(v.template) if m.startswith("r:")}
    for name in relations:
        if name not in used:
            errors.append(f"{sf}:[relations.{name}]: no view uses this relation (FR-002)")
    return texts, classes, relations, views, rules


def _load_rules(
    sf: Path, raw: list, relations: dict[str, Relation], errors: list[str]
) -> list[Rule]:
    rules: list[Rule] = []
    ids: set[str] = set()
    for i, r in enumerate(raw):
        rid = r.get("id", f"#{i + 1}")
        where = f"{sf}:[rules.{rid}]"
        if rid in ids:
            errors.append(f"{where}: duplicate rule id")
        ids.add(rid)
        between = r.get("between")
        rule = Rule(
            id=rid,
            kind=r.get("kind", ""),
            add_relation=r.get("add_relation", ""),
            if_relation=r.get("if_relation", ""),
            equals=str(r["equals"]) if "equals" in r else None,
            between=(str(between[0]), str(between[1])) if between else None,
            except_=[str(x) for x in r.get("except", [])],
            add_value=str(r.get("add_value", "")),
            first=r.get("first", ""),
            then=r.get("then", ""),
            from_=r.get("from", ""),
            map={str(k): str(v) for k, v in r.get("map", {}).items()},
        )
        add = relations.get(rule.add_relation)
        if add is None:
            errors.append(f"{where}: add_relation {rule.add_relation!r} unknown")
        if rule.kind == "class":
            src = relations.get(rule.if_relation)
            if src is None:
                errors.append(f"{where}: if_relation {rule.if_relation!r} unknown")
            elif add is not None and src.subject != add.subject:
                errors.append(f"{where}: if_relation and add_relation need the same subject class")
            if (rule.equals is None) == (rule.between is None):
                errors.append(f"{where}: class rule needs exactly one of 'equals' and 'between'")
            if rule.between and src is not None and src.type not in ("int", "dec"):
                errors.append(f"{where}: 'between' needs an int or dec relation")
            if not rule.add_value:
                errors.append(f"{where}: class rule needs 'add_value'")
        elif rule.kind == "chain":
            first, then = relations.get(rule.first), relations.get(rule.then)
            if first is None or first.type != "ref":
                errors.append(f"{where}: 'first' must be a ref relation")
            if then is None:
                errors.append(f"{where}: 'then' relation {rule.then!r} unknown")
            if first is not None and then is not None and first.target != then.subject:
                errors.append(f"{where}: 'then' must start at the target class of 'first'")
            if first is not None and add is not None and first.subject != add.subject:
                errors.append(f"{where}: add_relation must have the subject class of 'first'")
        elif rule.kind == "table":
            src = relations.get(rule.from_)
            if src is None:
                errors.append(f"{where}: 'from' relation {rule.from_!r} unknown")
            elif add is not None and src.subject != add.subject:
                errors.append(f"{where}: 'from' and add_relation need the same subject class")
            if not rule.map:
                errors.append(f"{where}: table rule needs 'map'")
        else:
            errors.append(f"{where}: kind {rule.kind!r} not in (class, chain, table)")
        rules.append(rule)
    return rules


def _check_template(where: str, what: str, text: str, allowed: set[str], relations, errors) -> None:
    for m in SLOT.findall(text):
        base = "r" if m.startswith("r:") else m
        if base not in allowed:
            errors.append(f"{where}: slot {{{m}}} not allowed in {what}")
        if base == "r":
            r = relations.get(m[2:])
            if r is None or r.card != "one":
                errors.append(f"{where}: {{{m}}} needs a card=one relation")
    rest = SLOT.sub("", text)
    if "{" in rest or "}" in rest:
        errors.append(f"{where}: unknown slot or stray brace in {what} {text!r}")
    if any(0 < ord(c) < 6 for c in text):
        errors.append(f"{where}: control bytes 0x01–0x05 are reserved for slots")


def _load_views(sf, raw: dict, classes, relations, errors) -> dict[str, View]:
    views: dict[str, View] = {}
    letters: dict[str, str] = {}
    for name, v in raw.items():
        where = f"{sf}:[views.{name!r}]" if "<" in name else f"{sf}:[views.{name}]"
        _ident(name, "view", where, errors, VIEW_NAME)
        view = View(
            name=name,
            kind=v.get("kind", ""),
            template=v.get("template", ""),
            relation=v.get("relation", ""),
            classes=list(v.get("classes", [])),
            not_applicable=v.get("not_applicable", ""),
            more=v.get("more", ""),
            letter=v.get("letter", ""),
        )
        for q in v.get("questions", []):
            view.questions.append(
                Question(
                    name, q.get("question", ""), str(q.get("key", "")), str(q.get("expect", ""))
                )
            )
        if view.kind not in KINDS:
            errors.append(f"{where}: kind {view.kind!r} not in {KINDS}")
            views[name] = view
            continue
        rel = relations.get(view.relation)
        if view.kind in ("forward", "reverse"):
            if rel is None:
                errors.append(f"{where}: relation {view.relation!r} unknown")
            else:
                view.classes = [rel.subject]
                if view.kind == "reverse" and rel.reverse == "none":
                    errors.append(f"{where}: relation {rel.name!r} has reverse = none")
        else:
            if view.relation:
                errors.append(f"{where}: {view.kind} views take no relation")
            if not view.classes or any(c not in classes for c in view.classes):
                errors.append(f"{where}: classes {view.classes} must name known classes")
        allowed = SLOTS_BY_KIND[view.kind]
        if not view.template or SLOT.match(view.template):
            errors.append(f"{where}: template must start with fixed text (the prefix)")
        _check_template(where, "template", view.template, allowed, relations, errors)
        _check_template(
            where, "not_applicable", view.not_applicable, {"name", "key"}, relations, errors
        )
        if view.more:
            _check_template(where, "more", view.more, {"n"}, relations, errors)
        multi = rel is not None and (
            (view.kind == "forward" and rel.card == "many")
            or (view.kind == "reverse" and rel.reverse == "many")
        )
        if multi and not view.more:
            errors.append(f"{where}: 'more' is required for a view that can return a list")
        if view.letter:
            if len(view.letter) != 1 or not (view.letter.isascii() and view.letter.isalpha()):
                errors.append(f"{where}: letter {view.letter!r} must be one ASCII letter")
            elif view.letter in letters:
                errors.append(
                    f"{where}: letter {view.letter!r} already used by {letters[view.letter]}"
                )
            letters[view.letter] = name
        if not view.questions:
            errors.append(f"{where}: at least one competency question is required (FR-002)")
        views[name] = view
    if not 1 <= len(views) <= MAX_VIEWS:
        errors.append(f"{sf}:[views]: 1–{MAX_VIEWS} views required")
    return views


def load_topic(
    root: Path | str, alphabet: Alphabet | None = None, allowed: set[str] | None = None
) -> Topic:
    """Load and validate a topic directory (contracts/topic-format.md). Raises TopicError."""
    root = Path(root).resolve()
    ab = alphabet or Alphabet(fn=True)
    allowed = allowed if allowed is not None else allowed_source_prefixes()
    tf, sf = root / "topic.toml", root / "schema.toml"
    try:
        traw = tomllib.loads(tf.read_text(encoding="utf-8"))
        sraw = tomllib.loads(sf.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError) as e:
        raise TopicError([f"{root}: {e}"]) from e

    # class 1: configuration and schema
    errors: list[str] = []
    tid = str(traw.get("id", ""))
    if not IDENT.fullmatch(tid) or len(tid.encode()) > TOPIC_ID_MAX:
        errors.append(f"{tf}: id {tid!r} must match {IDENT.pattern}, ≤ {TOPIC_ID_MAX} B")
    elif tid != root.name:
        errors.append(f"{tf}: id {tid!r} must equal the directory name {root.name!r}")
    sv = traw.get("schema_version")
    if not isinstance(sv, int) or not 1 <= sv <= 65535:
        errors.append(f"{tf}: schema_version must be an integer 1–65535")
    compat = traw.get("compat", {})
    texts, classes, relations, views, rules = _load_schema(root, sraw, errors)
    if errors:
        raise TopicError(errors)
    object_files = _expand(root, list(traw.get("object_files", ["objects.tsv"])))
    fact_files = _expand(root, list(traw.get("fact_files", ["facts/*.tsv"])))

    # class 2: objects
    objects: list[Obj] = []
    keys: dict[str, str] = {}
    names: dict[tuple[str, str], str] = {}
    for path in object_files:
        for lineno, r in read_tsv(path, ("key", "name", "class", "source")):
            where = f"{path.relative_to(root)}:{lineno}"
            o = Obj(r["key"], r["name"], r["class"], r["source"], where)
            if o.cls not in classes:
                errors.append(f"{where}: class {o.cls!r} unknown")
            if not o.key or len(o.key.encode()) > KEY_MAX or ab.invalid_chars(o.key):
                errors.append(
                    f"{where}: key {o.key!r}: empty, > {KEY_MAX} B or outside the alphabet"
                )
            if not o.name or len(o.name.encode()) > NAME_MAX or ab.invalid_chars(o.name):
                errors.append(
                    f"{where}: name {o.name!r}: empty, > {NAME_MAX} B or outside the alphabet"
                )
            if o.key in keys:
                errors.append(f"{where}: key {o.key!r} already defined at {keys[o.key]}")
            if (o.cls, o.name) in names:
                errors.append(
                    f"{where}: name {o.name!r} already used in class {o.cls} at "
                    f"{names[(o.cls, o.name)]}"
                )
            if e := source_error(o.source, allowed):
                errors.append(f"{where}: {e}")
            keys.setdefault(o.key, where)
            names.setdefault((o.cls, o.name), where)
            objects.append(o)
    if errors:
        raise TopicError(errors)
    obj_class = {o.key: o.cls for o in objects}

    # class 3: facts
    facts: list[Fact] = []
    seen: dict[tuple[str, str, str], str] = {}
    single: dict[tuple[str, str], tuple[str, str]] = {}
    for path in fact_files:
        for lineno, r in read_tsv(path, ("subject", "relation", "value", "source")):
            where = f"{path.relative_to(root)}:{lineno}"
            f = Fact(r["subject"], r["relation"], r["value"], r["source"], where)
            rel = relations.get(f.relation)
            if rel is None:
                errors.append(f"{where}: relation {f.relation!r} unknown")
                continue
            if f.subject not in obj_class:
                errors.append(f"{where}: subject {f.subject!r} is not an object key")
                continue
            if obj_class[f.subject] != rel.subject:
                errors.append(
                    f"{where}: {f.subject} is a {obj_class[f.subject]}, relation "
                    f"{rel.name!r} needs a {rel.subject}"
                )
            if e := check_value(rel, f.value, obj_class):
                errors.append(f"{where}: {e}")
            if e := source_error(f.source, allowed):
                errors.append(f"{where}: {e}")
            k3 = (f.subject, f.relation, f.value)
            if k3 in seen:
                errors.append(f"{where}: duplicate fact, first at {seen[k3]}")
            seen.setdefault(k3, where)
            if rel.card == "one":
                prev = single.get((f.subject, f.relation))
                if prev and prev[0] != f.value:
                    errors.append(
                        f"{where}: relation {rel.name!r} is card=one, but {f.subject} "
                        f"already has {prev[0]} ({prev[1]})"
                    )
                single.setdefault((f.subject, f.relation), (f.value, where))
            facts.append(f)
    if errors:
        raise TopicError(errors)

    source_files = [tf, sf, *object_files, *fact_files]
    return Topic(
        root=root,
        id=tid,
        schema_version=int(sv),
        title=str(traw.get("title", "")),
        budget_bytes=int(traw.get("budget_bytes", DEFAULT_BUDGET)),
        compat_oracle=(root / compat["oracle"]) if "oracle" in compat else None,
        compat_changes=(root / compat["changes"]) if "changes" in compat else None,
        texts=texts,
        classes=classes,
        relations=relations,
        views=views,
        rules=rules,
        objects=objects,
        facts=facts,
        source_files=source_files,
    )
