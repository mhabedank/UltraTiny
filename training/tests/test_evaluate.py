from ultratiny.evaluate import is_correct, normalize, refusal_metrics

REF = "Das weiß ich leider nicht. Frag mich etwas zur Chemie!"


def _res(answer, expected):
    return {"answer": answer, "expected": expected, "correct": is_correct(answer, expected)}


def test_normalize_and_edit_rule():
    assert normalize("Hallo,  Welt!") == "hallo welt"
    assert is_correct("Gold hat das Symbol Au", "Gold hat das Symbol Au.")
    assert not is_correct("Gold hat das Symbol Ag.", "Silber hat das Symbol Ag. Gold Au.")


def test_refusal_metrics_split_and_rates():
    rows = [
        {"prompt": "Was ist ein Ion?", "expected": "Ein Ion ist ...", "relation": "frei"},
        {"prompt": "Wer ist Messi?", "expected": REF, "relation": "abweisen"},
        {"prompt": "asdf", "expected": REF, "relation": "abweisen"},
    ]
    heldout = {
        "results": [
            _res(REF, "Ein Ion ist ..."),  # chemistry wrongly refused
            _res(REF, REF),  # correct refusal
            _res("Gold ist ein Metall.", REF),  # missed refusal
        ]
    }
    demo = {"results": [_res("Au.", "Au."), _res("Ag.", "Ag.")]}
    m = refusal_metrics(demo, heldout, rows)
    assert m["n_refusal"] == 2 and m["refusal_rate"] == 0.5
    assert m["n_chem_heldout"] == 1 and m["chem_heldout"] == 0.0
    assert abs(m["false_refusal"] - 1 / 3) < 1e-9  # 1 of (2 demo + 1 chemistry held-out)


def test_refusal_metrics_absent_without_refusal_rows():
    rows = [{"prompt": "x", "expected": "y", "relation": "frei"}]
    assert refusal_metrics({"results": []}, {"results": [_res("y", "y")]}, rows) == {}
