import copy

from categories import CUAD_CATEGORIES
from demo import errors

TEXT = "Il Fornitore può recedere in qualsiasi momento con 30 giorni. Penale di € 2.500,00."


def valid_answer():
    rows = [
        {"category": c, "role": r, "should_flag": False, "quote": None, "rationale": None}
        for c, r in CUAD_CATEGORIES.items()
    ]
    for row in rows:
        if row["category"] == "Termination For Convenience":
            row.update(should_flag=True, quote="può recedere in qualsiasi momento", rationale="Recesso libero.")
    return {
        "status": "bozza",
        "recommendation": "negotiate",
        "rationale": "Recesso solo per il Fornitore.",
        "rows": rows,
        "expected_dissent": [
            {
                "category": "Termination For Convenience",
                "role": "risk",
                "expected_note": "yes",
                "expected_verdict": "no",
                "type": "major",
                "who_is_right": "expert",
                "why": "Il relatore potrebbe non vederlo.",
            }
        ],
        "amounts_and_dates": ["€ 2.500,00", "30 giorni"],
    }


def test_valid_answer():
    assert errors(valid_answer(), TEXT) == []


def test_quote_that_does_not_appear_in_the_contract():
    answer = valid_answer()
    next(r for r in answer["rows"] if r["should_flag"])["quote"] = "può recedere senza preavviso"
    assert errors(answer, TEXT) == ["Termination For Convenience: the quote does not appear in the contract"]


def test_wrong_amount():
    answer = valid_answer()
    answer["amounts_and_dates"] = ["€ 25.000,00"]
    assert errors(answer, TEXT) == ["amount or date that does not appear in the contract: '€ 25.000,00'"]


def test_dissent_with_wrong_who_is_right():
    answer = valid_answer()
    answer["expected_dissent"][0]["who_is_right"] = "verdict"
    assert len(errors(answer, TEXT)) == 1


def test_missing_categories():
    answer = copy.deepcopy(valid_answer())
    answer["rows"].pop()
    assert any("19 CUAD categories" in e for e in errors(answer, TEXT))
