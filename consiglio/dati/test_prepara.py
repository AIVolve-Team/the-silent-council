import pytest

from prepara import campiona, estrai_clausole, righe_claudette, righe_contractnli, righe_cuad, risposte_claudette


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
