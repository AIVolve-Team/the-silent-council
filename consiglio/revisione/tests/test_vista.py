"""La vista per la pagina del verdetto e le regole di «Verdetto e dissenso», senza modello."""

import copy
import json
from pathlib import Path

from revisione import BENCHMARK
from revisione.vista import PAGINA, pagina, vista

ESEMPIO = Path(__file__).parents[1] / "pagina" / "esempio-revisione.json"
TITOLO = "Contratto di fornitura di componenti (esempio)"


def revisione():
    return json.loads(ESEMPIO.read_text())


def test_righe_raccomandazione_e_sigillo():
    v = vista(revisione(), BENCHMARK["dimostrativo"], TITOLO)
    assert len(v["righe"]) == 19 and [n["ruolo"] for n in v["note"]] == ["legale", "finanza", "rischio"]
    assert v["raccomandazione"]["valore"] == "negoziare"
    assert v["sigillo"] == {
        "integro": True,
        "messaggi": 3,
        "impronte": revisione()["impronte"],
        "controllo": None,
        "motivo": None,
    }
    tetto = next(r for r in v["righe"] if r["chiave"] == "Cap On Liability")
    assert tetto["segnalare"] is True and tetto["citazione_trovata"] is True and tetto["confidenza"] == "alta"
    cessione = next(r for r in v["righe"] if r["chiave"] == "Anti-Assignment")
    assert cessione["citazione_trovata"] is False


def test_il_taglio_e_i_passi_per_la_vista_a_fumetti():
    # quanti caratteri ha letto ogni esperto, e con quanti passi latenti, senza le frasi del contratto.
    v = vista(revisione(), BENCHMARK["dimostrativo"], TITOLO)
    assert v["taglio"] == {"modo": "titoli", "caratteri": {"legale": 4200, "finanza": 900, "rischio": 1400}}
    assert v["passi_latenti"] == 10
    senza = {k: x for k, x in revisione().items() if k not in ("taglio", "passi_latenti")}
    assert vista(senza, BENCHMARK["dimostrativo"], TITOLO)["taglio"] is None


def test_dissenso_grave_con_esperto_sicuro_in_evidenza():
    righe = {r["chiave"]: r for r in vista(revisione(), BENCHMARK["dimostrativo"], TITOLO)["righe"]}
    grave = righe["Change Of Control"]["dissenso"]
    assert grave["tipo"] == "grave" and grave["in_evidenza"] is True and grave["esperto_dice"] is True
    assert grave["citazione_esperto"].startswith("Se il controllo del Cliente")
    lieve = righe["Most Favored Nation"]["dissenso"]
    assert lieve["tipo"] == "lieve" and lieve["in_evidenza"] is False
    assert all(r["dissenso"] is None for k, r in righe.items() if k not in ("Change Of Control", "Most Favored Nation"))


def test_catena_fermata_niente_verdetto():
    fermata = copy.deepcopy(revisione())
    fermata["verdetto"] = None
    fermata["dissensi"] = []
    fermata["fermata"] = {"passa": False, "controllo": "sigillo", "motivo": "firma non valida per finanza"}
    v = vista(fermata, BENCHMARK["dimostrativo"], TITOLO)
    assert v["raccomandazione"] is None and v["sigillo"]["integro"] is False
    assert v["sigillo"]["motivo"] == "firma non valida per finanza"


def test_pagina_con_i_dati_dentro_senza_chiudere_lo_script():
    v = vista(revisione(), BENCHMARK["dimostrativo"], TITOLO)
    v["titolo"] = "Prova </script><script>alert(1)</script>"
    html = pagina(v)
    dentro = html.split('<script id="dati" type="application/json">', 1)[1].split("</script>", 1)[0]
    assert json.loads(dentro)["titolo"] == v["titolo"]
    assert PAGINA.read_text().count('<script id="dati"') == 1


def test_la_pagina_di_esempio_e_aggiornata():
    attesa = pagina(vista(revisione(), BENCHMARK["dimostrativo"], TITOLO))
    assert (ESEMPIO.parent / "esempio.html").read_text() == attesa, "rigenerare pagina/esempio.html (vedi README)"


def test_accanto_a_ogni_riga_la_risposta_degli_esperti():
    # Nel sito dei giudici: dove il Consiglio è d'accordo con gli esperti del dataset e dove sbaglia.
    esperti = {
        "Cap On Liability": {"da_segnalare": True, "prove": ["x" * 500]},
        "Anti-Assignment": {"da_segnalare": False, "prove": []},
    }
    fonte = {"nome": "CUAD", "chi": "gli esperti di CUAD", "link": "https://example.org", "spiegazione": "…"}
    v = vista(revisione(), BENCHMARK["dimostrativo"], TITOLO, esperti=esperti, fonte=fonte)
    righe = {r["chiave"]: r for r in v["righe"]}
    tetto, cessione = righe["Cap On Liability"]["esperti"], righe["Anti-Assignment"]["esperti"]
    assert tetto["d_accordo"] is True and tetto["prove"][0].endswith("…") and len(tetto["prove"][0]) < 500
    assert righe["Anti-Assignment"]["segnalare"] is True and cessione["d_accordo"] is False
    assert righe["Uncapped Liability"]["esperti"] is None
    assert v["confronto"] == fonte | {"d_accordo": 1, "confrontate": 2, "trovate": 1, "da_trovare": 1}


def test_la_pmi_non_vede_il_confronto():
    v = vista(revisione(), BENCHMARK["dimostrativo"], TITOLO)
    assert v["confronto"] is None and all(r["esperti"] is None for r in v["righe"])
