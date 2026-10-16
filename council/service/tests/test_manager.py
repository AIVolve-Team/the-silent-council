import json

import pytest

from reviewer.manager import Busy, Rejected, case_key

from .conftest import CATALOG, CONTRACT, EXAMPLE, SECRET, email, pdf_with_text


def test_a_contract_becomes_a_case_with_page_link_and_notice(reviewer, council):
    r = reviewer.review_contract(None, CONTRACT, **email())
    assert r["case_id"].startswith("council-") and r["verdict"] and r["seal_intact"]
    assert r["recommendation"]["value"] == EXAMPLE["verdict"]["data"]["recommendation"]
    assert r["link"] == f"https://council.example.org/verdict/{r['case_id']}?key={case_key(SECRET, r['case_id'])}"
    assert r["notice"]["subject"].startswith("[Consiglio] Contratto di fornitura:") and r["link"] in r["notice"]["text"]
    major = [d for d in EXAMPLE["dissents"] if d["type"] == "major"]
    assert len(r["major_dissents"]) == len(major)
    folder = reviewer.cases / r["case_id"]
    assert {f.name for f in folder.iterdir()} == {
        "review.json",
        "view.json",
        "page.html",
        "email.json",
        "response.json",
    }
    # The contract's text is not saved.
    assert all(CONTRACT.strip() not in f.read_text() for f in folder.iterdir())
    assert council.calls == [(r["case_id"], CONTRACT, "telepathy", "demo")]


def test_the_notice_speaks_italian_to_the_business(reviewer):
    r = reviewer.review_contract(None, CONTRACT, **email())
    italian = {"sign": "firmare", "negotiate": "negoziare", "do not sign": "non firmare"}
    assert f"Raccomandazione: {italian[r['recommendation']['value']]}." in r["notice"]["text"]


def test_the_same_email_is_the_same_case_and_the_council_does_not_run_again(reviewer, council):
    first = reviewer.review_contract(None, CONTRACT, **email())
    second = reviewer.review_contract(None, CONTRACT, **email())
    as_text = reviewer.review_contract(None, CONTRACT, **email(), mode="text")
    assert first == second and as_text["case_id"] != first["case_id"]
    assert len(council.calls) == 2


def test_the_contract_as_pdf(reviewer, council):
    reviewer.review_contract(pdf_with_text("Il Fornitore fornisce componenti"), None, **email())
    assert "Il Fornitore fornisce componenti" in council.calls[0][1]
    with pytest.raises(Rejected, match="PDF"):
        reviewer.review_contract(b"not a pdf", None, **email())
    with pytest.raises(Rejected, match="scan"):
        reviewer.review_contract(pdf_with_text(""), None, **email())


@pytest.mark.parametrize(
    ("contract", "text", "other", "reason"),
    [
        (None, None, {}, "only one"),
        (b"%PDF-", CONTRACT, {}, "only one"),
        (None, CONTRACT, {"mode": "voice"}, "mode"),
        (None, CONTRACT, {"sender": " "}, "sender"),
        (None, "x" * 200_001, {}, "contract"),
    ],
)
def test_bad_requests_do_not_touch_the_council(reviewer, council, contract, text, other, reason):
    with pytest.raises(Rejected, match=reason):
        reviewer.review_contract(contract, text, **(email() | other))
    assert council.calls == []


def test_without_a_seal_no_verdict_and_the_notice_asks_for_a_person(reviewer, council):
    council.stopped = {"check": "chain", "reason": "different previous hash"}
    r = reviewer.review_contract(None, CONTRACT, **email())
    assert not r["verdict"] and not r["seal_intact"] and r["recommendation"] is None
    assert "serve una persona" in r["notice"]["subject"]


def test_the_persons_choices(reviewer):
    case_id = reviewer.review_contract(None, CONTRACT, **email())["case_id"]
    in_dissent = sorted({d["category"] for d in EXAMPLE["dissents"]})
    choices = {in_dissent[0]: "expert"}
    recorded = reviewer.record_choices(case_id, choices, "Ash")
    assert recorded["recorded"] == 1 and reviewer.case(case_id)["choices"][0]["choices"] == choices
    with pytest.raises(Rejected, match="not in dissent"):
        reviewer.record_choices(case_id, {"Invented Category": "expert"}, "Ash")
    with pytest.raises(Rejected, match="expert or verdict"):
        reviewer.record_choices(case_id, {in_dissent[0]: "maybe"}, "Ash")
    with pytest.raises(Rejected, match="who"):
        reviewer.record_choices(case_id, choices, "")
    with pytest.raises(Rejected, match="not the id"):
        reviewer.record_choices("../../etc", choices, "Ash")
    listing = reviewer.listing()
    assert listing[0]["case_id"] == case_id and listing[0]["choices"] == 1


def test_the_page_knows_where_to_send_the_choices(reviewer):
    case_id = reviewer.review_contract(None, CONTRACT, **email())["case_id"]
    view = json.loads((reviewer.cases / case_id / "view.json").read_text())
    assert view["choices_url"] == f"/verdict/{case_id}/choices?key={case_key(SECRET, case_id)}"
    assert view["choices_url"] in reviewer.page_of(case_id)


def test_the_live_review_is_a_new_case_with_the_comparison(live, council):
    key = next(iter(CATALOG))
    first = live.live_review(key)
    second = live.live_review(key)
    assert first["case_id"] != second["case_id"]  # the judge sees the council at work, even on the same contract
    assert council.calls[0][1] == CATALOG[key]["text"] and council.calls[0][3] == "cuad"
    v = first["view"]
    assert v["language"] == "en" and v["live"] and v["title"] == CATALOG[key]["title"]
    cap = next(r for r in v["rows"] if r["key"] == "Cap On Liability")
    assert cap["experts"]["should_flag"] is True and v["comparison"]["name"] == "CUAD"
    assert live.case(first["case_id"])["view"] == v
    assert {c["case_id"] for c in live.listing()} == {first["case_id"], second["case_id"]}


def test_the_live_review_rejects_and_does_not_wait(live, reviewer, council):
    with pytest.raises(Rejected, match="off"):
        reviewer.live_review(next(iter(CATALOG)))
    with pytest.raises(Rejected, match="not one of"):
        live.live_review("cuad:../../etc/passwd")
    with pytest.raises(Rejected, match="mode"):
        live.live_review(next(iter(CATALOG)), "shout")
    with live.lock, pytest.raises(Busy):
        live.live_review(next(iter(CATALOG)))
    assert council.calls == []
