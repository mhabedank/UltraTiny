"""Benchmark suites: loading, SHA-256 pin checks and validation (research R3, R4).

A suite is data only (spec FR-001): `suite.toml`, `facts.tsv`, question sets, the S1 text and the
S2 probes. Every file the suite reads must be pinned in `[files]`; a mismatch stops every command
(FR-004, contracts/suite-format.md).
"""

from __future__ import annotations

import csv
import hashlib
import re
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[4]
SUITES_DIR = REPO_ROOT / "bench" / "suites"

KINDS = ("fact", "multi", "explain", "refuse", "unknown")
QUESTION_ROLES = ("unseen", "unknown", "offtopic", "kurzarbeit", "s3")
TEXT_ROLES = ("s1", "s2")
KPI_IDS = (
    "F1",
    "F2",
    "F3",
    "F4",
    "F5",
    "F6",
    "F7",
    "T1",
    "T2",
    "T3",
    "R1",
    "R2",
    "R3",
    "R4",
    "R5",
    "S1",
    "S2",
    "S3",
)
MAX_QUESTION_DEFAULT = (
    70  # console question limit at context 104 (data-model.md Test item.question)
)


class SuiteError(Exception):
    """Invalid or changed suite data (exit code 2)."""


def sha256_file(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def norm_q(s: str) -> str:
    """Question normalisation used to keep test questions out of training (as hybrid.norm_q)."""
    return " ".join(re.sub(r"[?.!,]", " ", s.lower()).split())


@dataclass
class ValueClass:
    name: str
    kind: str  # vocab | number
    case_sensitive: bool = True
    decimals: int = 0
    units: list[str] = field(default_factory=list)


@dataclass
class Property:
    name: str
    value_class: str
    canonical: str
    reverse: bool = False


@dataclass
class Fact:
    object: str
    object_name: str
    property: str
    value: str


@dataclass
class Item:
    set: str
    id: str
    kind: str
    question: str
    expected: list[tuple[str, str]]  # (property, object) for fact/multi
    keywords: list[str]  # explain
    grade: str = "-"

    @property
    def type(self) -> str:
        return self.expected[0][0] if self.expected else self.kind


@dataclass
class Probe:
    id: str
    distance: int
    target_start: int
    target_len: int
    text: str
    control: str


@dataclass
class Suite:
    name: str
    version: int
    root: Path
    pins: dict[str, str]
    value_classes: dict[str, ValueClass]
    properties: dict[str, Property]
    facts: dict[tuple[str, str], Fact]
    sets: dict[str, list[Item]]
    s1: dict[str, str]  # section -> text
    s2: list[Probe]
    refusal_forms: list[str]
    explain_max: int
    thresholds: dict[str, object]
    board_sample: dict
    s2_cfg: dict
    not_applicable: list[str]
    set_files: dict[str, str]

    def value(self, obj: str, prop: str) -> str | None:
        f = self.facts.get((obj, prop))
        return f.value if f else None

    def object_name(self, obj: str) -> str:
        for (o, _), f in self.facts.items():
            if o == obj:
                return f.object_name
        return obj

    def class_of(self, prop: str) -> ValueClass:
        return self.value_classes[self.properties[prop].value_class]

    def versions(self) -> dict[str, str]:
        """Test-set versions: role -> 'v<suite version>:<sha256[:12]>' (FR-004)."""
        out = {}
        for role, rel in sorted(self.set_files.items()):
            out[role] = f"v{self.version}:{self.pins.get(rel, '')[:12]}"
        if "facts.tsv" in self.pins:
            out["facts"] = f"v{self.version}:{self.pins['facts.tsv'][:12]}"
        return out

    def info(self) -> dict:
        return {
            "name": self.name,
            "version": self.version,
            "files": dict(sorted(self.pins.items())),
            "sets": self.versions(),
            "thresholds": dict(sorted(self.thresholds.items())),
            "s2_distances": list(self.s2_cfg.get("distances", [])),
        }


def read_tsv(path: Path) -> list[dict[str, str]]:
    with open(path, encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f, delimiter="\t", quoting=csv.QUOTE_NONE))
    return [{k: (v or "") for k, v in r.items()} for r in rows]


def check_pins(root: Path, pins: dict[str, str], allow_unpinned: bool = False) -> list[str]:
    """Return problems; every pinned file must exist and match (data-model.md Suite.files)."""
    problems = []
    for rel, pin in sorted(pins.items()):
        path = (root / rel).resolve()
        if not path.exists():
            problems.append(f"{rel}: pinned file missing")
            continue
        actual = sha256_file(path)
        if not pin:
            if not allow_unpinned:
                problems.append(f"{rel}: not pinned (sha256 {actual})")
        elif actual != pin:
            problems.append(f"{rel}: changed, pinned {pin}, found {actual}")
    return problems


def _parse_expected(raw: str, kind: str, where: str) -> tuple[list[tuple[str, str]], list[str]]:
    raw = raw.strip()
    if kind in ("fact", "multi"):
        out = []
        for e in (x.strip() for x in raw.split("|")):
            if not e:
                continue
            prop, sep, obj = (s.strip() for s in e.partition(":"))
            if not sep or not prop or not obj:
                raise SuiteError(f"{where}: expected entry {e!r} must be '<property>: <object>'")
            out.append((prop, obj))
        if not out:
            raise SuiteError(f"{where}: fact item without expected answer")
        return out, []
    if kind == "explain":
        return [], [k.strip() for k in raw.split(";") if k.strip()]
    return [], []


def load_items(path: Path, role: str, max_question: int) -> list[Item]:
    items, seen = [], set()
    for r in read_tsv(path):
        where = f"{path.name} {r.get('id', '?')}"
        kind = r.get("kind", "").strip()
        if kind not in KINDS:
            raise SuiteError(f"{where}: unknown kind {kind!r}")
        if r["id"] in seen:
            raise SuiteError(f"{where}: duplicate id")
        seen.add(r["id"])
        q = r["question"].strip()
        if not q or len(q) > max_question:
            raise SuiteError(f"{where}: question empty or longer than {max_question} characters")
        exp, kws = _parse_expected(r.get("expected", ""), kind, where)
        items.append(Item(role, r["id"], kind, q, exp, kws, r.get("grade", "-") or "-"))
    return items


def parse_s1(text: str) -> dict[str, str]:
    """`# topic` / `# general` section markers; other `#` lines are comments (suite-format.md)."""
    sections: dict[str, list[str]] = {}
    cur = "all"
    for line in text.splitlines():
        s = line.strip()
        if s.startswith("#"):
            tag = s[1:].strip().lower()
            if tag in ("topic", "general"):
                cur = tag
            continue
        sections.setdefault(cur, []).append(s)
    return {k: " ".join(" ".join(v).split()) for k, v in sections.items()}


def load_probes(path: Path) -> list[Probe]:
    out = []
    for r in read_tsv(path):
        p = Probe(
            r["id"],
            int(r["distance"]),
            int(r["target_start"]),
            int(r["target_len"]),
            r["text"],
            r["control"],
        )
        if len(p.text) != len(p.control):
            raise SuiteError(f"{path.name} {p.id}: text and control differ in length")
        out.append(p)
    return out


def load_suite(path: Path | str, allow_unpinned: bool = False) -> Suite:
    root = Path(path).resolve()
    cfg_path = root / "suite.toml"
    if not cfg_path.exists():
        raise SuiteError(f"{cfg_path}: no suite.toml")
    cfg = tomllib.loads(cfg_path.read_text(encoding="utf-8"))
    pins = {k: str(v) for k, v in cfg.get("files", {}).items()}
    problems = check_pins(root, pins, allow_unpinned)
    if problems:
        raise SuiteError("pin check failed:\n  " + "\n  ".join(problems))

    def pinned(rel: str) -> Path:
        if rel not in pins:
            raise SuiteError(f"{rel}: used by the suite but not listed in [files]")
        return (root / rel).resolve()

    vcs = {}
    for name, v in cfg.get("value_classes", {}).items():
        if v.get("kind") not in ("vocab", "number"):
            raise SuiteError(f"value class {name}: kind must be vocab or number")
        vcs[name] = ValueClass(
            name,
            v["kind"],
            bool(v.get("case_sensitive", True)),
            int(v.get("decimals", 0)),
            list(v.get("units", [])),
        )
    props = {}
    for name, p in cfg.get("properties", {}).items():
        if p.get("value_class") not in vcs:
            raise SuiteError(f"property {name}: unknown value class {p.get('value_class')!r}")
        props[name] = Property(
            name, p["value_class"], p.get("canonical", ""), bool(p.get("reverse"))
        )

    facts: dict[tuple[str, str], Fact] = {}
    if "facts.tsv" in pins:
        for r in read_tsv(pinned("facts.tsv")):
            f = Fact(r["object"], r["object_name"], r["property"], r["value"])
            if f.property not in props:
                raise SuiteError(f"facts.tsv: unknown property {f.property!r}")
            if (f.object, f.property) in facts:
                raise SuiteError(f"facts.tsv: duplicate fact {f.object} / {f.property}")
            facts[(f.object, f.property)] = f

    max_q = int(cfg.get("max_question", MAX_QUESTION_DEFAULT))
    set_files = {k: v for k, v in cfg.get("sets", {}).items()}
    sets: dict[str, list[Item]] = {}
    s1: dict[str, str] = {}
    s2: list[Probe] = []
    for role, rel in set_files.items():
        p = pinned(rel)
        if role in QUESTION_ROLES:
            sets[role] = load_items(p, role, max_q)
        elif role == "s1":
            s1 = parse_s1(p.read_text(encoding="utf-8"))
        elif role == "s2":
            s2 = load_probes(p)
        else:
            raise SuiteError(f"[sets]: unknown role {role!r}")
    objects = {o for o, _ in facts}
    for items in sets.values():
        for it in items:
            for prop, obj in it.expected:
                if prop not in props:
                    raise SuiteError(f"{it.set} {it.id}: unknown property {prop!r}")
                if (obj, prop) not in facts and obj not in objects:
                    raise SuiteError(f"{it.set} {it.id}: no fact for {prop}: {obj}")
                # a known object without this property: the right answer is "not applicable"

    na = list(cfg.get("not_applicable", []))
    for k in na:
        if k not in KPI_IDS:
            raise SuiteError(f"not_applicable: unknown KPI {k!r}")
    return Suite(
        name=cfg.get("name", root.name),
        version=int(cfg.get("version", 0)),
        root=root,
        pins=pins,
        value_classes=vcs,
        properties=props,
        facts=facts,
        sets=sets,
        s1=s1,
        s2=s2,
        refusal_forms=list(cfg.get("refusal_forms", [])),
        explain_max=int(cfg.get("explain_max", 60)),
        thresholds=dict(cfg.get("thresholds", {})),
        board_sample=dict(cfg.get("board_sample", {})),
        s2_cfg=dict(cfg.get("s2", {})),
        not_applicable=na,
        set_files=set_files,
    )


def pin_suite(path: Path | str) -> dict[str, str]:
    """Rewrite the [files] hashes in suite.toml to the current file contents (re-pin)."""
    root = Path(path).resolve()
    cfg_path = root / "suite.toml"
    text = cfg_path.read_text(encoding="utf-8")
    cfg = tomllib.loads(text)
    new = {}
    for rel in cfg.get("files", {}):
        digest = sha256_file(root / rel)
        new[rel] = digest
        pat = re.compile(r'^("' + re.escape(rel) + r'"\s*=\s*)"[0-9a-f]*"', re.M)
        text, n = pat.subn(lambda m, d=digest: f'{m.group(1)}"{d}"', text)
        if n != 1:
            raise SuiteError(f"suite.toml: cannot find the [files] line for {rel}")
    cfg_path.write_text(text, encoding="utf-8")
    return new


def all_questions(suites_dir: Path = SUITES_DIR) -> set[str]:
    """Normalised questions of every suite, for excluding them from training data (FR-005).

    Reads the TSV files directly (no pin check), so a suite under construction is excluded too.
    """
    out: set[str] = set()
    if not suites_dir.exists():
        return out
    for cfg_path in sorted(suites_dir.glob("*/suite.toml")):
        cfg = tomllib.loads(cfg_path.read_text(encoding="utf-8"))
        for role, rel in cfg.get("sets", {}).items():
            p = (cfg_path.parent / rel).resolve()
            if role in QUESTION_ROLES and p.exists():
                out |= {norm_q(r.get("question", "")) for r in read_tsv(p) if r.get("question")}
    return out
