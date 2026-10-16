"""Tests without a model of the eval: metrics, vote among 4, protection of the test and report."""

import argparse
import json

import pytest

from review import eval as evaluation
from review import metrics
from review.configurations import common_recommendation, vote_among
from review.council import MAX_ANALYSIS_TOKENS as MAX
from review.council import Written
from review.data import REPLICATION, correct_answers

EVIDENCE = "The Company shall not, during the Term, engage in any business that competes with the Distributor."


def row(contract, flag, *, details=(), p=None, tokens=(100, 10), seconds=1.0, dissents=(), notes=None):
    data = {"flag": flag, "details": list(details), "recommendation": "negotiate", "rationale": ""}
    return {
        "contract": contract,
        "verdict": {"data": data, "p_yes": p or {}},
        "notes": notes or {},
        "dissents": list(dissents),
        "tokens_read": tokens[0],
        "tokens_generated": tokens[1],
        "seconds": seconds,
    }


def test_overlap_with_the_annotated_span():
    assert metrics.overlaps("«engage in any business that competes» with others", [EVIDENCE])
    assert metrics.overlaps("shall not, during the", [EVIDENCE])  # short but entirely inside
    assert not metrics.overlaps("the Term", [EVIDENCE])  # fewer than 3 words
    assert not metrics.overlaps("the Distributor may terminate this Agreement", [EVIDENCE])


def test_strict_version_counts_the_yes_only_with_the_right_quote():
    correct = {("a", "x"): True, ("a", "y"): True, ("a", "z"): False}
    evidence = {("a", "x"): [EVIDENCE], ("a", "y"): [EVIDENCE], ("a", "z"): []}
    details = [
        {"category": "x", "quote": "engage in any business that competes"},
        {"category": "y", "quote": "a sentence that has nothing to do with it"},
    ]
    r = row("a", {"x": True, "y": True, "z": True}, details=details)
    strict = metrics.strict_score([r], correct, evidence)
    assert (strict.tp, strict.fp, strict.fn) == (1, 1, 1)
    main = metrics.score([r], correct)
    assert (main.tp, main.fp, main.fn) == (2, 1, 0)


def test_paired_bootstrap():
    correct = {(c, "x"): True for c in "abcdef"} | {(c, "y"): False for c in "abcdef"}
    all_right = [row(c, {"x": True, "y": False}) for c in "abcdef"]
    half = [row(c, {"x": c in "abc", "y": False}) for c in "abcdef"]
    same = metrics.paired_bootstrap(all_right, all_right, correct, repetitions=200)
    assert (same.difference, same.low, same.high) == (0.0, 0.0, 0.0) and same.shown
    better = metrics.paired_bootstrap(all_right, half, correct, repetitions=200)
    assert better.difference == pytest.approx(100 - 100 * 2 * 3 / 9)
    assert better.low >= 0 and better == metrics.paired_bootstrap(all_right, half, correct, repetitions=200)


def test_metrics_without_threshold():
    correct = {("a", "x"): True, ("a", "y"): False, ("a", "z"): True}
    dissents = [{"category": "x", "type": "major"}, {"category": "y", "type": "minor"}]
    r = row("a", {"x": True, "y": True, "z": False}, p={"x": 0.95, "y": 0.8, "z": 0.4}, dissents=dissents)
    assert metrics.who_is_right([r], correct) == {"major": (1, 1), "minor": (0, 1)}
    assert metrics.calibration([r], correct) == {"high": (1, 1), "medium": (0, 1), "low": (0, 1)}
    contract = "Il Cliente paga € 180.000,00 entro il 31/12/2026."
    details = [{"category": "x", "quote": "paga € 180.000,00", "rationale": "and another 5.000 euro on 1/1/2027"}]
    assert metrics.amounts_and_dates(row("a", {}, details=details), contract) == (3, 2)


def test_g4_and_sentence_on_the_thoughts():
    correct = {("a", "x"): True}
    tele = [row("a", {"x": True}, tokens=(50, 40), seconds=10)]
    text = [row("a", {"x": True}, tokens=(100, 100), seconds=20)]
    assert metrics.g4(tele, text, correct) == {"f1": True, "tokens": True, "time": True}
    assert metrics.g4(text, tele, correct) == {"f1": True, "tokens": False, "time": False}
    assert metrics.thoughts_help(60, 57, 59) is True
    assert metrics.thoughts_help(60, 59, 59) is False
    assert metrics.thoughts_help(60, None, 59) is None


def written(flag, p):
    return Written({"flag": flag}, p, {}, 0, 0, "")


def test_vote_among_four_with_a_tie():
    votes = {
        "a": written({"x": True, "y": True, "z": True}, {"x": 0.9, "y": 0.6, "z": 0.75}),
        "b": written({"x": True, "y": True, "z": True}, {"x": 0.9, "y": 0.6, "z": 0.75}),
        "c": written({"x": False, "y": False, "z": False}, {"x": 0.2, "y": 0.1, "z": 0.25}),
        "d": written({"x": True, "y": False, "z": False}, {"x": 0.9, "y": 0.1, "z": 0.25}),
        "broken": Written(None, {}, {}, 0, 0, ""),
    }
    flag, p = vote_among(votes, ["x", "y", "z"])
    # x: 3 to 1. y: 2 to 2, the no is surer (0.9 against 0.6). z: 2 to 2 at equal confidence (0.75): yes wins.
    assert flag == {"x": True, "y": False, "z": True}
    assert p["x"] == pytest.approx(0.725)
    assert common_recommendation(["sign", "negotiate"]) == "negotiate"
    assert common_recommendation(["sign", "sign", "do not sign"]) == "sign"
    assert common_recommendation([]) is None


def test_the_test_does_not_start_with_the_draft(tmp_path, monkeypatch):
    draft = tmp_path / "PREREGISTRATION.md"
    draft.write_text(f"# Pre-registration\n\n{evaluation.DRAFT}\n")
    monkeypatch.setattr(evaluation, "PREREGISTRATION", draft)
    with pytest.raises(SystemExit, match="draft"):
        evaluation.check_preregistration()


def test_report_on_cuad_dev(tmp_path):
    correct = correct_answers("cuad", "dev")
    contracts = sorted({c for c, _ in correct})
    perfect = [row(c, {k: v for (cc, k), v in correct.items() if cc == c}, tokens=(500, 100)) for c in contracts]
    all_no = [row(c, {k: False for (cc, k) in correct if cc == c}, tokens=(1000, 300), seconds=2) for c in contracts]
    for name, rows in {"telepathy": perfect, "text": all_no, "m0": all_no}.items():
        (tmp_path / f"cuad-dev-{name}.jsonl").write_text("\n".join(json.dumps(r) for r in rows))
    text = evaluation.write_report(tmp_path)
    numbers = json.loads((tmp_path / "numbers.json").read_text())["cuad-dev"]
    assert numbers["configurations"]["telepathy"]["f1"] == 100.0 and numbers["configurations"]["text"]["f1"] == 0.0
    assert numbers["telepathy_vs_text"]["shown"] and numbers["sabotages"]["m0"] == -100.0
    assert "[x] telepathy F1" in text and "Zeroed thoughts" in text
    assert (tmp_path / "chart-cuad-dev.svg").read_text().startswith("<svg")


def test_report_with_0_steps_no_tests_on_the_thoughts(tmp_path):
    # With 0 latent steps there are no thoughts: the sentence for the jury talks about memory (PREREGISTRATION.md).
    correct = correct_answers("cuad", "dev")
    contracts = sorted({c for c, _ in correct})
    perfect = [row(c, {k: v for (cc, k), v in correct.items() if cc == c}) for c in contracts]
    all_no = [row(c, {k: False for (cc, k) in correct if cc == c}) for c in contracts]
    for name, rows in {"telepathy": perfect, "text": all_no, "swapped-contract": all_no}.items():
        (tmp_path / f"cuad-dev-{name}.jsonl").write_text("\n".join(json.dumps(r) for r in rows))
    (tmp_path / "eval-cuad-dev.json").write_text(json.dumps({"steps": 0, "realign": False}))
    text = evaluation.write_report(tmp_path)
    assert "The agents hand each other the memory of what they read." in text
    assert "hand each other their thoughts" not in text and "Zeroed thoughts" not in text
    assert "realignment off" in text


def test_choice_of_the_steps_and_proposed_thresholds():
    from review.calibration import choose_steps, propose_thresholds

    assert choose_steps({0: 60.0, 10: 61.5, 20: 62.6, 40: 63.0}) == 20  # thoughts help: 20 and 40 within 1 point
    assert choose_steps({10: 61.5, 20: 62.0, 40: 62.4}) == 10  # under 1 point the value with fewer steps wins
    assert choose_steps({0: 68.8, 10: 56.2, 20: 60.0, 40: 69.5}) == 0  # thoughts do not help: it is corrected
    items = [(0.99, True)] * 9 + [(0.95, False)] + [(0.75, True)] * 7 + [(0.72, False)] * 3 + [(0.55, False)] * 5
    assert propose_thresholds(items) == (0.8, 0.6)  # above 0.8: 9 right out of 10; between 0.6 and 0.8: 7 out of 10
    assert propose_thresholds([(0.99, False)]) is None


def test_report_telepathy_against_solo_and_truncated_analyses(tmp_path):
    # The comparison that isolates the channel is with the solo agent, and the report counts the text analyses that
    # hit the cap.
    correct = correct_answers("cuad", "dev")
    contracts = sorted({c for c, _ in correct})
    perfect = [row(c, {k: v for (cc, k), v in correct.items() if cc == c}) for c in contracts]
    all_no = [row(c, {k: False for (cc, k) in correct if cc == c}) for c in contracts]
    in_text = [r | {"analyses": {"legal": MAX, "finance": 300, "risk": MAX - 1}} for r in all_no]
    for name, rows in {"telepathy": perfect, "text": in_text, "solo": perfect}.items():
        (tmp_path / f"cuad-dev-{name}.jsonl").write_text("\n".join(json.dumps(r) for r in rows))
    text = evaluation.write_report(tmp_path)
    numbers = json.loads((tmp_path / "numbers.json").read_text())["cuad-dev"]
    assert numbers["telepathy_vs_solo"]["difference"] == 0.0
    assert numbers["configurations"]["text"]["truncated_analyses"] == len(contracts)
    assert numbers["configurations"]["text"]["analyses"] == 3 * len(contracts)
    assert "Telepathy F1 minus solo agent F1" in text
    assert f"cap of {MAX} tokens:** {len(contracts)} of {3 * len(contracts)}" in text


def test_the_shown_judgement_only_on_cuad(tmp_path):
    # PREREGISTRATION.md: ContractNLI and CLAUDETTE are reported without a threshold.
    correct = correct_answers("contractnli", "dev")
    contracts = sorted({c for c, _ in correct})
    perfect = [row(c, {k: v for (cc, k), v in correct.items() if cc == c}) for c in contracts]
    for name in ("telepathy", "text"):
        (tmp_path / f"contractnli-dev-{name}.jsonl").write_text("\n".join(json.dumps(r) for r in perfect))
    text = evaluation.write_report(tmp_path)
    assert "shown" not in text and "Without a threshold" in text


# --- CUAD replication ---------------------------------------------------------------------------------------


def test_the_replication_does_not_start_without_its_section(tmp_path, monkeypatch):
    frozen = tmp_path / "PREREGISTRATION.md"
    frozen.write_text("# Pre-registration\n\nStatus: frozen on 13/10/2026\n")
    monkeypatch.setattr(evaluation, "PREREGISTRATION", frozen)
    with pytest.raises(SystemExit, match="Replication on CUAD"):
        evaluation.check_preregistration(REPLICATION)


def test_the_replication_reruns_only_its_three_configurations(tmp_path):
    args = argparse.Namespace(output=tmp_path, configurations=list(evaluation.ORDER), steps=0, subset=REPLICATION)
    with pytest.raises(SystemExit, match="replication reruns only"):
        evaluation.run(args)


def test_the_replication_has_the_72_contracts_and_their_answers():
    correct = correct_answers("cuad", REPLICATION)
    replication = {c for c, _ in correct}
    assert len(replication) == 72 and not replication & {c for c, _ in correct_answers("cuad", "test")}


def _cuad_runs(folder, subset, telepathy_right):
    correct = correct_answers("cuad", subset)
    contracts = sorted({c for c, _ in correct})
    perfect = [row(c, {k: v for (cc, k), v in correct.items() if cc == c}, tokens=(500, 100)) for c in contracts]
    all_no = [row(c, {k: False for (cc, k) in correct if cc == c}, tokens=(1000, 300), seconds=2) for c in contracts]
    runs = {"telepathy": perfect if telepathy_right else all_no, "text": all_no, "solo": perfect}
    for name, rows in runs.items():
        (folder / f"cuad-{subset}-{name}.jsonl").write_text("\n".join(json.dumps(r) for r in rows))
    return len(contracts)


def test_report_with_test_replication_and_total(tmp_path):
    n_test = _cuad_runs(tmp_path, "test", telepathy_right=True)
    n_replication = _cuad_runs(tmp_path, REPLICATION, telepathy_right=True)
    text = evaluation.write_report(tmp_path)
    numbers = json.loads((tmp_path / "numbers.json").read_text())
    assert set(numbers) == {"cuad-test", "cuad-replication", "cuad-total"}
    total = numbers["cuad-total"]
    assert total["telepathy_vs_text"]["contracts"] == n_test + n_replication == 92
    assert total["telepathy_vs_solo"]["contracts"] == 92
    assert "## cuad, total (92 contracts)" in text and "G4 on the replication" in text
    assert "The replication **confirms** it" in text


def test_the_replication_refutes_g4(tmp_path):
    _cuad_runs(tmp_path, "test", telepathy_right=True)
    _cuad_runs(tmp_path, REPLICATION, telepathy_right=False)
    text = evaluation.write_report(tmp_path)
    assert "where it is passed. The replication **refutes** it" in text
    # On the replication and the total the "shown" judgement is not given: G4 is decided on the test.
    replication_and_total = (
        text.split("## cuad, replication")[1].split("## cuad, test")[0] + text.split("## cuad, total")[1]
    )
    assert "shown" not in replication_and_total and "compatible" not in replication_and_total
