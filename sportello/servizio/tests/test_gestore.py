import json

import pytest
from conftest import IBAN_INTERO

from servizio.gestore import Rifiuto


def esamina(sportello, pdf, caso, modalita="telepatia"):
    e = caso.email
    return sportello.esamina_fattura(pdf, e["mittente"], e["oggetto"], e["data"], modalita)


def test_un_caso_bloccato_torna_con_il_link_e_senza_nessun_iban_intero(sportello, pdf_frode, frode):
    risposta = esamina(sportello, pdf_frode, frode)

    assert risposta["esito"] == "bloccare"
    assert risposta["frode_sospetta"] is True
    assert risposta["link"] == f"https://sportello.example/caso.html?id={risposta['id_caso']}"
    assert risposta["proposta"] is None
    assert risposta["contatti_anagrafica"]["telefono"]
    assert IBAN_INTERO.search(json.dumps(risposta, ensure_ascii=False)) is None


def test_la_stessa_email_due_volte_e_lo_stesso_caso_e_non_rifa_l_esame(sportello, pipeline, pdf_pulita, pulita):
    prima = esamina(sportello, pdf_pulita, pulita)
    seconda = esamina(sportello, pdf_pulita, pulita)
    a_testo = esamina(sportello, pdf_pulita, pulita, modalita="testo")

    assert seconda == prima
    assert a_testo["id_caso"] != prima["id_caso"]
    assert len(pipeline.chiamate) == 2


@pytest.mark.parametrize(
    ("pdf", "mittente", "modalita"),
    [
        (b"<html>non sono un PDF</html>", "a@b.it", "telepatia"),
        (None, "a@b.it", "veloce"),
        (None, "x" * 5000, "telepatia"),
    ],
)
def test_una_richiesta_sbagliata_si_rifiuta_senza_toccare_il_modello(
    sportello, pipeline, pdf_pulita, pdf, mittente, modalita
):
    with pytest.raises(Rifiuto):
        sportello.esamina_fattura(pdf or pdf_pulita, mittente, "Fattura", "2026-10-08", modalita)

    assert pipeline.chiamate == []


def test_un_caso_bloccato_si_approva_solo_con_la_nota_e_la_decisione_resta_nel_caso(sportello, pdf_frode, frode):
    id_caso = esamina(sportello, pdf_frode, frode)["id_caso"]

    with pytest.raises(Rifiuto):
        sportello.registra_decisione(id_caso, "approvato", "giudice", "")
    with pytest.raises(Rifiuto):
        sportello.registra_decisione(id_caso, "rifiutato", "giudice", "  ")
    registrata = sportello.registra_decisione(id_caso, "approvato", "giudice", "Verificato al telefono in anagrafica")

    assert registrata["registrata"] is True
    assert [d["decisione"] for d in sportello.caso(id_caso)["decisioni"]] == ["approvato"]


@pytest.mark.parametrize("id_caso", ["../../etc", "sportello-000000000000", "", None])
def test_un_caso_che_non_esiste_non_si_decide(sportello, id_caso):
    with pytest.raises(Rifiuto):
        sportello.registra_decisione(id_caso, "segnalato", "giudice", "")


def test_l_elenco_ha_i_casi_esaminati_con_l_esito_e_la_decisione(sportello, pdf_pulita, pulita, pdf_frode, frode):
    pagare = esamina(sportello, pdf_pulita, pulita)["id_caso"]
    bloccare = esamina(sportello, pdf_frode, frode)["id_caso"]
    sportello.registra_decisione(pagare, "approvato", "giudice", "")

    elenco = {c["id"]: c for c in sportello.elenco()}

    assert {k: c["esito"] for k, c in elenco.items()} == {pagare: "pagare", bloccare: "bloccare"}
    assert elenco[pagare]["decisione"] == "approvato"
    assert elenco[bloccare]["decisione"] is None
