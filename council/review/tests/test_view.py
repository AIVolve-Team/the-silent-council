"""The view for the verdict page and the rules of “Verdict and dissent”, without a model."""

import copy
import hashlib
import json
from pathlib import Path

from review import BENCHMARK
from review.view import PAGE, page, position, view, visual_section

EXAMPLE = Path(__file__).parents[1] / "page" / "example-review.json"
# The example is an Italian demo-style contract, so its title is Italian.
TITLE = "Contratto di fornitura di componenti (esempio)"


def review():
    return json.loads(EXAMPLE.read_text())


def test_rows_recommendation_and_seal():
    v = view(review(), BENCHMARK["demo"], TITLE)
    assert len(v["rows"]) == 19 and [n["role"] for n in v["notes"]] == ["legal", "finance", "risk"]
    assert v["recommendation"]["value"] == "negotiate"
    assert v["seal"] == {
        "intact": True,
        "messages": 3,
        "fingerprints": review()["fingerprints"],
        "check": None,
        "reason": None,
    }
    cap = next(r for r in v["rows"] if r["key"] == "Cap On Liability")
    assert cap["flag"] is True and cap["quote_found"] is True and cap["confidence"] == "high"
    assignment = next(r for r in v["rows"] if r["key"] == "Anti-Assignment")
    assert assignment["quote_found"] is False


def test_the_latent_steps_in_the_view():
    v = view(review(), BENCHMARK["demo"], TITLE)
    assert v["latent_steps"] == 10
    without = {k: x for k, x in review().items() if k != "latent_steps"}
    assert view(without, BENCHMARK["demo"], TITLE)["latent_steps"] is None


def test_major_dissent_with_a_confident_expert_highlighted():
    rows = {r["key"]: r for r in view(review(), BENCHMARK["demo"], TITLE)["rows"]}
    major = rows["Change Of Control"]["dissent"]
    assert major["type"] == "major" and major["highlighted"] is True and major["expert_says"] is True
    assert major["expert_quote"].startswith("Se il controllo del Cliente")
    minor = rows["Most Favored Nation"]["dissent"]
    assert minor["type"] == "minor" and minor["highlighted"] is False
    assert all(r["dissent"] is None for k, r in rows.items() if k not in ("Change Of Control", "Most Favored Nation"))


def test_stopped_chain_no_verdict():
    stopped = copy.deepcopy(review())
    stopped["verdict"] = None
    stopped["dissents"] = []
    stopped["stopped"] = {"passed": False, "check": "seal", "reason": "invalid signature for finance"}
    v = view(stopped, BENCHMARK["demo"], TITLE)
    assert v["recommendation"] is None and v["seal"]["intact"] is False
    assert v["seal"]["reason"] == "invalid signature for finance"


def test_page_with_the_data_inside_without_closing_the_script():
    v = view(review(), BENCHMARK["demo"], TITLE)
    v["title"] = "Trial </script><script>alert(1)</script>"
    html = page(v)
    inside = html.split('<script id="data" type="application/json">', 1)[1].split("</script>", 1)[0]
    assert json.loads(inside)["title"] == v["title"]
    assert PAGE.read_text().count('<script id="data"') == 1


def test_the_example_page_is_up_to_date():
    expected = page(view(review(), BENCHMARK["demo"], TITLE))
    assert (EXAMPLE.parent / "example.html").read_text() == expected, "regenerate page/example.html (see README)"


def test_next_to_each_row_the_experts_answer():
    # On the judges' site: where the council agrees with the dataset's experts and where it is wrong.
    experts = {
        "Cap On Liability": {"should_flag": True, "evidence": ["x" * 500]},
        "Anti-Assignment": {"should_flag": False, "evidence": []},
    }
    source = {"name": "CUAD", "who": "the CUAD experts", "link": "https://example.org", "explanation": "…"}
    v = view(review(), BENCHMARK["demo"], TITLE, experts=experts, source=source)
    rows = {r["key"]: r for r in v["rows"]}
    cap, assignment = rows["Cap On Liability"]["experts"], rows["Anti-Assignment"]["experts"]
    assert cap["agrees"] is True and cap["evidence"][0].endswith("…") and len(cap["evidence"][0]) < 500
    assert rows["Anti-Assignment"]["flag"] is True and assignment["agrees"] is False
    assert rows["Uncapped Liability"]["experts"] is None
    assert v["comparison"] == source | {"agreed": 1, "compared": 2, "found": 1, "to_find": 1}


def test_the_client_business_does_not_see_the_comparison():
    v = view(review(), BENCHMARK["demo"], TITLE)
    assert v["comparison"] is None and all(r["experts"] is None for r in v["rows"])


# --- The visual checks ---

# The page of the example before the visual checks, with the corrections and the instruction of without "visual"
# the page stays byte for byte the same.
EXAMPLE_SHA256 = "6d59278b67a6bbf0de6472a3d880dd2103b96880cc20804c499ddfa1db72b694"


def visual():
    return {
        "complex": True,
        "signals": [
            {"page": 6, "kind": "signature_field", "detail": "Buyer"},
            {"page": 6, "kind": "drawing", "detail": "212 curve segments"},
            {"page": 2, "kind": "scanned", "detail": "no text layer"},
            {"page": 3, "kind": "hidden_text", "detail": "white text"},
        ],
        "visual_pages": [2, 6],
        "route": "visual",
        "hidden_text_removed": True,
        "visual_mode": "on",
        "skill_sections": ["signatures", "handwriting", "scans"],
        "checks": [
            {
                "question": "Is the contract signed by both parties?",
                "answer": {
                    "answer": "Only the supplier signed.",
                    "objects": [
                        {"page": 6, "type": "signature", "box_2d": [820, 100, 880, 300], "text": "M. Rossi"},
                        {"page": 6, "type": "unsigned_signature_block", "box_2d": [820, 600, 880, 900], "text": ""},
                    ],
                    "known": True,
                },
                "known": True,
            },
            {"question": "Was any amount changed by hand?", "answer": None, "known": False},
        ],
    }


def visual_view(**changes):
    v = view(review(), BENCHMARK["demo"], TITLE)
    v["visual"] = visual() | changes
    return v


def test_without_visual_the_page_is_unchanged():
    v = view(review(), BENCHMARK["demo"], TITLE)
    assert hashlib.sha256(page(v).encode()).hexdigest() == EXAMPLE_SHA256
    assert 'id="visual"' not in page(v) and "visual-checks" not in page(v)
    # A simple PDF has nothing to show either: only its data, as for any other key of the view.
    simple = {"complex": False, "signals": [], "visual_pages": [], "route": "text"}
    for x in (None, simple):
        html = page(v | {"visual": x})
        assert 'id="visual"' not in html and "visual-checks" not in html


def test_the_data_cannot_open_a_comment_in_its_script():
    # "<!--" followed by "<script" would make the parser swallow the rest of the page; only such data changes bytes.
    v = view(review(), BENCHMARK["demo"], "Trial <!--<script>")
    inside = page(v).split('<script id="data" type="application/json">', 1)[1].split("</script>", 1)[0]
    assert "<!--" not in inside and json.loads(inside)["title"] == "Trial <!--<script>"


def test_the_position_in_words():
    assert position(6, [820, 100, 880, 300], "en") == "page 6, bottom left"
    assert position(6, [820, 100, 880, 300], "it") == "pagina 6, in basso a sinistra"
    assert position(1, [0, 400, 100, 600], "en") == "page 1, top centre"
    assert position(1, [0, 400, 100, 600], "it") == "pagina 1, in alto al centro"
    assert position(3, [450, 450, 550, 550], "en") == "page 3, centre"
    assert position(3, [450, 450, 550, 550], "it") == "pagina 3, al centro"
    assert position(4, [400, 700, 600, 1000], "en") == "page 4, middle right"
    assert position(4, [400, 700, 600, 1000], "it") == "pagina 4, a metà pagina a destra"
    # missing_initials has no box; a box that is not four numbers gives only the page.
    assert position(5, None, "en") == "page 5" and position(5, [1, 2, "x", 4], "it") == "pagina 5"
    assert position(None, [900, 900, 1000, 1000], "en") == "bottom right"


def test_the_section_in_italian_and_english():
    section = visual_section(visual())
    it, en = section["it"], section["en"]
    assert it["title"] == "Controlli visivi" and en["title"] == "Visual checks"
    assert en["why"] == [
        "page 2: scanned page",
        "page 3: hidden text",
        "page 6: signature field “Buyer”, drawing or hand stroke",
    ]
    assert it["why"][0] == "pagina 2: pagina scansionata"
    assert en["route"] == "The council looked at pages 2 and 6 as images."
    assert it["route"] == "Il Consiglio ha guardato come immagini le pagine 2 e 6."
    assert en["hidden"] == "The hidden text (page 3) was removed before reading."
    assert it["hidden"] == "Il testo nascosto (pagina 3) è stato tolto prima della lettura."
    signed, amounts = en["checks"]
    assert signed["question"] == "Is the contract signed by both parties?"
    assert signed["answer"] == "Only the supplier signed." and signed["unknown"] is None
    assert signed["objects"] == [
        "Signature, page 6, bottom left: “M. Rossi”",
        "Unsigned signature block, page 6, bottom right",
    ]
    assert it["checks"][0]["objects"][1] == "Spazio per la firma non firmato, pagina 6, in basso a destra"
    assert amounts["answer"] == "No answer." and amounts["objects"] == []
    assert it["checks"][1]["answer"] == "Nessuna risposta."


def test_the_checks_as_the_service_writes_them():
    """reviewer.manager.visual_checks puts the answer's fields on the check itself."""
    flat = [
        {
            "section": "signatures",
            "question": "Who signed? Which signature blocks are empty?",
            "answer": "Only the supplier signed.",
            "objects": [{"page": 6, "type": "signature", "box_2d": [820, 100, 880, 300], "text": "M. Rossi"}],
            "known": True,
        },
        {"section": "stamps", "question": "Stamps?", "answer": "I cannot tell.", "objects": [], "known": False},
        {
            "section": "handwriting",
            "question": "Handwriting?",
            "answer": None,
            "objects": [],
            "known": False,
            "error": "the answer is not a valid JSON",
        },
    ]
    one_page = visual_section(visual() | {"checks": flat, "visual_pages": [3]})
    assert one_page["en"]["route"] == "The council looked at page 3 as an image."
    assert one_page["it"]["route"] == "Il Consiglio ha guardato come immagine la pagina 3."
    signed, stamps, handwriting = one_page["en"]["checks"]
    assert signed["answer"] == "Only the supplier signed." and signed["unknown"] is None
    assert signed["objects"] == ["Signature, page 6, bottom left: “M. Rossi”"]
    assert stamps["answer"] == "I cannot tell." and stamps["unknown"] == "The pages do not say for sure."
    assert handwriting == {"question": "Handwriting?", "answer": "No answer.", "unknown": None, "objects": []}


def test_the_text_route_and_no_hidden_text():
    en = visual_section(visual() | {"route": "text", "visual_mode": "off", "hidden_text_removed": False})["en"]
    assert en["route"] == "The council read only the visible text: the visual mode was off."
    assert en["hidden"] == "The PDF had no hidden text."
    it = visual_section(visual() | {"route": "text", "visual_mode": "on", "checks": []})["it"]
    assert it["route"].startswith("Il Consiglio ha letto solo il testo visibile") and it["checks"] == []


def test_the_page_carries_the_visual_checks_escaped():
    v = visual_view()
    v["visual"]["checks"][0]["question"] = "Signed? </script><script>alert(1)</script><!--"
    html = page(v)
    assert html.count('<script id="visual" type="application/json">') == 1 and ".visual-checks {" in html
    inside = html.split('<script id="visual" type="application/json">', 1)[1].split("</script>", 1)[0]
    assert "<" not in inside
    assert json.loads(inside)["en"]["checks"][0]["question"] == v["visual"]["checks"][0]["question"]
    # The rest of the page is the one of today, with the data and the section added.
    assert html.startswith(PAGE.read_text().split("</style>", 1)[0])
    assert html.rstrip().endswith("</script>\n</body>\n</html>")
