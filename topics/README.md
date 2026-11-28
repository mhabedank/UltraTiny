# Topics

A topic is **data only** (specs/008-wissens-compiler FR-001): the knowledge compiler turns a topic
directory into a knowledge image (`models/<id>.utki`) that the NodeMCU answers from. Nothing in the
compiler, the image format, the query engine or the firmware names a topic, a class or a relation.

```text
topics/<id>/
├── topic.toml      id, schema version, file list, budget
├── schema.toml     classes, relations, rules, views (answer templates), texts, competency questions
├── objects.tsv     key, name, class, source
├── facts/*.tsv     subject, relation, value, source   (one fact per line)
├── prepare.py      optional, reproducible: writes objects.tsv and facts/generated/*.tsv
└── compat/         optional: frozen answers of a predecessor and the reviewed changes
```

Build and check (from `training/`):

```bash
uv run ut knowledge build --topic ../topics/<id> --out ../models/<id>.utki
uv run ut knowledge check --topic ../topics/<id> --image ../models/<id>.utki
```

Formats: [specs/008-wissens-compiler/contracts/topic-format.md](../specs/008-wissens-compiler/contracts/topic-format.md).
