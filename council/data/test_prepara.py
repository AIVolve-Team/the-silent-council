import csv
import hashlib
import json
import re
from pathlib import Path

import pytest

from categorie import CLAUDETTE_CATEGORIE, CONTRACTNLI_IPOTESI, CUAD_CATEGORIE, FINANZA, LEGALE, LETTORI, RISCHIO
from prepara import (
    campiona,
    estrai_clausole,
    replica,
    righe_claudette,
    righe_contractnli,
    righe_cuad,
    risposte_claudette,
)


def test_clausole_annidate_e_tag_ignorati():
    xml = (
        "Inizio. <ltd2>Non rispondiamo <ter3>e possiamo chiudere</ter3> il conto.</ltd2> <countryM>IT</countryM> Fine."
    )
    assert estrai_clausole(xml) == [
        ("ter", 3, "e possiamo chiudere"),
        ("ltd", 2, "Non rispondiamo e possiamo chiudere il conto."),
    ]


def test_html_citato_nel_tos_non_e_un_tag():
    xml = "Il link (<a>) rimanda alla fonte. <j1>Foro di Milano.</j1>"
    assert estrai_clausole(xml) == [("j", 1, "Foro di Milano.")]


def test_tag_non_chiuso_si_ferma():
    with pytest.raises(ValueError):
        estrai_clausole("<ltd2>senza chiusura")


def test_claudette_grado_1_non_va_segnalato():
    contratto = {"id": "X", "risposte": risposte_claudette("<j1>Foro.</j1> <ltd3>Nessuna responsabilità.</ltd3>")}
    righe = {r["tag"]: r for r in righe_claudette(contratto, "test")}
    assert righe["j"]["da_segnalare"] is False and righe["j"]["grado_massimo"] == 1 and righe["j"]["prove"] == []
    assert righe["ltd"]["da_segnalare"] is True and righe["ltd"]["da_segnalare_grado_3"] is True
    assert righe["ltd"]["prove"] == ["Nessuna responsabilità."]
    assert righe["a"]["da_segnalare"] is False and righe["a"]["grado_massimo"] is None
    assert len(righe) == 9


def test_contractnli_solo_contradiction_va_segnalata():
    risposte = {f"nda-{i}": ("NotMentioned", []) for i in (1, 2, 3, 4, 5, 8, 10, 11, 12, 13, 15, 16, 17, 18, 19, 20)}
    risposte["nda-7"] = ("Contradiction", ["Può condividere con terzi."])
    risposte["nda-4"] = ("Entailment", ["Solo per lo scopo."])
    righe = {r["ipotesi"]: r for r in righe_contractnli({"id": "nda.pdf", "risposte": risposte}, "test")}
    assert righe["nda-7"]["da_segnalare"] is True and righe["nda-7"]["prove"] == ["Può condividere con terzi."]
    assert righe["nda-4"]["da_segnalare"] is False and righe["nda-4"]["etichetta_originale"] == "Entailment"
    assert len(righe) == 17


def test_cuad_si_se_c_e_un_pezzo_annotato():
    from prepara import risposte_cuad

    qas = [
        {"id": "C__Exclusivity", "answers": [{"text": "esclusiva", "answer_start": 0}]},
        {"id": "C__Governing Law", "answers": [{"text": "legge di New York", "answer_start": 0}]},
        {"id": "C__Non-Compete", "answers": []},
    ]
    righe = {r["categoria"]: r for r in righe_cuad({"id": "C", "risposte": risposte_cuad(qas)}, "test")}
    assert righe["Exclusivity"]["da_segnalare"] is True and righe["Exclusivity"]["ruolo"] == "rischio"
    assert righe["Non-Compete"]["da_segnalare"] is False
    assert "Governing Law" not in righe and len(righe) == 19


def test_campione_riproducibile_e_indipendente_dall_ordine():
    ids = [f"c{i}" for i in range(50)]
    assert campiona(ids, 20, "x-test") == campiona(list(reversed(ids)), 20, "x-test")
    assert campiona(ids, 20, "x-test") != campiona(ids, 20, "y-test")


def test_campione_troppo_piccolo_si_ferma():
    with pytest.raises(SystemExit):
        campiona(["a", "b"], 5, "x-sviluppo")


def test_lettori_sono_i_ruoli_con_categorie_nell_ordine_della_staffetta():
    ruoli = {
        "cuad": set(CUAD_CATEGORIE.values()),
        "contractnli": {ruolo for _, ruolo in CONTRACTNLI_IPOTESI.values()},
        "claudette": {ruolo for _, ruolo in CLAUDETTE_CATEGORIE.values()},
    }
    assert set(LETTORI) == set(ruoli)
    for benchmark, lettori in LETTORI.items():
        assert set(lettori) == ruoli[benchmark], benchmark
        assert list(lettori) == [r for r in (LEGALE, FINANZA, RISCHIO) if r in lettori], benchmark


def test_replica_e_tutto_il_sotto_tetto_meno_il_test():
    assert replica(["c3", "c1", "c2", "c4"], ["c2", "c9"]) == ["c1", "c3", "c4"]


# --- La replica di CUAD sui file committati --------------------------------------------------------------------

SET = Path(__file__).resolve().parent / "set-di-misura"


def _hash_preregistrati() -> dict[str, str]:
    testo = (Path(__file__).resolve().parents[1] / "PREREGISTRAZIONE.md").read_text()
    return dict(re.findall(r"`consiglio/dati/set-di-misura/([^`]+)` \| `([0-9a-f]{64})`", testo))


def test_i_file_del_test_restano_quelli_preregistrati():
    hash_ = _hash_preregistrati()
    assert set(hash_) >= {"campione.json", "risposte-giuste.jsonl"}
    for nome, atteso in hash_.items():
        assert hashlib.sha256((SET / nome).read_bytes()).hexdigest() == atteso, nome


def test_replica_cuad_72_contratti_sotto_il_tetto_fuori_dal_test():
    campione = json.loads((SET / "campione.json").read_text())
    replica_cuad = json.loads((SET / "campione-replica.json").read_text())["cuad"]["replica"]
    with (SET / "token-per-contratto.csv").open() as f:
        token = {
            r["contratto"]: int(r["token_qwen3"])
            for r in csv.DictReader(f)
            if r["benchmark"] == "cuad" and r["insieme_originale"] == "test"
        }
    sotto = {cid for cid, t in token.items() if t <= campione["tetto"]}
    assert len(replica_cuad) == len(set(replica_cuad)) == 72
    assert not set(replica_cuad) & set(campione["cuad"]["test"])
    assert set(replica_cuad) == sotto - set(campione["cuad"]["test"])


def test_risposte_della_replica_una_riga_per_coppia():
    replica_cuad = json.loads((SET / "campione-replica.json").read_text())["cuad"]["replica"]
    righe = [json.loads(r) for r in (SET / "risposte-giuste-replica.jsonl").open()]
    assert {(r["benchmark"], r["insieme"]) for r in righe} == {("cuad", "replica")}
    assert sorted({r["contratto"] for r in righe}) == replica_cuad
    assert len({(r["contratto"], r["categoria"]) for r in righe}) == len(righe) == 72 * len(CUAD_CATEGORIE)
    assert any(r["da_segnalare"] for r in righe)
