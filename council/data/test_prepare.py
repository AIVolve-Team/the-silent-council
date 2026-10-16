import csv
import hashlib
import json
import re
from pathlib import Path

import pytest

from categories import CLAUDETTE_CATEGORIES, CONTRACTNLI_HYPOTHESES, CUAD_CATEGORIES, FINANCE, LEGAL, READERS, RISK
from prepare import (
    claudette_answers,
    claudette_rows,
    contractnli_rows,
    cuad_rows,
    draw_sample,
    extract_clauses,
    replication,
)


def test_nested_clauses_and_ignored_tags():
    xml = (
        "Inizio. <ltd2>Non rispondiamo <ter3>e possiamo chiudere</ter3> il conto.</ltd2> <countryM>IT</countryM> Fine."
    )
    assert extract_clauses(xml) == [
        ("ter", 3, "e possiamo chiudere"),
        ("ltd", 2, "Non rispondiamo e possiamo chiudere il conto."),
    ]


def test_html_quoted_in_the_tos_is_not_a_tag():
    xml = "Il link (<a>) rimanda alla fonte. <j1>Foro di Milano.</j1>"
    assert extract_clauses(xml) == [("j", 1, "Foro di Milano.")]


def test_unclosed_tag_stops():
    with pytest.raises(ValueError):
        extract_clauses("<ltd2>senza chiusura")


def test_claudette_grade_1_is_not_flagged():
    contract = {"id": "X", "answers": claudette_answers("<j1>Foro.</j1> <ltd3>Nessuna responsabilità.</ltd3>")}
    rows = {r["tag"]: r for r in claudette_rows(contract, "test")}
    assert rows["j"]["should_flag"] is False and rows["j"]["max_grade"] == 1 and rows["j"]["evidence"] == []
    assert rows["ltd"]["should_flag"] is True and rows["ltd"]["should_flag_grade_3"] is True
    assert rows["ltd"]["evidence"] == ["Nessuna responsabilità."]
    assert rows["a"]["should_flag"] is False and rows["a"]["max_grade"] is None
    assert len(rows) == 9


def test_contractnli_only_contradiction_is_flagged():
    answers = {f"nda-{i}": ("NotMentioned", []) for i in (1, 2, 3, 4, 5, 8, 10, 11, 12, 13, 15, 16, 17, 18, 19, 20)}
    answers["nda-7"] = ("Contradiction", ["Può condividere con terzi."])
    answers["nda-4"] = ("Entailment", ["Solo per lo scopo."])
    rows = {r["hypothesis"]: r for r in contractnli_rows({"id": "nda.pdf", "answers": answers}, "test")}
    assert rows["nda-7"]["should_flag"] is True and rows["nda-7"]["evidence"] == ["Può condividere con terzi."]
    assert rows["nda-4"]["should_flag"] is False and rows["nda-4"]["original_label"] == "Entailment"
    assert len(rows) == 17


def test_cuad_yes_if_there_is_an_annotated_piece():
    from prepare import cuad_answers

    qas = [
        {"id": "C__Exclusivity", "answers": [{"text": "esclusiva", "answer_start": 0}]},
        {"id": "C__Governing Law", "answers": [{"text": "legge di New York", "answer_start": 0}]},
        {"id": "C__Non-Compete", "answers": []},
    ]
    rows = {r["category"]: r for r in cuad_rows({"id": "C", "answers": cuad_answers(qas)}, "test")}
    assert rows["Exclusivity"]["should_flag"] is True and rows["Exclusivity"]["role"] == "risk"
    assert rows["Non-Compete"]["should_flag"] is False
    assert "Governing Law" not in rows and len(rows) == 19


def test_sample_reproducible_and_independent_of_order():
    ids = [f"c{i}" for i in range(50)]
    assert draw_sample(ids, 20, "x-test") == draw_sample(list(reversed(ids)), 20, "x-test")
    assert draw_sample(ids, 20, "x-test") != draw_sample(ids, 20, "y-test")


def test_sample_too_small_stops():
    with pytest.raises(SystemExit):
        draw_sample(["a", "b"], 5, "x-dev")


def test_readers_are_the_roles_with_categories_in_relay_order():
    roles = {
        "cuad": set(CUAD_CATEGORIES.values()),
        "contractnli": {role for _, role in CONTRACTNLI_HYPOTHESES.values()},
        "claudette": {role for _, role in CLAUDETTE_CATEGORIES.values()},
    }
    assert set(READERS) == set(roles)
    for benchmark, readers in READERS.items():
        assert set(readers) == roles[benchmark], benchmark
        assert list(readers) == [r for r in (LEGAL, FINANCE, RISK) if r in readers], benchmark


def test_replication_is_all_under_cap_minus_the_test():
    assert replication(["c3", "c1", "c2", "c4"], ["c2", "c9"]) == ["c1", "c3", "c4"]


# --- The committed files and the pre-registration ---------------------------------------------------------------------

SET = Path(__file__).resolve().parent / "measurement-set"

# The pre-registration pins the hashes of the files as they were written before the English rename, with Italian
# file names, keys and values. The committed files differ from those only in these names, so the test rebuilds the
# original bytes from them and checks the pinned hash: the content (contracts, categories, answers) is unchanged.
LEGACY_FILES = {
    "campione.json": "sample.json",
    "campione-replica.json": "sample-replication.json",
    "risposte-giuste.jsonl": "correct-answers.jsonl",
    "risposte-giuste-replica.jsonl": "correct-answers-replication.jsonl",
}
LEGACY_KEYS = {
    "seed": "seme",
    "token_cap": "tetto",
    "subset": "insieme",
    "contract": "contratto",
    "category": "categoria",
    "hypothesis": "ipotesi",
    "role": "ruolo",
    "should_flag": "da_segnalare",
    "original_label": "etichetta_originale",
    "should_flag_grade_3": "da_segnalare_grado_3",
    "max_grade": "grado_massimo",
    "evidence": "prove",
}
LEGACY_SUBSETS = {"dev": "sviluppo", "replication": "replica", "all": "tutti"}
LEGACY_ROLES = {"legal": "legale", "finance": "finanza", "risk": "rischio"}


def _legacy_row(row: dict) -> dict:
    values = {"subset": LEGACY_SUBSETS, "role": LEGACY_ROLES}
    return {LEGACY_KEYS.get(k, k): values[k].get(v, v) if k in values else v for k, v in row.items()}


def _legacy_sample(sample: dict) -> dict:
    return {
        LEGACY_KEYS.get(k, k): {LEGACY_SUBSETS.get(s, s): ids for s, ids in v.items()} if isinstance(v, dict) else v
        for k, v in sample.items()
    }


def _legacy_bytes(name: str) -> bytes:
    """The bytes of a committed file as they were before the rename; `name` is the old or the new file name."""
    path = SET / LEGACY_FILES.get(name, name)
    if path.suffix == ".jsonl":
        text = "".join(json.dumps(_legacy_row(json.loads(r)), ensure_ascii=False) + "\n" for r in path.open())
    else:
        text = json.dumps(_legacy_sample(json.loads(path.read_text())), indent=2, ensure_ascii=False) + "\n"
    return text.encode()


def _preregistered_hashes() -> dict[str, str]:
    council = Path(__file__).resolve().parents[1]
    (preregistration,) = [p for p in (council / "PREREGISTRATION.md", council / "PREREGISTRAZIONE.md") if p.exists()]
    pattern = r"`(?:consiglio/dati/set-di-misura|council/data/measurement-set)/([^`]+)` \| `([0-9a-f]{64})`"
    return dict(re.findall(pattern, preregistration.read_text()))


def test_the_test_files_are_still_the_preregistered_ones():
    hashes = _preregistered_hashes()
    assert {LEGACY_FILES.get(name, name) for name in hashes} >= {"sample.json", "correct-answers.jsonl"}
    for name, expected in hashes.items():
        assert hashlib.sha256(_legacy_bytes(name)).hexdigest() == expected, name


def test_cuad_replication_72_contracts_under_the_cap_outside_the_test():
    sample = json.loads((SET / "sample.json").read_text())
    replication_cuad = json.loads((SET / "sample-replication.json").read_text())["cuad"]["replication"]
    with (SET / "tokens-per-contract.csv").open() as f:
        tokens = {
            r["contract"]: int(r["qwen3_tokens"])
            for r in csv.DictReader(f)
            if r["benchmark"] == "cuad" and r["original_split"] == "test"
        }
    under = {cid for cid, t in tokens.items() if t <= sample["token_cap"]}
    assert len(replication_cuad) == len(set(replication_cuad)) == 72
    assert not set(replication_cuad) & set(sample["cuad"]["test"])
    assert set(replication_cuad) == under - set(sample["cuad"]["test"])


def test_replication_answers_one_row_per_pair():
    replication_cuad = json.loads((SET / "sample-replication.json").read_text())["cuad"]["replication"]
    rows = [json.loads(r) for r in (SET / "correct-answers-replication.jsonl").open()]
    assert {(r["benchmark"], r["subset"]) for r in rows} == {("cuad", "replication")}
    assert sorted({r["contract"] for r in rows}) == replication_cuad
    assert len({(r["contract"], r["category"]) for r in rows}) == len(rows) == 72 * len(CUAD_CATEGORIES)
    assert any(r["should_flag"] for r in rows)
