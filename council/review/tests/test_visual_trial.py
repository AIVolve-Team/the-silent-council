"""The telepathy-vs-text trial of the visual mode, offline: the scoring on canned server responses and the
request it sends, without a server."""

import importlib.util
import json
import sys
from pathlib import Path

import pytest

# Loaded from its file: the package __init__ imports the engine and torch, which the trial does not need.
_spec = importlib.util.spec_from_file_location("visual_trial", Path(__file__).parents[1] / "review" / "visual_trial.py")
trial = importlib.util.module_from_spec(_spec)
sys.modules["visual_trial"] = trial
_spec.loader.exec_module(trial)

PAGES = Path(__file__).parents[2] / "data" / "vision" / "pages"


def documents() -> dict[str, dict]:
    path = PAGES / "ground-truth.json"
    if not path.exists():
        pytest.skip(f"{path} not found")
    return {d["file"]: d for d in trial.probe.load_ground_truth(path)}


def check(question, *objects, answer="", known=True):
    return {"question": question, "answer": answer, "quote": "", "known": known, "objects": list(objects)}


def obj(page, type_, box=None, text=""):
    return {"page": page, "type": type_, "box_2d": box, "text": text}


# What the council might say about D's signature page: the drawn signature (twice, from two questions), the empty
# field, an invented stamp; it misses the tick and the logos.
D_RESPONSE = {
    "case_id": "c-1",
    "visual": {
        "complex": True,
        "route": "visual",
        "visual_mode": "on",
        "checks": [
            check("Who signed?", obj(3, "signature", [256, 168, 315, 500], "Shelby J. Butterfield")),
            check(
                "Is every signature block signed?",
                obj(3, "Signature", [258, 170, 318, 498]),  # the same signature, type in another case
                obj(3, "unsigned_signature_block", [450, 150, 498, 512]),
            ),
            check("Is there a stamp or seal?", obj(3, "stamp", [600, 400, 700, 560], "PAID")),
            check("Anything written by hand?", known=False),
        ],
    },
}


def test_ground_truth_types_are_the_probes_and_hidden_text_is_left_out():
    docs = documents()
    for doc in docs.values():
        assert {o["type"] for o in doc["objects"]} <= set(trial.probe.TYPES), doc["file"]
    d = docs["d-signals.pdf"]
    assert "hidden_text" not in {o["type"] for o in d["objects"]}
    assert sorted(o["type"] for o in d["objects"] if o["page"] == 3) == [
        "handwritten_note",
        "logo",
        "signature",
        "unsigned_signature_block",
    ]
    # Still listed in the file, for the detector's tests.
    raw = json.loads((PAGES / "ground-truth.json").read_text())["documents"]
    hidden = [o for doc in raw for o in doc["objects"] if o["type"] == "hidden_text"]
    assert len(hidden) == 1 and hidden[0]["visual"] is False


def test_repeated_objects_count_once():
    objects, repeats = trial.objects_of(D_RESPONSE)
    assert repeats == 1
    assert [(o["page"], o["type"]) for o in objects] == [
        (3, "signature"),
        (3, "unsigned_signature_block"),
        (3, "stamp"),
    ]


def test_two_signatures_far_apart_are_two_objects():
    response = {
        "visual": {
            "checks": [
                check("Who signed?", obj(6, "signature", [263, 186, 307, 376])),
                check("Who signed for Party B?", obj(6, "signature", [490, 182, 535, 373])),
            ]
        }
    }
    objects, repeats = trial.objects_of(response)
    assert len(objects) == 2 and repeats == 0


def test_score_of_d():
    row = trial.score_response(D_RESPONSE, documents()["d-signals.pdf"])
    assert row["checks"] == 4 and row["route"] == "visual" and row["visual_mode"] == "on"
    assert row["score"] == {
        "logo": {"missed": 3},
        "signature": {"found": 1},
        "handwritten_note": {"missed": 1},
        "unsigned_signature_block": {"found": 1},
        "stamp": {"invented": 1},
    }


def test_a_box_that_misses_the_mark_is_invented_and_the_mark_missed():
    response = {"visual": {"checks": [check("Who signed?", obj(3, "signature", [700, 600, 760, 900]))]}}
    score = trial.score_response(response, documents()["d-signals.pdf"])["score"]
    assert score["signature"] == {"missed": 1, "invented": 1}


def test_the_control_without_visual_scores_nothing():
    row = trial.score_response({"case_id": "c-2", "verdict": "ok"}, documents()["c-text-only.pdf"])
    assert row["checks"] == 0 and row["score"] == {} and row["route"] is None


def test_summary_per_mode():
    docs = documents()
    rows = []
    for mode, response in (("telepathy", D_RESPONSE), ("text", {"visual": {"checks": [], "visual_mode": "on"}})):
        rows.append({"file": "d-signals.pdf", "mode": mode, "expected_complex": True, "seconds": 40.0})
        rows[-1].update(trial.score_response(response, docs["d-signals.pdf"]))
    rows.append(
        {
            "file": "a-embedded-images.pdf",
            "mode": "text",
            "expected_complex": True,
            "checks": 0,
            "seconds": 1.0,
            "error": "HTTP 409: busy",
        }
    )
    summary = trial.summarize(rows)
    assert list(summary) == ["telepathy", "text"]
    tele, text = summary["telepathy"], summary["text"]
    assert tele["overall"] == {"found": 2, "missed": 4, "invented": 1, "precision": 0.667, "recall": 0.333}
    assert tele["per_type"]["signature"]["recall"] == 1.0
    assert text["overall"]["found"] == 0 and text["overall"]["missed"] == 6
    assert text["errors"] == 1 and text["without_checks"] == ["d-signals.pdf"]
    assert text["seconds_mean"] == 40.0  # the failed review does not count in the mean
    assert text["seconds_per_document"] == {"d-signals.pdf": 40.0, "a-embedded-images.pdf": 1.0}
    trial.print_summary(summary)  # prints without failing


def test_the_request_is_what_evolus_sends(monkeypatch):
    sent = {}

    class Reply:
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def read(self):
            return json.dumps(D_RESPONSE).encode()

    def urlopen(request, timeout):
        sent["url"], sent["timeout"] = request.full_url, timeout
        sent["headers"] = dict(request.header_items())
        sent["body"] = json.loads(request.data)
        return Reply()

    monkeypatch.setattr(trial.urllib.request, "urlopen", urlopen)
    response = trial.post_review("http://host:8000/", "s" * 32, b"%PDF-1.4", mode="text", subject="S", timeout=5)
    assert response == D_RESPONSE
    assert sent["url"] == "http://host:8000/review_contract" and sent["timeout"] == 5
    assert sent["headers"]["Authorization"] == "Bearer " + "s" * 32
    assert sent["body"]["pdf_base64"] == "JVBERi0xLjQ="
    assert sent["body"]["mode"] == "text" and sent["body"]["subject"] == "S"
    assert set(sent["body"]) == {"pdf_base64", "sender", "subject", "date", "mode"}


def test_main_without_the_secret_stops(monkeypatch):
    monkeypatch.delenv("COUNCIL_SECRET", raising=False)
    with pytest.raises(SystemExit, match="COUNCIL_SECRET"):
        trial.main(["--url", "http://localhost:1"])


def test_main_writes_a_row_per_document_and_mode(monkeypatch, tmp_path, capsys):
    monkeypatch.setenv("COUNCIL_SECRET", "s" * 32)
    calls = []

    def post_review(url, secret, pdf, *, mode, subject, timeout):
        calls.append((mode, subject))
        return D_RESPONSE if "d-signals" in subject else {"visual": {"checks": []}}

    monkeypatch.setattr(trial, "post_review", post_review)
    output = tmp_path / "trial.jsonl"
    trial.main(["--url", "http://localhost:1", "--pages-dir", str(PAGES), "--output", str(output)])
    rows = [json.loads(line) for line in output.read_text().splitlines()]
    assert [(r["mode"], r["file"]) for r in rows] == [(m, f) for m in trial.MODES for f in documents()]
    assert len(calls) == 8
    summary = json.loads(output.with_suffix(".summary.json").read_text())
    assert summary["telepathy"]["per_type"]["signature"]["found"] == 1
    assert "OVERALL" in capsys.readouterr().out
