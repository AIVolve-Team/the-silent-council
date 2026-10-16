"""Tests without a model: schemas, confidence, quotes, dissent and score."""

import math

import pytest
from engine import Generation, Step

from review import BENCHMARK
from review.confidence import level, p_yes
from review.council import Written, dissents
from review.quotes import check, found
from review.schemas import note_schema, verdict_schema
from review.scoring import agreement, score

CUAD = BENCHMARK["cuad"]
TRUE, FALSE = 1, 2


def step(text, p_true=None):
    observed = {} if p_true is None else {TRUE: math.log(p_true), FALSE: math.log(1 - p_true)}
    return Step(0, text, 0.0, [], observed)


def test_bounded_schemas_with_all_the_categories():
    note = note_schema(CUAD.of_role("finance"))
    assert note["properties"]["flag"]["required"] == [c.key for c in CUAD.of_role("finance")]
    assert note["properties"]["quotes"]["maxItems"] == 3
    verdict = verdict_schema(CUAD.categories)
    assert len(verdict["properties"]["flag"]["required"]) == 19
    assert verdict["required"][0] == "objections" and verdict["required"][-2] == "recommendation"


def test_benchmark_categories():
    assert [len(CUAD.of_role(r)) for r in CUAD.readers] == [7, 4, 8]
    assert BENCHMARK["contractnli"].readers == ("legal", "risk") and len(BENCHMARK["contractnli"].categories) == 17
    assert len(BENCHMARK["claudette"].categories) == 9
    assert BENCHMARK["demo"].categories == CUAD.categories


def test_confidence_from_the_booleans_inside_flag():
    steps = [step('{"flag": {"Exclusivity": '), step("true", 0.8), step(', "Non-Compete": ', 0.3)]
    steps += [step(" false", 0.1), step('}, "details": [{"category": "Exclusivity", "x": '), step("true", 0.99)]
    p = p_yes(Generation("", steps, 0), [TRUE], [FALSE])
    assert p == pytest.approx({"Exclusivity": 0.8, "Non-Compete": 0.1})
    assert level(0.95, True) == "high" and level(0.2, False) == "medium" and level(0.6, True) == "low"


def test_quotes_looked_up_in_the_contract():
    contract = "Il Cliente si impegna ad acquistare, in ciascun Anno Contrattuale, Componenti per € 180.000,00."
    assert found("si impegna ad acquistare, in ciascun Anno", contract)
    assert found("«Il cliente si impegna» … per € 180.000,00", contract)
    assert not found("se un terzo ottiene condizioni migliori", contract)
    assert not found("Cliente", contract)
    data = {"details": [{"category": "Minimum Commitment", "quote": "per € 180.000,00 di componenti"}]}
    assert check(data, contract) == {"Minimum Commitment": False}


def written(flag, p=None):
    return Written({"flag": flag}, p or {}, {}, 0, 0, "")


def test_major_and_minor_dissent():
    notes = {"risk": written({"Exclusivity": True, "Non-Compete": False}, {"Exclusivity": 0.95})}
    verdict = written({"Exclusivity": False, "Non-Compete": True}, {"Exclusivity": 0.4})
    by_category = {d.category: d for d in dissents(CUAD, notes, verdict)}
    assert by_category["Exclusivity"].type == "major" and by_category["Exclusivity"].expert_confidence == "high"
    assert by_category["Exclusivity"].verdict_confidence == "low"
    assert by_category["Non-Compete"].type == "minor" and by_category["Non-Compete"].expert_confidence is None


def test_score_with_the_always_yes_baseline():
    reviews = [
        {"contract": "a", "verdict": {"data": {"flag": {"x": True, "y": False}}}},
        {"contract": "b", "verdict": None},
    ]
    correct = {("a", "x"): True, ("a", "y"): True, ("b", "x"): False, ("b", "y"): True}
    s = score(reviews, correct)
    assert (s.tp, s.fp, s.fn, s.tn, s.invalid) == (1, 0, 2, 1, 2)
    assert round(s.f1, 1) == 50.0 and round(s.f1_always_yes, 1) == round(100 * 2 * 3 / 7, 1)


def test_score_of_the_notes_and_agreement_with_the_verdict():
    def note(flag):
        return {"data": None if flag is None else {"flag": flag}}

    reviews = [
        {
            "contract": "a",
            "notes": {"legal": note({"x": True}), "risk": note({"y": True})},
            "verdict": {"data": {"flag": {"x": False, "y": True}}},
        },
        # The finance note is not valid: its category counts as "no" and is not compared with the verdict.
        {
            "contract": "b",
            "notes": {"legal": note({"x": False}), "finance": note(None)},
            "verdict": {"data": {"flag": {"x": True, "y": True}}},
        },
    ]
    correct = {("a", "x"): True, ("a", "y"): True, ("b", "x"): False, ("b", "y"): True}
    s = score(reviews, correct, from_notes=True)
    assert (s.tp, s.fp, s.fn, s.tn, s.invalid) == (2, 0, 1, 1, 1)
    assert agreement(reviews) == (1, 3)
    assert agreement([{**reviews[0], "verdict": None}]) == (0, 0)


def test_token_limit_from_the_worst_case_of_the_schema():
    from review.schemas import max_tokens

    schema = {
        "type": "object",
        "properties": {
            "yes": {"type": "boolean"},
            "items": {"type": "array", "maxItems": 2, "items": {"type": "string", "maxLength": 10}},
            "outcome": {"enum": ["sign", "do not sign"]},
        },
    }
    # 2 braces + keys with quotes and colon + values in the worst case of one token per character
    assert max_tokens(schema) == 2 + (3 + 4 + 5) + (5 + 4 + 2 * 13 + 2) + (7 + 4 + 13)
    verdict = max_tokens(verdict_schema(CUAD.categories))
    assert verdict > 1100 and max_tokens(note_schema(CUAD.of_role("risk"))) > 300
