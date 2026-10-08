import json
import re

from pagina.pagina import elenco, pagina_caso


def vista(id_="sviluppo-0006", esito="pagare", descrizione="Toner nero"):
    return {"id": id_, "esito": esito, "motivo": {"it": "ok", "en": "ok"},
            "fattura": {"fornitore": "Alfa S.r.l.", "numero": "FT/1/2026", "data": "2026-09-15", "totale": 152.5, "scadenza": None},
            "sigillo": {"integro": True, "dettaglio": "integro"}, "testimoni": [], "regole": [], "altri_motivi": [],
            "ordine": None, "righe": [{"n": 1, "descrizione": descrizione}], "nascosto": [], "contatti": None,
            "frode_sospetta": False, "proposta": {"importo": 152.5}, "nota_obbligatoria": False, "pdf": "JVBER"}  # fmt: skip


def dati_di(html: str) -> dict:
    return json.loads(re.search(r'<script id="dati" type="application/json">(.*?)</script>', html, re.DOTALL).group(1))


def test_la_pagina_porta_i_dati_del_caso():
    html = pagina_caso(vista(), registrato="15/10/2026 sulla MI300X")
    assert dati_di(html)["id"] == "sviluppo-0006"
    assert dati_di(html)["registrato"] == "15/10/2026 sulla MI300X"


def test_una_descrizione_non_rompe_la_pagina():
    html = pagina_caso(vista(descrizione="</script><script>alert(1)</script>"))
    assert dati_di(html)["righe"][0]["descrizione"] == "</script><script>alert(1)</script>"
    assert html.count("<script>alert(1)") == 0


def test_l_indirizzo_per_evolus_si_mette_solo_se_c_e():
    assert 'data-api=""' in pagina_caso(vista())
    assert 'data-api="/api/decisione"' in pagina_caso(vista(), api="/api/decisione")


def test_l_elenco_mette_in_cima_le_proposte_da_approvare():
    html = elenco([vista("a", "bloccare"), vista("b", "pagare"), vista("c", "persona")])
    casi = dati_di(html)
    assert [c["id"] for c in casi] == ["a", "b", "c"]
    assert "pdf" not in casi[0]  # l'elenco non si porta dietro i PDF


def test_con_il_pdf_accanto_la_pagina_non_lo_incorpora():
    dati = dati_di(pagina_caso(vista(), pdf_url="sviluppo-0006.pdf"))
    assert dati["pdf_url"] == "sviluppo-0006.pdf"
    assert "pdf" not in dati
