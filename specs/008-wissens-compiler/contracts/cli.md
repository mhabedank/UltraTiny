# Contract: Commands

Commands added or changed by spec 008. Training-side commands run from `training/` with `uv run`.

## `ut knowledge build`

```bash
uv run ut knowledge build --topic ../topics/chemie --out ../models/chemie.utki
```

- Loads and validates the topic, applies the rules, writes the image and `build.json` next to it
  (`../models/chemie.build.json`).
- Prints a summary: classes, objects, relations, views, explicit facts, derived facts per rule,
  answerable facts (F7), image bytes and bytes per answerable fact (R5), the size per section, and the
  budget (`… B of 58,982 B, …%`).
- Exit 0 on success; exit 1 on any validation error (all errors of the first failing class, each with
  file, line and rule; [topic-format.md](topic-format.md#errors)), on a rule conflict, or when the image
  exceeds `budget_bytes`.
- Deterministic: the same topic files give byte-identical `.utki` and `build.json` (SC-007).

## `ut knowledge check`

```bash
uv run ut knowledge check --topic ../topics/chemie [--image ../models/chemie.utki] [--compat]
```

Runs, in order, and stops at the first failure:

1. build in memory (as above);
2. every competency question of every view renders its `expect` (exact bytes, or the outcome);
3. if `--image`: the given file is byte-identical to the fresh build (committed images are current);
4. if `--compat`: every row of the topic's `compat.oracle` renders the same bytes through its legacy
   letter, or is listed in `compat.changes` with `reviewed = yes` (research R10). Prints the number of
   identical rows, listed changes and unlisted differences (the first 20 in full).

## `ut knowledge cases`

```bash
uv run ut knowledge cases --topic ../topics/chemie --image ../models/chemie.utki \
    --out ../models/chemie_cases.tsv
```

Writes the golden query cases ([query.md](query.md#cases-file-golden-queries)) from the Python
reference.

## `ut knowledge propose` / `accept` (optional, US4)

```bash
uv run ut knowledge propose --topic ../topics/chemie --relation schmelzpunkt --model qwen3.6:35b
uv run ut knowledge accept ../topics/chemie/proposals/2026-12-01.tsv
```

- `propose` lists the subjects of the relation's class without a value, asks the LLM (Spark client of
  `training/tools/shorten_llm.py`) for value, source and reason, and writes
  `proposals/<date>.tsv` with an empty `accepted` column. It changes no fact file.
- `accept` copies rows with `accepted = yes` and a non-`llm:` allowed source into
  `facts/accepted.tsv`, keeping that file sorted; it reports rejected rows.

## `topics/<id>/prepare.py`

```bash
uv run python ../topics/chemie/prepare.py          # rewrite objects.tsv and facts/generated/
uv run python ../topics/chemie/prepare.py --check  # exit 1 if the committed files are stale
```

## Removed

- `ut facts` (writes UTFT v1). The fact set of spec 006 stays available to the training data generator
  (`hybrid.build_facts` without the `.utft` output).

## Changed

| Command | Change |
|---------|--------|
| `ut pipeline` (hybrid configs) | builds the topic image named by the config's `topic` (`[knowledge] topic = "../topics/chemie"`) instead of `facts.utft`; `ut export --facts` takes the `.utki` and writes `"topic"` into the model meta (research R11) |
| `utiny-host` | `--facts` takes `.utki`; new `--kb-cases`, `--query` ([query.md](query.md#host-tool)) |
| `tools/budget_report.py --facts` | accepts `.utki` (magic `UTKI`), same 58,982 B limit |
| `make nodemcu-flash-facts FACTS=…` | checks the `UTKI` magic; default `FACTS ?= models/chemie.utki` |
| `make knowledge` | new: builds `models/<id>.utki` for every topic under `topics/` |
| `tools/bench.py pc/board --facts` | `.utki`; identity check reads `data_sha` of the UTKI header and the new `/info` line |
| `tools/bench.py image --facts IMAGE --suite S --out R.json` | new: image-only KPIs F7, R3, R5 (research R13) |
| `tools/bench_export_facts.py --topic ../topics/chemie` | new source: exports `facts.tsv` rows from the views with a legacy letter |
| `tools/device_knowledge.py --port P --cases C` | new: sends every case as `/wissen` with `/trace an`, compares the answer and reports the lookup time (max, median) |
| `tools/devlib.py` | parses the `Wissen: …` line; new `query(view, key)` |
| `tools/bench_demo.py` | demo items that start with `/wissen` are sent as commands; a board without the command (e.g. `chemie-nodemcu`) shows `—` in its column (FR-021, `bench/demo/008.tsv`) |
