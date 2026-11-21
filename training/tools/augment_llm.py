#!/usr/bin/env python3
"""Generate training augmentation with a local LLM via Ollama (e.g. on the DGX Spark).

Writes train-only snapshot files into data/augment/ (read by datagen, see ultratiny/augment.py):

    paraphrase  extra question phrasings for every free fact (answers stay curated)
    templates   extra question templates for structured relations (element profiles, formulas)
    refusals    off-topic / nonsense inputs for the refusal relation

Every candidate is (1) sanitized and checked against the model alphabet, (2) checked by a
second "judge" prompt, and (3) deduplicated. Held-out prompts are never shown to the LLM and are
filtered again in datagen, so SC-002/SC-003 stay honest. Standard library only.

    python3 tools/augment_llm.py --host http://localhost:11434 paraphrase --n 15
    python3 tools/augment_llm.py templates --n 12
    python3 tools/augment_llm.py refusals --n 3000
    python3 tools/augment_llm.py all            # all three with defaults

Progress is cached in runs/augment_cache/ so an interrupted run resumes where it stopped.
"""

from __future__ import annotations

import argparse
import concurrent.futures as cf
import csv
import glob
import hashlib
import json
import random
import re
import sys
import threading
import time
import tomllib
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from ultratiny.alphabet import Alphabet  # noqa: E402
from ultratiny.augment import PLACEHOLDER, sanitize  # noqa: E402

AB = Alphabet()
AUG = ROOT / "data" / "augment"
CACHE = ROOT / "runs" / "augment_cache"
FREE_FILES = ["chemie_rlp_*.tsv", "chemie_reaktionen.tsv", "chemie_persona.tsv"]
REFUSAL_TOPICS = [
    "Fußball und andere Sportarten", "Musik, Bands und Konzerte", "Filme, Serien und Streaming",
    "Promis und Influencer", "Geschichte und Jahreszahlen", "Politik und Wahlen",
    "Erdkunde, Länder und Hauptstädte", "Wetter und Klima im Alltag", "Kochen und Rezepte",
    "Tiere und Haustiere", "Mathe-Rechenaufgaben", "Programmieren und Computer",
    "Videospiele", "Liebe, Freundschaft und persönliche Ratschläge", "Witze und Rätsel",
    "Übersetzungen und Sprachen", "Uhrzeit, Datum und Kalender", "Meinungsfragen",
    "Physik (nicht Chemie)", "Biologie und der menschliche Körper (nicht Chemie)",
    "Astronomie und Weltraum", "Autos und Verkehr", "Schule allgemein (Hausaufgaben, Lehrer)",
    "Geld, Einkaufen und Preise", "Reisen und Urlaub", "Kunst und Literatur",
    "Religion und Philosophie", "Technik und Smartphones",
    "einzelne Wörter, Satzfragmente und Füllwörter (z. B. 'Und?', 'Alle', 'Okay')",
    "Tastatur-Gestammel und sinnlose Zeichenfolgen (z. B. 'asdf', 'lkj lkj')",
    "englische Fragen zu Alltagsthemen", "lange, abschweifende Sätze ohne klare Frage",
    "Listen-Wünsche ('Zähl alle ... auf')", "Fragen mit Chemie-Wörtern in übertragener Bedeutung "
    "(z. B. 'Stimmt die Chemie zwischen uns?')",
]  # fmt: skip


# ---------------------------------------------------------------- logging

LOG_FILE = ROOT / "runs" / "augment.log"
_log_lock = threading.Lock()
_tl = threading.local()  # per-item stats: LLM calls, cache hits, LLM seconds


def log(msg: str) -> None:
    line = f"{time.strftime('%H:%M:%S')} {msg}"
    with _log_lock:
        print(line, flush=True)
        LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
        with LOG_FILE.open("a", encoding="utf-8") as f:
            f.write(line + "\n")


def fmt_dur(sec: float) -> str:
    sec = int(sec)
    return (
        f"{sec // 3600}h{sec % 3600 // 60:02d}m" if sec >= 3600 else f"{sec // 60}m{sec % 60:02d}s"
    )


# ---------------------------------------------------------------- LLM client


class Ollama:
    def __init__(self, host: str, model: str, seed: int, timeout: float = 600):
        self.host, self.model, self.seed, self.timeout = host.rstrip("/"), model, seed, timeout

    def json(self, prompt: str, schema: dict, temperature: float = 0.8, salt: str = "") -> dict:
        body = {
            "model": self.model,
            "messages": [{"role": "user", "content": prompt}],
            "stream": False,
            "format": schema,
            "options": {"temperature": temperature, "seed": self.seed + int(
                hashlib.sha256(salt.encode()).hexdigest()[:6], 16)},
        }  # fmt: skip
        if self.model.startswith("gpt-oss"):
            body["think"] = "low"
        req = urllib.request.Request(
            self.host + "/api/chat", data=json.dumps(body).encode(),
            headers={"Content-Type": "application/json"},
        )  # fmt: skip
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as r:
                content = json.load(r)["message"]["content"]
        except urllib.error.HTTPError as e:
            msg = e.read().decode(errors="replace")[:200]
            raise RuntimeError(f"Ollama HTTP {e.code}: {msg}") from None
        return json.loads(content)


def _schema(key: str, item_type: str) -> dict:
    return {
        "type": "object",
        "properties": {key: {"type": "array", "items": {"type": item_type}}},
        "required": [key],
    }


LIST_SCHEMA = _schema("items", "string")
JUDGE_SCHEMA = _schema("ok", "integer")


# ---------------------------------------------------------------- helpers


def clean(text: str, max_len: int = 150) -> str | None:
    t = sanitize(text).strip()
    t = re.sub(r"^\s*(\d+[.)]|[-*])\s+", "", t)  # list markers
    if not t or len(t) > max_len or AB.invalid_chars(PLACEHOLDER.sub("", t)):
        return None
    if "{" in PLACEHOLDER.sub("", t) or "}" in PLACEHOLDER.sub("", t):
        return None
    return t


def norm(s: str) -> str:
    return " ".join(re.sub(r"[?.!,]", " ", s.lower()).split())


def read_tsv(path: Path) -> list[dict]:
    with path.open(encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f, delimiter="\t", quoting=csv.QUOTE_NONE))


def write_tsv(path: Path, cols: list[str], rows: list[tuple]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = "\t".join(cols) + "\n" + "".join("\t".join(r) + "\n" for r in rows)
    path.write_text(text, encoding="utf-8")


def cached(kind: str, key: str, fn):
    """Run fn() once per (kind, key); results persist in runs/augment_cache/<kind>.jsonl."""
    CACHE.mkdir(parents=True, exist_ok=True)
    path = CACHE / f"{kind}.jsonl"
    store = cached.stores.setdefault(kind, {})
    if not store and path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            d = json.loads(line)
            store[d["key"]] = d["value"]
    _tl.calls = getattr(_tl, "calls", 0) + 1
    if key in store:
        _tl.hits = getattr(_tl, "hits", 0) + 1
        return store[key]
    t0 = time.time()
    value = fn()
    _tl.llm_s = getattr(_tl, "llm_s", 0.0) + time.time() - t0
    with cached.lock:
        store[key] = value
        with path.open("a", encoding="utf-8") as f:
            f.write(json.dumps({"key": key, "value": value}, ensure_ascii=False) + "\n")
    return value


cached.stores = {}
cached.lock = threading.Lock()


def judge(llm: Ollama, task: str, candidates: list[str], salt: str) -> list[str]:
    if not candidates:
        return []
    listing = "\n".join(f"{i}: {c}" for i, c in enumerate(candidates))
    prompt = (f"{task}\n\nKandidaten:\n{listing}\n\nGib die Nummern aller Kandidaten zurück, "
              "die die Bedingung erfüllen, als JSON {\"ok\": [...]}.")  # fmt: skip
    res = llm.json(prompt, JUDGE_SCHEMA, temperature=0.0, salt="judge" + salt)
    return [
        candidates[i] for i in res.get("ok", []) if isinstance(i, int) and 0 <= i < len(candidates)
    ]


def run_parallel(items, fn, workers: int, label, describe):
    """Run fn over items in threads; log one line per finished item with progress and ETA."""
    items = list(items)
    total, done, fresh, t0 = len(items), 0, 0, time.time()

    def wrapped(it):
        _tl.calls, _tl.hits, _tl.llm_s = 0, 0, 0.0
        t = time.time()
        res = fn(it)
        return res, _tl.calls, _tl.hits, time.time() - t

    with cf.ThreadPoolExecutor(workers) as ex:
        futs = {ex.submit(wrapped, it): it for it in items}
        for fut in cf.as_completed(futs):
            done += 1
            it = futs[fut]
            try:
                res, calls, hits, dt = fut.result()
            except Exception as e:  # keep going; failed items are retried on the next run
                log(f"[{done:>4}/{total}] {label(it)}  FEHLER: {e}")
                continue
            from_cache = calls > 0 and hits == calls
            fresh += not from_cache
            elapsed = time.time() - t0
            eta = elapsed / done * (total - done) if fresh else 0
            src = "Cache" if from_cache else f"{dt:5.1f} s"
            log(f"[{done:>4}/{total}] {label(it):<28} {describe(res):<26} {src:>8}"
                f"  | {fmt_dur(elapsed)} vergangen, noch ~{fmt_dur(eta)}")  # fmt: skip
            yield res


# ---------------------------------------------------------------- tasks


def task_paraphrase(llm: Ollama, judge_llm: Ollama, n: int, workers: int) -> None:
    facts = []
    for pat in FREE_FILES:
        for p in sorted(glob.glob(str(ROOT / "data" / "facts" / pat))):
            facts += read_tsv(Path(p))
    taken = {norm(q) for f in facts for q in f["subject"].split("|")}

    def one(f: dict):
        train = f["subject"].split("|")[:-1]  # the last phrasing is held out: never shown

        def gen():  # noqa: E306
            prompt = (
                "Du hilfst beim Erstellen von Trainingsdaten für einen kleinen Chemie-Lehrer-"
                "Chatbot (Schule, Klasse 7-10, Deutsch).\n"
                f"Antwort des Chatbots: {f['object']}\n"
                f"Bisherige Fragen, auf die genau diese Antwort passt:\n- " + "\n- ".join(train) +
                f"\n\nSchreibe {n} weitere, möglichst unterschiedliche deutsche Fragen, die "
                "Schülerinnen und Schüler stellen könnten und auf die GENAU diese Antwort passt. "
                "Mische Stile: formell, umgangssprachlich, kurz (2-3 Wörter), mit 'du', als "
                "Aufforderung ('Erklär mal ...'). Keine Antwort, nur Fragen. Max. 120 Zeichen. "
                "Nur normale Zeichen, Formeln wie H2O."
            )  # fmt: skip
            return llm.json(prompt, LIST_SCHEMA, salt=f["id"])["items"]

        raw = cached("paraphrase_gen", f["id"], gen)
        cands = [c for c in dict.fromkeys(filter(None, map(clean, raw))) if norm(c) not in taken]
        ok = cached("paraphrase_judge", f["id"], lambda: judge(
            judge_llm, "Prüfe: Passt die folgende Antwort vollständig und korrekt auf die Frage? "
            f"Antwort: {f['object']}", cands, f["id"]))  # fmt: skip
        return f["id"], [c for c in ok if c in cands], len(cands)

    rows, seen = [], set(taken)
    log(f"Formulierungen: {len(facts)} Fragen, je {n} neue Vorschläge + Prüfung")
    for fid, qs, _ in run_parallel(
        facts, one, workers, label=lambda f: f["id"],
        describe=lambda r: f"{r[2]:>2} Vorschläge -> {len(r[1]):>2} ok",
    ):  # fmt: skip
        for q in qs:
            if norm(q) not in seen:
                seen.add(norm(q))
                rows.append((fid, q, f"llm:{llm.model}"))
    rows.sort()
    write_tsv(AUG / "paraphrasen.tsv", ["id", "phrasing", "source"], rows)
    log(f"-> paraphrasen.tsv: {len(rows)} Formulierungen für {len({r[0] for r in rows})} Fragen")


def task_templates(llm: Ollama, judge_llm: Ollama, n: int, workers: int) -> None:
    raw = tomllib.loads((ROOT / "data" / "templates" / "chemie.toml").read_text(encoding="utf-8"))
    rels = {k: v for k, v in raw["relations"].items() if not v.get("free")}
    sample = {}
    for r in read_tsv(ROOT / "data" / "facts" / "wikidata_elemente_chemie.tsv"):
        sample.setdefault(r["relation"], r)
    for r in read_tsv(ROOT / "data" / "facts" / "chemie_verbindungen.tsv"):
        sample.setdefault(r["relation"], r)

    def one(item):
        rel, spec = item
        default = spec["answers"][0]
        train = [q for q in spec["questions"] if q.get("split", "train") == "train"]
        fwd = [q["text"] for q in train if not q.get("answer")]

        def gen():  # noqa: E306
            prompt = (
                "Erzeuge Frage-Vorlagen für einen kleinen deutschen Chemie-Chatbot (Klasse 7-10).\n"
                f"Antwort-Vorlage: {default}\n"
                "Bestehende Frage-Vorlagen (gleiche Bedeutung):\n- " + "\n- ".join(fwd) +
                f"\n\nSchreibe {n} weitere, unterschiedliche Frage-Vorlagen mit genau derselben "
                "Bedeutung, sodass die Antwort-Vorlage passt. Verwende die Platzhalter {subject} "
                "(und falls nötig {object}) exakt so geschrieben. "
                "Mische formell, umgangssprachlich "
                "und kurz. Max. 100 Zeichen."
            )  # fmt: skip
            return llm.json(prompt, LIST_SCHEMA, salt=rel)["items"]

        cands = []
        for c in cached("templates_gen", rel, gen):
            c = clean(c, 110)
            if c and PLACEHOLDER.search(c) and "{object}" not in c:  # forward questions only
                cands.append(c)
        cands = list(dict.fromkeys(cands))
        s = sample.get(rel)
        if not s or not cands:
            return rel, [], 0
        filled = [c.replace("{subject}", s["subject"]) for c in cands]
        answer = default.replace("{subject}", s["subject"]).replace("{object}", s["object"])
        ok = cached("templates_judge", rel, lambda: judge(
            judge_llm,
            f"Prüfe: Passt die Antwort '{answer}' vollständig und korrekt auf die Frage?",
            filled, rel))  # fmt: skip
        return rel, [c for c, fq in zip(cands, filled, strict=True) if fq in ok], len(cands)

    rows = []
    log(f"Vorlagen: {len(rels)} Relationen, je {n} neue Vorschläge + Prüfung")
    for rel, ts, _ in run_parallel(
        list(rels.items()), one, workers, label=lambda it: it[0],
        describe=lambda r: f"{r[2]:>2} Vorschläge -> {len(r[1]):>2} ok",
    ):  # fmt: skip
        rows += [(rel, t, "", f"llm:{llm.model}") for t in ts]
    rows.sort()
    write_tsv(AUG / "vorlagen.tsv", ["relation", "text", "answer", "source"], rows)
    log(f"-> vorlagen.tsv: {len(rows)} Vorlagen für {len({r[0] for r in rows})} Relationen")


def task_refusals(llm: Ollama, judge_llm: Ollama, n: int, workers: int) -> None:
    per_call = 25
    calls = [
        (t, k) for t in REFUSAL_TOPICS for k in range(max(1, n // (per_call * len(REFUSAL_TOPICS))))
    ]
    existing = set()
    for r in read_tsv(ROOT / "data" / "facts" / "abweisen.tsv"):
        existing |= {norm(q) for q in r["subject"].split("|")}

    def one(call):
        topic, k = call
        key = f"{topic}#{k}"

        def gen():  # noqa: E306
            prompt = (
                "Erzeuge Eingaben, die Nutzer an einen Chemie-Lehrer-Chatbot schicken könnten, die "
                f"aber NICHTS mit Chemie zu tun haben. Thema: {topic}.\n"
                f"Schreibe {per_call} unterschiedliche Eingaben (Variante {k + 1}): Fragen, "
                "Aufforderungen oder Fragmente, gemischt formell/umgangssprachlich, manche mit "
                "Tippfehlern, manche kleingeschrieben. Max. 120 Zeichen. Keine Chemie!"
            )  # fmt: skip
            return llm.json(prompt, LIST_SCHEMA, salt=key)["items"]

        cands = [c for c in dict.fromkeys(filter(None, map(clean, cached("refusal_gen", key, gen))))
                 if norm(c) not in existing]  # fmt: skip
        ok = cached("refusal_judge", key, lambda: judge(
            judge_llm, "Prüfe: Welche Eingaben haben KEINEN Bezug zu Chemie (keine Frage zu "
            "Stoffen, Elementen, Reaktionen, Atomen, Laborarbeit oder chemischen Begriffen)?",
            cands, key))  # fmt: skip
        return [c for c in ok if c in cands], len(cands)

    rows, seen = [], set(existing)
    log(f"Abweisungen: {len(calls)} Aufrufe, {len(REFUSAL_TOPICS)} Themen, je {per_call} Eingaben")
    for qs, _ in run_parallel(
        calls, one, workers, label=lambda c: f"{c[0][:22]} #{c[1] + 1}",
        describe=lambda r: f"{r[1]:>2} Vorschläge -> {len(r[0]):>2} ok",
    ):  # fmt: skip
        for q in qs:
            if norm(q) not in seen:
                seen.add(norm(q))
                rows.append((q, f"llm:{llm.model}"))
    rows.sort()
    write_tsv(AUG / "abweisen.tsv", ["phrasing", "source"], rows)
    log(f"-> abweisen.tsv: {len(rows)} Abweisungs-Eingaben")


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--host", default="http://localhost:11434")
    ap.add_argument("--model", default="gpt-oss:120b")
    ap.add_argument("--judge-model", default=None, help="default: same as --model")
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--seed", type=int, default=1234)
    sub = ap.add_subparsers(dest="task", required=True)
    for name, default_n in (("paraphrase", 15), ("templates", 12), ("refusals", 3000), ("all", 0)):
        p = sub.add_parser(name)
        p.add_argument("--n", type=int, default=default_n)
    a = ap.parse_args()
    random.seed(a.seed)
    llm = Ollama(a.host, a.model, a.seed)
    judge_llm = Ollama(a.host, a.judge_model or a.model, a.seed)
    log(f"Start: {a.task}, Modell {llm.model}, Prüfer {judge_llm.model}, {a.workers} parallel, "
        f"Log: {LOG_FILE}")  # fmt: skip
    for m in {x.model: x for x in (llm, judge_llm)}.values():
        t = time.time()
        try:
            m.json('Antworte nur mit {"items": ["ok"]}.', LIST_SCHEMA, temperature=0.0)
        except Exception as e:
            log(f"Modell {m.model} antwortet nicht: {e}")
            return 1
        log(f"Modell {m.model} antwortet ({time.time() - t:.1f} s, inkl. evtl. Laden)")
    if a.task in ("paraphrase", "all"):
        task_paraphrase(llm, judge_llm, a.n or 15, a.workers)
    if a.task in ("templates", "all"):
        task_templates(llm, judge_llm, a.n or 12, a.workers)
    if a.task in ("refusals", "all"):
        task_refusals(llm, judge_llm, a.n or 3000, a.workers)
    log("Fertig.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
