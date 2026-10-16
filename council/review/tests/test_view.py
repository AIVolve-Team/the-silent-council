"""The view for the verdict page and the rules of “Verdict and dissent”, without a model."""

import copy
import json
from pathlib import Path

from review import BENCHMARK
from review.view import PAGE, page, view

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
