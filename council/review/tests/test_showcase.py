"""The council's part of the judges' site, without a model."""

import json
from pathlib import Path

import pytest

from review import BENCHMARK
from review.data import expert_answers
from review.showcase import Private, cuad_title, write_showcase

EXAMPLE = Path(__file__).parents[1] / "page" / "example-review.json"
DATA_SCRIPT = '<script id="data" type="application/json">'


def run(tmp_path, **changes):
    review = json.loads(EXAMPLE.read_text()) | changes
    f = tmp_path / f"run-{review['benchmark']}.jsonl"
    f.write_text(json.dumps(review) + "\n")
    return f


def index_data(output):
    index = (output / "index.html").read_text()
    return json.loads(index.split(DATA_SCRIPT)[1].split("</script>")[0])


def test_the_demo_set_does_not_go_out_before_delivery(tmp_path):
    with pytest.raises(Private, match="private until delivery"):
        write_showcase([run(tmp_path)], tmp_path / "showcase", recorded=None)
    assert not (tmp_path / "showcase").exists()


def test_index_and_pages(tmp_path):
    output = tmp_path / "showcase"
    n = write_showcase([run(tmp_path, benchmark="cuad", contract="EXAMPLE-SUPPLY AGREEMENT")], output, recorded="today")
    assert n == 1
    data = index_data(output)
    entry = data["verdicts"][0]
    assert data["recorded"] == "today" and entry["recommendation"] == "negotiate" and entry["categories"] == 19
    assert entry["seal_intact"] and (output / entry["page"]).exists()
    # the empty verdict page, which the live review opens with the view saved in the judge's browser
    assert f"{DATA_SCRIPT}null</script>" in (output / "verdict.html").read_text()
    assert "quote" not in json.dumps(entry)  # in the index only counts, no sentences of the contract


def test_the_category_names_are_those_of_the_data():
    # If a name does not match, the verdict row would be left without the experts' answer.
    for benchmark in ("cuad", "contractnli", "claudette"):
        keys = {c.key for c in BENCHMARK[benchmark].categories}
        used = {cat for categories in expert_answers(benchmark).values() for cat in categories}
        assert used == keys, benchmark


def test_a_cuad_contract_has_the_comparison_with_the_experts(tmp_path):
    contract = "TRANSPHORM,INC_02_14_2020-EX-10.12(1)-JOINT VENTURE AGREEMENT"
    output = tmp_path / "showcase"
    write_showcase([run(tmp_path, benchmark="cuad", contract=contract)], output, recorded=None)
    entry = index_data(output)["verdicts"][0]
    correct = expert_answers("cuad")[contract]
    flag = json.loads(EXAMPLE.read_text())["verdict"]["data"]["flag"]
    expected = sum(flag[c] == g["should_flag"] for c, g in correct.items() if flag.get(c) is not None)
    assert entry["source"] == "CUAD" and entry["compared"] == 19 and entry["agreed"] == expected
    page = (output / entry["page"]).read_text()
    assert "github.com/TheAtticusProject/cuad" in page


def test_the_numbers_for_the_home_page(tmp_path):
    # The per-contract averages of telepathy and text, only on the contracts done in both modes.
    contract = "TRANSPHORM,INC_02_14_2020-EX-10.12(1)-JOINT VENTURE AGREEMENT"
    telepathy = run(tmp_path, benchmark="cuad", contract=contract, tokens_generated=1000, seconds=100.0)
    text = tmp_path / "run-text.jsonl"
    text.write_text(
        json.dumps(json.loads(EXAMPLE.read_text()) | {"benchmark": "cuad", "contract": contract, "mode": "text"}) + "\n"
    )
    telepathy_only = tmp_path / "run-other.jsonl"
    telepathy_only.write_text(
        json.dumps(json.loads(EXAMPLE.read_text()) | {"benchmark": "cuad", "contract": "EXAMPLE-OTHER"}) + "\n"
    )
    output = tmp_path / "showcase"
    write_showcase([telepathy, text, telepathy_only], output, recorded="today")
    numbers = json.loads((output / "numbers.json").read_text())
    assert numbers["source"] == "CUAD" and numbers["contracts"] == 1 and numbers["recorded"] == "today"
    assert numbers["telepathy"]["tokens_generated"] == 1000 and numbers["telepathy"]["seconds"] == 100.0
    assert numbers["text"]["tokens_generated"] == json.loads(EXAMPLE.read_text())["tokens_generated"]
    assert numbers["telepathy"]["to_find"] == sum(g["should_flag"] for g in expert_answers("cuad")[contract].values())


def test_without_text_no_numbers_and_no_double_runs(tmp_path):
    output = tmp_path / "showcase"
    write_showcase([run(tmp_path, benchmark="cuad", contract="EXAMPLE-SUPPLY AGREEMENT")], output, recorded=None)
    assert not (output / "numbers.json").exists()
    double = run(tmp_path, benchmark="cuad", contract="EXAMPLE-SUPPLY AGREEMENT")
    double.write_text(double.read_text() * 2)
    with pytest.raises(SystemExit, match="twice"):
        write_showcase([double], tmp_path / "other", recorded=None)


def test_the_names_of_the_cuad_contracts():
    assert (
        cuad_title("PenntexMidstreamPartnersLp_20150416_S-1A_EX-10.4_9042833_EX-10.4_Transportation Agreement")
        == "Penntex Midstream Partners Lp: transportation agreement"
    )
    assert cuad_title("SightLife Surgical, Inc. - STRATEGIC SALES _ MARKETING AGREEMENT") == (
        "SightLife Surgical, Inc.: strategic sales & marketing agreement"
    )
    assert cuad_title("MSCIINC_02_28_2008-EX-10.10-") == "MSCIINC: contract"


def test_the_catalog_of_the_live_reviews(monkeypatch):
    # The judge picks only among dataset contracts: the key is benchmark:id and the text stays on the server.
    from review import live

    contract = "TRANSPHORM,INC_02_14_2020-EX-10.12(1)-JOINT VENTURE AGREEMENT"
    fake = {"dev": [(contract, "short"), ("EXAMPLE-LONG", "long " * 50)], "test": [("EXAMPLE-TEST", "x")]}
    monkeypatch.setattr(live, "contracts", lambda benchmark, subset: fake[subset])
    items = live.catalog(("dev",), length=lambda text: len(text.split()), max_tokens=10)
    assert list(items) == [f"cuad:{contract}"]
    item = items[f"cuad:{contract}"]
    assert item["title"] == "TRANSPHORM, INC: joint venture agreement" and item["source"]["name"] == "CUAD"
    assert item["experts"] == expert_answers("cuad")[contract]
    assert "EXAMPLE-TEST" not in str(items) and set(live.catalog(("dev", "test"))) >= {"cuad:EXAMPLE-TEST"}
    assert all("text" not in v for v in live.listing(items))
    with pytest.raises(ValueError, match="unknown"):
        live.catalog(("trial",))
