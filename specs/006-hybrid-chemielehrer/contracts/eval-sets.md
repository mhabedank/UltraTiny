# Contract: Held-back Sets, Short-test File and Evaluation Report

Implements FR-009, FR-010, SC-001–SC-005 and US3 (research R7, R9, R10).

## Files written by datagen (`runs/<name>/data/`)

| File | Content |
|------|---------|
| `train.txt` | `question \t target` (target is text or `\x01` + type + key) |
| `heldout_combo.jsonl` | Held-back type × object combinations |
| `heldout_family.jsonl` | Held-back phrasing families |
| `heldout_explain.jsonl` | Held-back short explanations |
| `heldout_refusal.jsonl` | Off-topic questions and unknown objects |
| `kurzarbeit.jsonl` | The short-test set (copied, with pin check) |
| `trained_sample.jsonl` | 500 random training prompts, to measure memorisation |
| `heldback.json` | The lists of held-back combinations and families, plus the seed |
| `dataset.sha256` | Hash over all of the above plus `facts.utft` |

Every `*.jsonl` row:

```json
{"prompt": "...", "kind": "fact|explain|refuse|unknown|multi",
 "expected": ["OCu"] | ["Reaktion", "Stoffe"] | [],
 "type": "O", "object": "Cu", "family": "imp"}
```

- `expected` for `fact` holds the accepted function outputs without `<fn>`. The first one is the canonical one.
- For `explain` it holds the required keywords.

## Short-test file `training/data/eval/kurzarbeit.tsv`

```text
id	grade	kind	question	expected
ka/001	8	fact	Gib das Elementsymbol von Natrium an.	element_symbol: Na
ka/014	9	fact	Wie viele Valenzelektronen besitzt ein Stickstoffatom?	element_aussenelektronen: N
ka/031	9	fact	Symbol und Ordnungszahl von Gold?	element_symbol: Au | element_ordnungszahl: Au | element_profil: Au
ka/077	8	explain	Was versteht man unter einem Element?	Stoff; nicht
ka/101	10	refuse	Wer hat die Fußball-WM 2014 gewonnen?
ka/110	9	unknown	Welche Formel hat Unobtainiumchlorid?
```

- `fact`/`multi` entries are written as `question type name: key`; datagen maps the name to its
  type code (`element_symbol: Na` → `SNa`).
- At least 120 rows. The config pins the file by `kurzarbeit_sha256`. Datagen fails if the hash
  differs, which forces an explicit re-pin after the user's review.
- It is never read for training. Datagen drops any training prompt whose normalised form (lower case,
  no `?.!,`, collapsed spaces) equals a short-test question, and reports how many it dropped.

## Scoring

| Kind | Correct when | Wrong fact when |
|------|--------------|-----------------|
| `fact`, `multi` | The function output equals one of `expected`, **or** it renders the same printed answer as the canonical one | The output is a function output whose rendered value differs from every expected one (another object, or another type with a different value) |
| `explain` | Plain text, ≤ 60 chars, all keywords present (case-insensitive) | – |
| `refuse` | The output is a refusal (as in 003/005: plain text matching the refusal answers) | – |
| `unknown` | Refusal, `Das weiß ich leider nicht.`, or a function output that renders `UNKNOWN`/not applicable | A function output that renders a real fact |

- A `fact` question answered with a refusal or `UNKNOWN` counts as a **decline**: not correct, not wrong.
- False refusal = a refusal on a `fact`/`explain` item.

## Report `runs/<name>/eval.json` (and console summary)

```json
{
  "trained_sample": {"n": 500, "accuracy": 0.99},
  "heldout_family": {"n": 1800, "accuracy": 0.88, "wrong_fact": 0.02, "by_type": {"O": 0.93, "...": 0}},
  "heldout_combo":  {"n": 600, "accuracy": 0.86, "wrong_fact": 0.03, "by_type": {}},
  "kurzarbeit":     {"n": 124, "accuracy": 0.82, "wrong_fact": 0.02, "by_kind": {}},
  "explain":        {"n": 46, "accuracy": 0.70},
  "refusal":        {"refusal_rate": 0.93, "false_refusal": 0.03},
  "facts": {"types": 26, "forms_min": 12, "records": 2534, "sha256": "..."},
  "thresholds": {"combo": 0.85, "family": 0.85, "kurzarbeit": 0.80, "wrong_fact_max": 0.03,
                 "refusal_min": 0.90, "false_refusal_max": 0.05}
}
```

`ut pipeline` exits non-zero (`FAILED: …`) when any threshold in `[eval]` is missed. These are the SC
values by default. The spec allows adjusting them after a first baseline run, recorded in measurements.md.
