# Tasks: ESP32-Chemielehrer

**Input**: spec.md, plan.md in `specs/003-chemielehrer/`

## Phase 1: Setup

- [X] T001 Add topics `chemie_*`, `ueber_mich`, `abweisen` to training/data/topics.toml
- [X] T002 Add `free_repeat` to DataConfig and oversample free-relation train lines in training/src/ultratiny/config.py and training/src/ultratiny/datagen.py
- [X] T003 Create training/configs/chemie.toml (6 × 192, MQA, d_ff 512, ctx 192, dropout 0.1, eval thresholds from spec SC-001..SC-004)

## Phase 2: Foundational (data)

- [X] T004 [P] Compute periodic-table position (group, period, category, state at 20 °C) from the atomic number in training/tools/periodic.py
- [X] T005 [P] Extend training/tools/fetch_wikidata.py with `--chemie`: atomic mass, melting/boiling point (normalized to °C) → training/data/facts/wikidata_elemente_chemie.tsv
- [X] T006 [P] Element-profile templates (symbol, Ordnungszahl, Atommasse, Gruppe, Periode, Kategorie, Zustand, Schmelz-/Siedepunkt; reverse where unique) in training/data/templates/chemie.toml

## Phase 3: User Story 1 – Ask the chemistry teacher (P1)

- [X] T007 [P] [US1] Concept Q&A Themenfelder 3.1–3.4 in training/data/facts/chemie_rlp_a.tsv
- [X] T008 [P] [US1] Concept Q&A Themenfelder 3.5–3.8 in training/data/facts/chemie_rlp_b.tsv
- [X] T009 [P] [US1] Concept Q&A Themenfelder 3.9–3.12 in training/data/facts/chemie_rlp_c.tsv
- [X] T010 [P] [US1] Compounds (name ↔ formula, everyday names, uses) and simple reactions in training/data/facts/chemie_verbindungen.tsv
- [X] T011 [US1] Chemistry demo list (≥ 40 prompts, all Themenfelder + elements + compounds) in training/data/demo_chemie.tsv
- [X] T012 [US1] Validate all chemistry data with `ut datagen --config configs/chemie.toml` (alphabet, length ≤ 160, sources)

## Phase 4: User Story 2 – Honest "I don't know" (P1)

- [X] T013 [P] [US2] Persona answers (chemistry teacher) in training/data/facts/chemie_persona.tsv
- [X] T014 [P] [US2] Off-topic / nonsense refusal examples in training/data/facts/abweisen.tsv
- [X] T015 [US2] Refusal + false-refusal metrics in training/src/ultratiny/evaluate.py and pipeline thresholds in training/src/ultratiny/cli.py; tests in training/tests/test_evaluate.py

## Phase 5: User Story 3 – Bigger model, longer training (P2)

- [ ] T016 [US3] Train `runs/chemie` (CPU here or MPS on the M3), check eval + budget, iterate on data if thresholds fail
- [ ] T017 [US3] Commit models/chemie.utny + golden/eval/run.json; host parity (`utiny-host --golden`) and QEMU parity
- [ ] T018 [US3] Record results in specs/003-chemielehrer/measurements.md; README section "Chemielehrer" (make qemu MODEL=models/chemie.utny)

## Phase 6: DGX Spark (added 2026-11-21)

- [X] T019 CUDA device support (`--device cuda`, auto: CUDA > MPS > CPU) in training/src/ultratiny/train.py
- [X] T020 Train-only LLM augmentation (phrasings, templates, refusals) with leak/conflict/source filters in training/src/ultratiny/augment.py and training/src/ultratiny/datagen.py; tests in training/tests/test_augment.py
- [X] T021 Ollama generator with judge pass and resume cache in training/tools/augment_llm.py; wrapper tools/spark/augment.sh
- [X] T022 Docker image (NGC PyTorch, CUDA on GB10) in training/docker/Dockerfile.spark; multi-seed training + parity + best-run selection in tools/spark/train.sh, tools/spark/select_best.py
- [X] T023 Config training/configs/chemie-spark.toml (60k steps, batch 128, augmentation) and guide training/SPARK.md
- [ ] T024 Run augmentation on the Spark, commit training/data/augment/*.tsv (user)
- [ ] T025 Train on the Spark, commit models/chemie.* and record results in measurements.md (user)

## Dependencies

T001–T003 → T004–T006 → T007–T014 (parallel) → T012, T015 → T016 → T017 → T018
