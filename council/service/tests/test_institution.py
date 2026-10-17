import json

import pytest

from reviewer.institution import Institution, Memory, lessons_text
from reviewer.manager import Rejected, Reviewer

from .conftest import CONTRACT, EXAMPLE, LINK, SECRET
from .test_manager import email

PLAYBOOK = "CONTRACT PLAYBOOK. Never sign uncapped liability on our side."


def institution_of(tmp_path) -> Institution:
    (tmp_path / "playbook.md").write_text(PLAYBOOK + "\n")
    return Institution(tmp_path / "playbook.md", tmp_path / "institution")


def test_the_persons_choices_become_precedents_once(council, tmp_path):
    institution = institution_of(tmp_path)
    reviewer = Reviewer(council, tmp_path / "cases", secret=SECRET, link=LINK, institution=institution)
    case_id = reviewer.review_contract(None, CONTRACT, **email())["case_id"]
    first = institution.version()
    assert institution.texts() == [PLAYBOOK]

    dissent = EXAMPLE["dissents"][0]
    recorded = reviewer.record_choices(case_id, {dissent["category"]: "expert"}, "Ash")
    assert recorded["precedents_added"] == 1
    (precedent,) = institution.precedents()
    assert precedent["category"] == dissent["category"] and precedent["who"] == "Ash"
    # the person sided with the expert: the clause is flagged as the expert said
    assert precedent["flag"] == (dissent["type"] == "major")
    assert institution.version() != first and len(institution.texts()) == 2
    assert dissent["category"] in institution.texts()[1]

    again = reviewer.record_choices(case_id, {dissent["category"]: "verdict"}, "Ash")
    assert again["precedents_added"] == 0 and len(institution.precedents()) == 1


def test_a_lesson_has_both_sides_and_the_persons_why():
    p = {"who": "Ash", "when": "2026-10-17T15:00:00", "title": "Supply", "category": "Non-Compete", "expert": "risk"}
    p |= {"expert_quote": "shall not compete", "verdict_quote": None, "verdict_rationale": None}
    with_expert = p | {"flag": True, "sided_with": "expert", "reason": "a two-year ban on competing is a non-compete"}
    with_verdict = p | {"flag": False, "sided_with": "verdict", "reason": None, "case_id": "other"}
    text = lessons_text([with_expert, with_verdict])
    assert text.count('LESSONS ON "Non-Compete"') == 1  # grouped by category
    assert "The verdict said: do not flag it." in text
    assert 'The risk expert said: flag it, on "shall not compete".' in text
    assert "The person sided with the risk expert." in text and "Why: a two-year ban" in text
    assert "The person sided with the verdict." in text and text.count("Why:") == 1


def test_the_persons_reason_goes_into_the_precedent(council, tmp_path):
    institution = institution_of(tmp_path)
    reviewer = Reviewer(council, tmp_path / "cases", secret=SECRET, link=LINK, institution=institution)
    case_id = reviewer.review_contract(None, CONTRACT, **email())["case_id"]
    category = EXAMPLE["dissents"][0]["category"]
    with pytest.raises(Rejected, match="no choice"):
        reviewer.record_choices(case_id, {category: "expert"}, "Ash", {"Invented": "why"})
    recorded = reviewer.record_choices(case_id, {category: "expert"}, "Ash", {category: " the cap is in 8.2 "})
    assert recorded["reasons"] == {category: "the cap is in 8.2"}
    assert institution.precedents()[0]["reason"] == "the cap is in 8.2"
    assert "Why: the cap is in 8.2" in institution.texts()[1]


def test_without_the_institution_the_choices_are_only_recorded(reviewer):
    case_id = reviewer.review_contract(None, CONTRACT, **email())["case_id"]
    recorded = reviewer.record_choices(case_id, {EXAMPLE["dissents"][0]["category"]: "expert"}, "Ash")
    assert "precedents_added" not in recorded


class FakeEngine:
    def __init__(self) -> None:
        self.read: list[tuple[str, int, str, bool]] = []

    def think(self, agent, text, received, *, session, latent_steps, base):
        self.read.append((text, len(received), session, base))
        return {"text": text}


def test_the_memory_is_read_once_per_version(council, tmp_path):
    institution = institution_of(tmp_path)
    engine = FakeEngine()
    memory = Memory(institution, engine)
    version, base = memory.current()
    assert memory.current() == (version, base) and len(engine.read) == 1
    assert engine.read[0] == (PLAYBOOK, 0, f"institution/{version}", True)

    reviewer = Reviewer(council, tmp_path / "cases", secret=SECRET, link=LINK, institution=institution)
    case_id = reviewer.review_contract(None, CONTRACT, **email())["case_id"]
    reviewer.record_choices(case_id, {EXAMPLE["dissents"][0]["category"]: "expert"}, "Ash")
    new_version, new_base = memory.current()
    assert new_version != version and len(new_base) == 2
    # the precedents are read on top of the playbook, in the new version's session
    assert [r[1:3] for r in engine.read[1:]] == [(0, f"institution/{new_version}"), (1, f"institution/{new_version}")]


def test_the_response_says_which_memory_the_review_started_from(council, tmp_path):
    memory = {"version": "abc", "precedents": 2, "base_fingerprints": ["f1", "f2"]}

    def with_memory(*args, **options):
        return council(*args, **options) | {"institution": memory}

    reviewer = Reviewer(with_memory, tmp_path / "cases", secret=SECRET, link=LINK)
    response = reviewer.review_contract(None, CONTRACT, **email())
    assert response["institution"] == memory
    assert json.loads((tmp_path / "cases" / response["case_id"] / "response.json").read_text())["institution"]


def test_a_wrong_row_without_a_dissent_and_an_instruction_become_lessons(council, tmp_path):
    institution = institution_of(tmp_path)
    reviewer = Reviewer(council, tmp_path / "cases", secret=SECRET, link=LINK, institution=institution)
    case_id = reviewer.review_contract(None, CONTRACT, **email())["case_id"]
    in_dissent = {d["category"] for d in EXAMPLE["dissents"]}
    rows = {r["key"]: r for r in reviewer.case(case_id)["view"]["rows"]}
    calm = next(k for k, r in rows.items() if k not in in_dissent and r["flag"] is True)

    with pytest.raises(Rejected, match="without a dissent"):
        reviewer.record_choices(case_id, None, "Ash", corrections={next(iter(in_dissent)): False})
    with pytest.raises(Rejected, match="true .flag it. or false"):
        reviewer.record_choices(case_id, None, "Ash", corrections={calm: "no"})
    with pytest.raises(Rejected, match="expert or verdict is required"):
        reviewer.record_choices(case_id, None, "Ash", instruction="  ")

    rule = "A non-compete longer than 12 months is always flagged for us."
    recorded = reviewer.record_choices(
        case_id, None, "Ash", {calm: "it is a template clause"}, corrections={calm: False}, instruction=rule
    )
    assert recorded["recorded"] == 2 and recorded["precedents_added"] == 2
    correction, instruction = institution.precedents()
    assert correction["kind"] == "correction" and correction["flag"] is False and correction["sided_with"] == "person"
    assert instruction == instruction | {"kind": "instruction", "text": rule, "who": "Ash"}
    text = institution.texts()[1]
    assert text.index("INSTRUCTIONS") < text.index(f'LESSONS ON "{calm}"')
    assert f"- {rule} (written by Ash" in text
    assert "The verdict said: flag it" in text and "The person corrected it." in text
    assert "Why: it is a template clause" in text

    again = reviewer.record_choices(case_id, None, "Ash", corrections={calm: False}, instruction=rule)
    assert again["precedents_added"] == 0 and len(institution.precedents()) == 2
