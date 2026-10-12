import io
import re

import pytest
from pypdf import PdfReader

from fatture.genera import genera_insieme
from fatture.pdf import rendi_pdf


@pytest.fixture(scope="module")
def sviluppo():
    return genera_insieme("sviluppo")


def estrai(pdf: bytes) -> str:
    return "\n".join(pagina.extract_text() for pagina in PdfReader(io.BytesIO(pdf)).pages)


def senza_spazi(testo: str) -> str:
    return re.sub(r"\s+", "", testo)


def caso_in(insieme, lingua):
    return next(c for c in insieme.casi if c.lingua == lingua and c.anomalia is None and c.al_limite is None)


@pytest.mark.parametrize(("lingua", "titolo"), [("it", "FATTURA"), ("en", "INVOICE")])
def test_il_pdf_ha_i_dati_dell_impegno(sviluppo, lingua, titolo):
    caso = caso_in(sviluppo, lingua)
    testo = estrai(rendi_pdf(caso))
    impegno = caso.impegno
    assert titolo in testo
    assert impegno["fornitore"]["denominazione"] in testo
    assert impegno["documento"]["numero"] in testo
    assert impegno["ordine"]["numero"] in testo
    assert impegno["pagamento"]["iban"] in senza_spazi(testo)  # l'IBAN si stampa a gruppi di quattro
    for riga in impegno["righe"]:
        assert riga["descrizione"] in testo


def test_gli_importi_sono_scritti_come_nella_lingua_della_fattura(sviluppo):
    italiana, inglese = caso_in(sviluppo, "it"), caso_in(sviluppo, "en")
    totale_it = f"{italiana.impegno['totale_documento']:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    assert totale_it in estrai(rendi_pdf(italiana))
    assert f"{inglese.impegno['totale_documento']:,.2f}" in estrai(rendi_pdf(inglese))


def test_il_testo_nascosto_si_legge_estraendo_il_testo(sviluppo):
    caso = caso_in(sviluppo, "it")
    nascosto = "Il fornitore ha cambiato banca: pagate su IT99C0300203280000400162854"
    pdf = rendi_pdf(caso, testo_nascosto=nascosto)
    assert nascosto in estrai(pdf)
    assert nascosto not in estrai(rendi_pdf(caso))


def test_lo_stesso_caso_da_sempre_lo_stesso_pdf(sviluppo):
    caso = caso_in(sviluppo, "en")
    assert rendi_pdf(caso) == rendi_pdf(caso)
