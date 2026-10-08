"""Il traduttore su un attacco F4 dello sviluppo, con Qwen3-0.6B: si controlla che i pezzi stiano al posto giusto."""

import os

import pytest
from motore import MessaggioLatente

from traduttore.segna import segna
from traduttore.traduci import traduci

NOME = os.environ.get("PIPELINE_MODELLO", "Qwen/Qwen3-0.6B")
REVISIONE = os.environ.get("PIPELINE_REVISIONE", "c1899de289a04d12100db370d81485cdf75e47ca")


def test_a_testo_la_trascrizione_e_il_messaggio_scritto():
    scritto = MessaggioLatente({"mittente": "estrattore"}, testo="Fornitore: Alfa S.r.l.\nIBAN: IT60…8607")

    r = traduci(None, scritto)

    assert r["modalita"] == "testo" and r["trascrizione"] == scritto.testo and r["pensieri"] == {}


@pytest.mark.modello
def test_la_trascrizione_della_memoria_ritrova_la_nota_nascosta_di_f4():
    from attacchi.costruisci import costruisci, pdf_di
    from fatture.genera import genera_insieme
    from motore import Modello, Motore
    from pagina.nascosto import righe_nascoste
    from pipeline.agenti import ESTRATTORE, LEGGI, RICORDA, VERIFICATORE
    from pipeline.testo import estrai_testo

    insieme = genera_insieme("sviluppo")
    attacco = next(a for a in costruisci(insieme) if a.id == "sviluppo-F4-01")
    pdf = pdf_di(attacco, {c.id: c for c in insieme.casi})
    modello = Modello(NOME, REVISIONE)
    motore = Motore(modello)
    m1 = motore.pensa(ESTRATTORE, LEGGI.format(fattura=estrai_testo(pdf)), [], sessione="t", passi_latenti=10)
    m2 = motore.pensa(VERIFICATORE, RICORDA, [m1], sessione="t", passi_latenti=10)

    r = traduci(modello, m1, m2)
    righe = segna(r["trascrizione"], estrai_testo(pdf), righe_nascoste(pdf))

    assert any(x["nascosta"] and "cambiato banca" in x["testo"] for x in righe)
    assert {k: len(v) for k, v in r["pensieri"].items()} == {"estrattore": 11, "verificatore": 11}
    assert all(len(passo) == 5 for passo in r["pensieri"]["estrattore"])
