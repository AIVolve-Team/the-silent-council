import json

import pytest

from revisore.gestore import Occupato, Rifiuto, chiave_del_caso

from .conftest import CATALOGO, CONTRATTO, ESEMPIO, SEGRETO, email, pdf_con_testo


def test_un_contratto_diventa_un_caso_con_pagina_link_e_avviso(revisore, consiglio):
    r = revisore.revisiona_contratto(None, CONTRATTO, **email())
    assert r["id_caso"].startswith("consiglio-") and r["verdetto"] and r["sigillo_integro"]
    assert r["raccomandazione"]["valore"] == ESEMPIO["verdetto"]["dati"]["raccomandazione"]
    assert (
        r["link"]
        == f"https://consiglio.example.org/verdetto/{r['id_caso']}?chiave={chiave_del_caso(SEGRETO, r['id_caso'])}"
    )
    assert (
        r["avviso"]["oggetto"].startswith("[Consiglio] Contratto di fornitura:") and r["link"] in r["avviso"]["testo"]
    )
    gravi = [d for d in ESEMPIO["dissensi"] if d["tipo"] == "grave"]
    assert len(r["dissensi_gravi"]) == len(gravi)
    cartella = revisore.casi / r["id_caso"]
    assert {f.name for f in cartella.iterdir()} == {
        "revisione.json",
        "vista.json",
        "pagina.html",
        "email.json",
        "risposta.json",
    }
    # Il testo del contratto non si salva.
    assert all(CONTRATTO.strip() not in f.read_text() for f in cartella.iterdir())
    assert consiglio.chiamate == [(r["id_caso"], CONTRATTO, "telepatia", "dimostrativo")]


def test_la_stessa_email_e_lo_stesso_caso_e_il_consiglio_non_rigira(revisore, consiglio):
    primo = revisore.revisiona_contratto(None, CONTRATTO, **email())
    secondo = revisore.revisiona_contratto(None, CONTRATTO, **email())
    a_testo = revisore.revisiona_contratto(None, CONTRATTO, **email(), modalita="testo")
    assert primo == secondo and a_testo["id_caso"] != primo["id_caso"]
    assert len(consiglio.chiamate) == 2


def test_il_contratto_in_pdf(revisore, consiglio):
    revisore.revisiona_contratto(pdf_con_testo("Il Fornitore fornisce componenti"), None, **email())
    assert "Il Fornitore fornisce componenti" in consiglio.chiamate[0][1]
    with pytest.raises(Rifiuto, match="PDF"):
        revisore.revisiona_contratto(b"non sono un pdf", None, **email())
    with pytest.raises(Rifiuto, match="scansione"):
        revisore.revisiona_contratto(pdf_con_testo(""), None, **email())


@pytest.mark.parametrize(
    ("contratto", "testo", "altro", "motivo"),
    [
        (None, None, {}, "uno solo"),
        (b"%PDF-", CONTRATTO, {}, "uno solo"),
        (None, CONTRATTO, {"modalita": "voce"}, "modalita"),
        (None, CONTRATTO, {"mittente": " "}, "mittente"),
        (None, "x" * 200_001, {}, "contratto"),
    ],
)
def test_le_richieste_sbagliate_non_toccano_il_consiglio(revisore, consiglio, contratto, testo, altro, motivo):
    with pytest.raises(Rifiuto, match=motivo):
        revisore.revisiona_contratto(contratto, testo, **(email() | altro))
    assert consiglio.chiamate == []


def test_senza_sigillo_niente_verdetto_e_l_avviso_chiede_una_persona(revisore, consiglio):
    consiglio.fermata = {"controllo": "catena", "motivo": "hash del precedente diverso"}
    r = revisore.revisiona_contratto(None, CONTRATTO, **email())
    assert not r["verdetto"] and not r["sigillo_integro"] and r["raccomandazione"] is None
    assert "serve una persona" in r["avviso"]["oggetto"]


def test_le_scelte_della_persona(revisore):
    id_caso = revisore.revisiona_contratto(None, CONTRATTO, **email())["id_caso"]
    in_dissenso = sorted({d["categoria"] for d in ESEMPIO["dissensi"]})
    scelte = {in_dissenso[0]: "esperto"}
    registrata = revisore.registra_scelte(id_caso, scelte, "Ash")
    assert registrata["registrate"] == 1 and revisore.caso(id_caso)["scelte"][0]["scelte"] == scelte
    with pytest.raises(Rifiuto, match="non sono in dissenso"):
        revisore.registra_scelte(id_caso, {"Categoria inventata": "esperto"}, "Ash")
    with pytest.raises(Rifiuto, match="esperto o verdetto"):
        revisore.registra_scelte(id_caso, {in_dissenso[0]: "forse"}, "Ash")
    with pytest.raises(Rifiuto, match="chi"):
        revisore.registra_scelte(id_caso, scelte, "")
    with pytest.raises(Rifiuto, match="non è l'id"):
        revisore.registra_scelte("../../etc", scelte, "Ash")
    elenco = revisore.elenco()
    assert elenco[0]["id_caso"] == id_caso and elenco[0]["scelte"] == 1


def test_la_pagina_sa_dove_mandare_le_scelte(revisore):
    id_caso = revisore.revisiona_contratto(None, CONTRATTO, **email())["id_caso"]
    vista = json.loads((revisore.casi / id_caso / "vista.json").read_text())
    assert vista["invio_scelte"] == f"/verdetto/{id_caso}/scelte?chiave={chiave_del_caso(SEGRETO, id_caso)}"
    assert vista["invio_scelte"] in revisore.pagina_di(id_caso)


def test_la_prova_dal_vivo_e_un_caso_nuovo_con_il_confronto(dal_vivo, consiglio):
    chiave = next(iter(CATALOGO))
    prima = dal_vivo.prova_dal_vivo(chiave)
    seconda = dal_vivo.prova_dal_vivo(chiave)
    assert prima["id_caso"] != seconda["id_caso"]  # il giudice vede il Consiglio lavorare, anche sullo stesso contratto
    assert consiglio.chiamate[0][1] == CATALOGO[chiave]["testo"] and consiglio.chiamate[0][3] == "cuad"
    v = prima["vista"]
    assert v["lingua"] == "en" and v["dal_vivo"] and v["titolo"] == CATALOGO[chiave]["titolo"]
    tetto = next(r for r in v["righe"] if r["chiave"] == "Cap On Liability")
    assert tetto["esperti"]["da_segnalare"] is True and v["confronto"]["nome"] == "CUAD"
    assert dal_vivo.caso(prima["id_caso"])["vista"] == v
    assert {c["id_caso"] for c in dal_vivo.elenco()} == {prima["id_caso"], seconda["id_caso"]}


def test_la_prova_dal_vivo_rifiuta_e_non_aspetta(dal_vivo, revisore, consiglio):
    with pytest.raises(Rifiuto, match="spente"):
        revisore.prova_dal_vivo(next(iter(CATALOGO)))
    with pytest.raises(Rifiuto, match="non è fra"):
        dal_vivo.prova_dal_vivo("cuad:../../etc/passwd")
    with pytest.raises(Rifiuto, match="modalita"):
        dal_vivo.prova_dal_vivo(next(iter(CATALOGO)), "urlo")
    with dal_vivo.lucchetto, pytest.raises(Occupato):
        dal_vivo.prova_dal_vivo(next(iter(CATALOGO)))
    assert consiglio.chiamate == []
