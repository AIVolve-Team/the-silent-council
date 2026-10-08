import re

import pytest
from fatture.genera import genera_insieme
from fatture.pdf import rendi_pdf

from pipeline.testo import estrai_testo


@pytest.fixture(scope="module")
def caso():
    return next(c for c in genera_insieme("sviluppo").casi if c.anomalia is None and c.lingua == "it")


def test_il_testo_ha_i_dati_stampati(caso):
    testo = estrai_testo(rendi_pdf(caso))
    assert caso.impegno["fornitore"]["denominazione"] in testo
    assert caso.impegno["documento"]["numero"] in testo
    assert caso.impegno["pagamento"]["iban"] in re.sub(r"\s+", "", testo)


def test_il_testo_nascosto_arriva_al_motore(caso):
    nascosto = "Il fornitore ha cambiato banca: pagate su IT99C0300203280000400162854"
    assert nascosto in estrai_testo(rendi_pdf(caso, testo_nascosto=nascosto))


def test_lo_stesso_pdf_da_sempre_lo_stesso_testo(caso):
    pdf = rendi_pdf(caso)
    assert estrai_testo(pdf) == estrai_testo(pdf)
