# Contract: Topic Format

A topic is a directory `topics/<id>/` with data files only (FR-001). The compiler
(`ultratiny.knowledge`) reads it; nothing in the compiler, the image format, the query engine or the
firmware names a topic, a class or a relation. Entities and validation rules:
[data-model.md](../data-model.md).

## `topic.toml`

```toml
id = "chemie"                     # [a-z][a-z0-9_]*, ≤ 15 B, equals the directory name
schema_version = 1
title = "Chemie Klasse 7–10"
alphabet = "../../training/configs/chemie-hybrid.toml"   # model alphabet for keys and names
object_files = ["objects.tsv"]
fact_files = ["facts/generated/*.tsv", "facts/*.tsv"]    # globs, sorted, read in this order
budget_bytes = 58982              # optional, default 58982

[compat]                          # optional (chemistry only)
oracle = "compat/utft1_answers.tsv"
changes = "compat/changes.tsv"
```

## `schema.toml`

```toml
[texts]
unknown = "Das weiß ich leider nicht."
not_applicable = ": dazu habe ich keine Angabe."
fallback_sep = "– "
list_sep = ", "
list_last = " und "

[classes.element]
order_by = "ordnungszahl"
[classes.verbindung]              # no order_by: order of appearance in the object files

[relations.ordnungszahl]
subject = "element"
type = "int"
card = "one"
reverse = "one"

[relations.familie]
subject = "element"
type = "enum"
values = ["Alkalimetalle", "Erdalkalimetalle", "Halogene", "Edelgase", "…"]
card = "one"
reverse = "many"

[relations.atommasse]
subject = "element"
type = "dec"
decimals = 2
card = "one"
reverse = "one"

[[rules]]
id = "alkali"
kind = "class"
if_relation = "gruppe_nr"
equals = "1"
except = ["H"]
add_relation = "familie"
add_value = "Alkalimetalle"

[[rules]]
id = "hauptgruppe"
kind = "table"
from = "gruppe_nr"
add_relation = "hauptgruppe"
map = { "1" = "1", "2" = "2", "13" = "3", "14" = "4", "15" = "5", "16" = "6", "17" = "7", "18" = "8" }

[[rules]]
id = "art_beschreibung"           # example of a chain rule
kind = "chain"
first = "art"                     # (s, art, o) where o is an object
then = "beschreibung"             # (o, beschreibung, v)
add_relation = "art_beschreibung" # → (s, art_beschreibung, v)

[views.ordnungszahl]
kind = "forward"
relation = "ordnungszahl"
letter = "O"
template = "Die Ordnungszahl von {name} ist {v}."
questions = [
  { question = "Welche Ordnungszahl hat Kupfer?", key = "Cu", expect = "Die Ordnungszahl von Kupfer ist 29." },
]

[views."ordnungszahl<"]
kind = "reverse"
relation = "ordnungszahl"
letter = "o"
template = "Die Ordnungszahl {key} hat {name}."
questions = [ { question = "Welches Element hat die Ordnungszahl 29?", key = "29", expect = "Die Ordnungszahl 29 hat Kupfer." } ]

[views."familie<"]
kind = "reverse"
relation = "familie"
template = "Diese Elemente sind {key}: {v}."  # no inflection: grammar is spec 010
more = " und {n} weitere"
# expect is the exact answer the build renders; shown shortened here
questions = [ { question = "Welche Elemente sind Halogene?", key = "Halogene", expect = "Diese Elemente sind Halogene: Fluor, Chlor, …" } ]

[views.symbol]
kind = "self"
classes = ["element"]
letter = "S"
template = "Das Symbol von {name} ist {key}."

[views.profil]
kind = "profile"
classes = ["element"]
letter = "E"
template = "Das Element {name} ({key}) ist ein {r:kategorie} mit der Ordnungszahl {r:ordnungszahl}."
not_applicable = "{name} kenne ich nicht genau genug für ein Kurzprofil."
```

Rules:
- Every relation must be used by at least one view, and every view needs at least one entry in
  `questions` (FR-002). `expect` is the exact answer, or `unknown` or `na`.
- A view's template must start with fixed text and may only use the slots of its kind
  ([data-model.md](../data-model.md#view)).
- `more` is required for views that can return more than one item (`card = many` forward, `reverse =
  many` reverse).
- Names of classes, relations and views use `[a-z][a-z0-9_]*`; a reverse view name may end in `<`.

## `objects.tsv`

Tab-separated, UTF-8, header line required, `#` lines are comments:

```text
key	name	class	source
H	Wasserstoff	element	wikidata:Q556
H2O	Wasser	verbindung	own
```

## `facts/*.tsv`

```text
subject	relation	value	source
Cu	ordnungszahl	29	wikidata:Q753
Cu	familie	Übergangsmetalle	wikidata:Q753
NaCl	bindung	Ionenbindung	computed
```

- One fact per line. A `card = many` relation has one line per value; the value order in the image is
  the order of the value table (byte order), not the line order.
- Sources must have a prefix from `DATA_LICENSES.md`; `llm:` is rejected for facts (R14).

## `prepare.py` (optional)

A topic may ship a preparation script for calculations the rule kinds cannot express (FR-008). It
must be deterministic, write only `objects.tsv` and files under `facts/generated/`, and take no
arguments other than `--check` (exit 1 if the written files would differ from the committed ones).
The compiler never runs it; CI runs `prepare.py --check`.

The chemistry script runs `ultratiny.factgen.build` with `training/configs/chemie-hybrid.toml` and
writes its objects and values as triples (research R3).

## `compat/` (optional)

- `utft1_answers.tsv`: `letter	key	outcome	answer`; `outcome` is `fact`, `na`, `unknown`.
  Frozen once from UTFT v1 (research R10).
- `changes.tsv`: `letter	key	old	new	reason	reviewed`; only rows with `reviewed = yes` excuse a
  difference.

## `proposals/` (optional)

`<YYYY-MM-DD>.tsv` with `subject	relation	value	source	reason	accepted` (research R14).

## Errors

Every error names the file, the line (or the TOML key) and the rule, for example:

```text
topics/chemie/facts/zusatz.tsv:14: relation 'ordnungszahl' is card=one, but Cu already has 29 (facts/generated/elemente.tsv:288)
topics/chemie/schema.toml:[rules.alkali]: derived (Na, familie, Alkalimetalle) contradicts (Na, familie, Erdalkalimetalle) from facts/generated/elemente.tsv:401
topics/chemie/schema.toml:[views."familie<"]: list for 'Metalle' does not fit 100 B even with one item
```
