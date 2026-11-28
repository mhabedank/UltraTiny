# Quickstart: Knowledge Compiler

Validation scenarios that show spec 008 works end to end. Commands run from the repository root
unless noted; training commands from `training/` with `uv run`. Formats and commands:
[contracts/](contracts/). 🔌 = needs the NodeMCU, 🖥️ = needs the DGX Spark.

## Prerequisites

- The spec 006 toolchain (Python 3.11+ with `uv`, CMake and a C compiler, PlatformIO for the
  NodeMCU firmware).
- For board steps: a NodeMCU with the 006 layout and, for the end-to-end demo, `chemie-hybrid` from
  spec 006 (T044) plus a second board with `chemie-nodemcu`.

## 1 · Chemistry topic builds (US1, SC-002, SC-003, SC-007, SC-008)

```bash
cd training
uv run python ../topics/chemie/prepare.py --check
time uv run ut knowledge build --topic ../topics/chemie --out ../models/chemie.utki
```

Expected: `prepare.py --check` exits 0; the build finishes in under a minute and prints
≥ 2,855 answerable facts, an image ≤ 58,982 B and ≤ 8.56 B per answerable fact, with the size split
into sections. A second build gives the same SHA-256 for `.utki` and `build.json`.

## 2 · Nothing lost against spec 006 (SC-001)

```bash
uv run ut knowledge check --topic ../topics/chemie --image ../models/chemie.utki --compat
```

Expected: all competency questions pass; every oracle row is identical or listed in
`topics/chemie/compat/changes.tsv` with `reviewed = yes`; 0 unlisted differences.

## 3 · Validation stops bad data (US1 scenario 6, US2 scenarios 2 and 4)

```bash
uv run pytest tests/test_knowledge_topic.py tests/test_knowledge_rules.py -q
```

Expected: the fixture topics with a wrong type, a second value for a `one` relation, a missing
source, an `llm:` source, a non-unique `reverse = one` value, a rule conflict and a list that cannot
fit each fail with file, line and rule in the message.

## 4 · C engine equals the Python reference (FR-014)

```bash
uv run ut knowledge cases --topic ../topics/chemie --image ../models/chemie.utki --out ../models/chemie_cases.tsv
cd .. && cmake -S runtime -B build/runtime && cmake --build build/runtime && ctest --test-dir build/runtime
./build/runtime/utiny-host --facts models/chemie.utki --kb-cases models/chemie_cases.tsv
./build/runtime/utiny-host --facts models/chemie.utki --query "familie< Halogene"
```

Expected: all CTest tests pass, including the alignment-checked build; `--kb-cases` reports every
case identical; the query prints the halogen list.

## 5 · Second topic without a code change (US3, SC-004)

```bash
cd training
uv run ut knowledge check --topic ../topics/schach
uv run ut knowledge build --topic ../topics/schach --out ../models/schach.utki
uv run ut knowledge cases --topic ../topics/schach --image ../models/schach.utki --out ../models/schach_cases.tsv
cd .. && ./build/runtime/utiny-host --facts models/schach.utki --kb-cases models/schach_cases.tsv
git diff --stat <commit before the chess topic>..<commit that adds it>
```

Expected: every chess competency question passes; the diff touches only `topics/schach/`, the chess
image, its cases file and their test registration, with zero lines in
`training/src/ultratiny/knowledge/`, `runtime/`, `firmware-nodemcu/` and `contracts/image-format.md`.

## 6 · Benchmark (FR-020)

```bash
uv run python ../tools/bench.py image --facts ../models/chemie.utki --suite ../bench/suites/chemie \
    --out ../bench/results/chemie_chemie_image_<date>.json
uv run python ../tools/bench_export_facts.py --topic ../topics/chemie --out /tmp/facts.tsv
cmp /tmp/facts.tsv ../bench/suites/chemie/facts.tsv
uv run python ../tools/bench_report.py ../bench/results/chemie_chemie_image_<date>.json \
    --baseline ../bench/results/chemie-nodemcu_chemie_pc_20261123.json \
    --predecessor ../bench/results/chemie-hybrid-utft1_chemie_image.json \
    --md ../bench/results/008.md --html ../bench/results/008.html
```

Expected: F7 ≥ 2,855 and R5 ≤ 8.56 in the report, compared with the 006 table; the exported
`facts.tsv` equals the pinned file, or the difference is exactly the reviewed changes and the suite
version is bumped.

## 7 · On the board 🔌 (SC-001, SC-004, SC-005, SC-006)

```bash
make nodemcu-build && make nodemcu-flash
make nodemcu-flash-facts FACTS=models/chemie.utki
python tools/device_knowledge.py --port /dev/ttyUSB0 --cases models/chemie_cases.tsv
```

Expected:
- the boot line and `/info` show `Wissen: OK v1, Thema chemie (Schema 1), …`;
- `device_knowledge.py` reports every case identical and a maximum lookup time ≤ 50 ms;
- `tools/budget_report.py` (run by the build) shows firmware ≤ 360,448 B, image ≤ 58,982 B and the
  static RAM growth ≤ 1 KB;
- with `chemie-hybrid` flashed: `tools/device_parity.py` passes the 006 golden cases (printed answers
  identical), first character ≤ 2 s, ≥ 5 chars/s (007 board run).

Then the chess image on the same board, and the failure paths:

```bash
make nodemcu-flash-facts FACTS=models/schach.utki
python tools/device_knowledge.py --port /dev/ttyUSB0 --cases models/schach_cases.tsv
```

Expected: all chess cases identical. With a model whose meta says `topic = chemie`, the boot line
reads `Wissen: falsches Thema (Bild schach, Modell chemie)` and a fact question prints the "missing"
text, while `Hi` still gets a greeting. After erasing the area (`esptool erase_region 0x100000
0x10000`): `Wissen: fehlt`, fact questions print the missing text, greetings and explanations work.

## 8 · Demo next to the baseline 🔌 (FR-021)

```bash
python tools/bench_demo.py --a /dev/ttyUSB0 --a-label chemie-hybrid --b /dev/ttyUSB1 --b-label chemie-nodemcu \
    --script bench/demo/008.tsv --out bench/results/demo_008.md
```

Expected: 10–15 items side by side; the fact questions answered from the new image on board A, at
least 3 reverse queries and 2 rule results as `/wissen` items (board B shows `—`).

## 9 · Optional: LLM proposals (US4) 🖥️

```bash
uv run ut knowledge propose --topic ../topics/chemie --relation familie --model qwen3.6:35b
git status --short ../topics/chemie/facts   # unchanged
uv run ut knowledge accept ../topics/chemie/proposals/<date>.tsv
```

Expected: the proposal run writes only `proposals/<date>.tsv`; `accept` copies only reviewed rows
with a non-`llm:` source into `facts/accepted.tsv`.
