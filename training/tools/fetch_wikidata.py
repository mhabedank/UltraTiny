#!/usr/bin/env python3
"""One-off snapshot of German facts from Wikidata (CC0) into data/facts/wikidata_*.tsv.

Not part of the training pipeline: the snapshot is committed, so training stays reproducible
and offline. Re-run only to refresh the data:

    uv run python tools/fetch_wikidata.py

Every row gets `source = wikidata:<QID>` (data-model.md Fact.source). Labels with characters
outside the model alphabet, or without a German label, are dropped.
"""

from __future__ import annotations

import csv
import json
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from ultratiny.alphabet import Alphabet  # noqa: E402

ENDPOINT = "https://query.wikidata.org/sparql"
USER_AGENT = "UltraTinyDataSnapshot/0.1 (offline training data snapshot)"
OUT = Path(__file__).resolve().parents[1] / "data" / "facts"
AB = Alphabet()

# Dative form for "Hauptstadt von ..." where German uses an article.
DATIV = {
    "Schweiz": "der Schweiz", "Türkei": "der Türkei", "Slowakei": "der Slowakei",
    "Ukraine": "der Ukraine", "Mongolei": "der Mongolei", "Niederlande": "den Niederlanden",
    "Vereinigte Staaten": "den Vereinigten Staaten", "Philippinen": "den Philippinen",
    "Vereinigtes Königreich": "dem Vereinigten Königreich", "Malediven": "den Malediven",
    "Vereinigte Arabische Emirate": "den Vereinigten Arabischen Emiraten",
    "Seychellen": "den Seychellen", "Komoren": "den Komoren", "Bahamas": "den Bahamas",
    "Salomonen": "den Salomonen", "Marshallinseln": "den Marshallinseln",
    "Dominikanische Republik": "der Dominikanischen Republik",
    "Zentralafrikanische Republik": "der Zentralafrikanischen Republik",
    "Demokratische Republik Kongo": "der Demokratischen Republik Kongo",
    "Republik Kongo": "der Republik Kongo", "Elfenbeinküste": "der Elfenbeinküste",
    "Volksrepublik China": "China", "Republik Moldau": "der Republik Moldau",
    "Irak": "dem Irak", "Iran": "dem Iran", "Jemen": "dem Jemen", "Libanon": "dem Libanon",
    "Sudan": "dem Sudan", "Südsudan": "dem Südsudan", "Tschad": "dem Tschad",
    "Niger": "dem Niger", "Kosovo": "dem Kosovo", "Vatikanstadt": "der Vatikanstadt",
    "Föderierte Staaten von Mikronesien": "Mikronesien",
}  # fmt: skip

QUERIES = {
    "countries": """
SELECT ?c ?cLabel ?cap ?capLabel ?cur ?curLabel WHERE {
  ?c wdt:P31 wd:Q3624078 ; wdt:P36 ?cap .
  FILTER NOT EXISTS { ?c wdt:P576 ?end }
  OPTIONAL { ?c wdt:P38 ?cur }
  SERVICE wikibase:label { bd:serviceParam wikibase:language "de". }
}""",
    "states": """
SELECT ?s ?sLabel ?cap ?capLabel WHERE {
  ?s wdt:P31 wd:Q1221156 ; wdt:P36 ?cap .
  SERVICE wikibase:label { bd:serviceParam wikibase:language "de". }
}""",
    "cities": """
SELECT ?city ?cityLabel ?a ?b ?c WHERE {
  ?city wdt:P31 wd:Q1549591 ; wdt:P17 wd:Q183 ; wdt:P131 ?a .
  OPTIONAL { ?a wdt:P131 ?b . OPTIONAL { ?b wdt:P131 ?c . } }
  SERVICE wikibase:label { bd:serviceParam wikibase:language "de". }
}""",
    "elements": """
SELECT ?e ?eLabel ?sym ?num WHERE {
  ?e wdt:P31 wd:Q11344 ; wdt:P246 ?sym ; wdt:P1086 ?num .
  SERVICE wikibase:label { bd:serviceParam wikibase:language "de". }
}""",
}


def sparql(query: str) -> list[dict]:
    url = ENDPOINT + "?" + urllib.parse.urlencode({"query": query, "format": "json"})
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    for attempt in range(4):
        try:
            with urllib.request.urlopen(req, timeout=120) as r:
                data = json.load(r)
            return [{k: v["value"] for k, v in b.items()} for b in data["results"]["bindings"]]
        except OSError as e:
            print(f"query attempt {attempt + 1} failed: {e!r}", file=sys.stderr)
            time.sleep(5 * (attempt + 1))
    raise SystemExit("Wikidata query failed")


def qid(uri: str) -> str:
    return uri.rsplit("/", 1)[-1]


def ok(label: str) -> bool:
    return (
        bool(label)
        and not (label[0] == "Q" and label[1:].isdigit())
        and not AB.invalid_chars(label)
    )


def write(name: str, rows: list[tuple]) -> int:
    rows = sorted(set(rows), key=lambda r: (r[2], r[0]))
    path = OUT / f"wikidata_{name}.tsv"
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f, delimiter="\t", lineterminator="\n", quoting=csv.QUOTE_NONE)
        w.writerow(["id", "topic", "relation", "subject", "object", "source"])
        w.writerows(rows)
    return len(rows)


def unique(rows: list[dict], key: str, val: str) -> dict[str, dict]:
    """Keep only entities with exactly one distinct value (e.g. one capital)."""
    vals: dict[str, set] = {}
    first: dict[str, dict] = {}
    for r in rows:
        vals.setdefault(r[key], set()).add(r.get(val))
        first.setdefault(r[key], r)
    return {k: first[k] for k, v in vals.items() if len(v) == 1 and None not in v}


CHEMIE_QUERY = """
SELECT ?e ?eLabel ?sym ?num ?mass ?mp ?bp WHERE {
  ?e wdt:P31 wd:Q11344 ; wdt:P246 ?sym ; wdt:P1086 ?num .
  OPTIONAL { ?e wdt:P2067 ?mass }
  OPTIONAL { ?e p:P2101/psn:P2101/wikibase:quantityAmount ?mp }
  OPTIONAL { ?e p:P2102/psn:P2102/wikibase:quantityAmount ?bp }
  SERVICE wikibase:label { bd:serviceParam wikibase:language "de". }
}"""


def _celsius(kelvins: set[float]) -> str | None:
    """Normalized SI values (kelvin) -> rounded degree Celsius, only if sources agree (<= 5 K)."""
    if not kelvins or max(kelvins) - min(kelvins) > 5:
        return None
    k = sorted(kelvins)[len(kelvins) // 2]
    return str(round(k - 273.15))


def _mass(values: set[float], z: int) -> str | None:
    if len(values) != 1:
        return None
    m = next(iter(values))
    if z > 94 or m == int(m):
        return str(round(m))  # synthetic elements: mass number of the most stable isotope
    from decimal import ROUND_HALF_UP, Decimal

    q = Decimal(repr(m)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return str(q).replace(".", ",")


def main_chemie() -> int:
    """Element profiles for the chemistry-teacher model (specs/003-chemielehrer)."""
    sys.path.insert(0, str(Path(__file__).parent))
    import periodic as pt

    els: dict[int, dict] = {}
    for r in sparql(CHEMIE_QUERY):
        z = int(float(r["num"]))
        if z > 118:
            continue
        e = els.setdefault(z, {"q": qid(r["e"]), "name": r["eLabel"], "sym": set(), "mass": set(),
                               "mp": set(), "bp": set()})  # fmt: skip
        e["sym"].add(r["sym"])
        for k in ("mass", "mp", "bp"):
            if k in r:
                e[k].add(float(r[k]))
    rows = []
    for z, e in sorted(els.items()):
        name = e["name"]
        if not ok(name) or len(e["sym"]) != 1:
            continue
        sym = next(iter(e["sym"]))
        src = f"wikidata:{e['q']}"
        facts = {
            "element_symbol": sym,
            "element_ordnungszahl": str(z),
            "element_atommasse": _mass(e["mass"], z),
            "element_periode": str(pt.period(z)),
            "element_gruppe": pt.group_phrase(z),
            "element_familie": pt.family(z),
            "element_kategorie": pt.category(z),
            "element_zustand": pt.state(z),
            "element_schmelzpunkt": _celsius(e["mp"]) if z <= 103 else None,
            "element_siedepunkt": _celsius(e["bp"]) if z <= 103 else None,
        }
        for rel, obj in facts.items():
            if obj is not None and ok(obj):
                rows.append((f"wd/{e['q']}/{rel.split('_', 1)[1]}", "chemie", rel, name, obj, src))
    n = write("elemente_chemie", rows)
    print(json.dumps({"elements": len(els), "facts": n}, indent=2))
    return 0


def main() -> int:
    if "--chemie" in sys.argv:
        return main_chemie()
    countries = sparql(QUERIES["countries"])
    caps, curs = [], []
    for c in unique(countries, "c", "cap").values():
        name, cap = c["cLabel"], c["capLabel"]
        subj = DATIV.get(name, name)
        if ok(subj) and ok(cap):
            caps.append((f"wd/{qid(c['c'])}/cap", "geografie", "hauptstadt_von", subj, cap,
                         f"wikidata:{qid(c['c'])}"))  # fmt: skip
    for c in unique([r for r in countries if "cur" in r], "c", "cur").values():
        subj = DATIV.get(c["cLabel"], c["cLabel"])
        if ok(subj) and ok(c.get("curLabel", "")):
            curs.append((f"wd/{qid(c['c'])}/cur", "geografie", "waehrung_von", subj,
                         c["curLabel"], f"wikidata:{qid(c['c'])}"))  # fmt: skip

    state_rows = sparql(QUERIES["states"])
    states = []
    for st in unique(state_rows, "s", "cap").values():
        if ok(st["sLabel"]) and ok(st["capLabel"]) and st["sLabel"] != st["capLabel"]:
            states.append((f"wd/{qid(st['s'])}/cap", "deutschland", "landeshauptstadt_von",
                           st["sLabel"], st["capLabel"], f"wikidata:{qid(st['s'])}"))  # fmt: skip
    # All 16 states (incl. city states without a separate capital) for the city lookup.
    all_states = {
        qid(r["s"]): r["sLabel"]
        for r in sparql(
            QUERIES["states"].replace("; wdt:P36 ?cap ", "").replace("?cap ?capLabel", "")
        )
    }

    cities = []
    city_state: dict[str, set] = {}
    labels: dict[str, str] = {}
    for r in sparql(QUERIES["cities"]):
        cq = qid(r["city"])
        labels[cq] = r["cityLabel"]
        for k in ("a", "b", "c"):
            if k in r and qid(r[k]) in all_states:
                city_state.setdefault(cq, set()).add(all_states[qid(r[k])])
    for cq, sts in city_state.items():
        city, st = labels[cq], next(iter(sts))
        if len(sts) == 1 and ok(city) and ok(st) and city != st:
            cities.append((f"wd/{cq}/land", "deutschland", "stadt_bundesland", city, st,
                           f"wikidata:{cq}"))  # fmt: skip

    syms, nums = [], []
    for e in unique(sparql(QUERIES["elements"]), "e", "sym").values():
        if ok(e["eLabel"]) and ok(e["sym"]) and int(float(e["num"])) <= 118:  # known elements
            src = f"wikidata:{qid(e['e'])}"
            syms.append((f"wd/{qid(e['e'])}/sym", "chemie", "element_symbol", e["eLabel"],
                         e["sym"], src))  # fmt: skip
            nums.append((f"wd/{qid(e['e'])}/num", "chemie", "element_ordnungszahl",
                         e["eLabel"], str(int(float(e["num"]))), src))  # fmt: skip

    counts = {
        "hauptstaedte": write("hauptstaedte", caps),
        "waehrungen": write("waehrungen", curs),
        "landeshauptstaedte": write("landeshauptstaedte", states),
        "staedte": write("staedte", cities),
        "elemente": write("elemente", syms + nums),
    }
    print(json.dumps(counts, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
