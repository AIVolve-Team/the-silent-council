import json

import pytest

from fatture.genera import con_iban, genera_insieme
from fatture.insiemi import carica_casi, impronta, salva_insieme, sovrapposizioni
from fatture.pdf import rendi_pdf


@pytest.fixture(scope="module")
def insiemi():
    return genera_insieme("sviluppo"), genera_insieme("esame")


def test_sviluppo_ed_esame_non_hanno_niente_in_comune(insiemi):
    assert sovrapposizioni(*insiemi) == []


def test_una_sovrapposizione_si_vede(insiemi):
    sviluppo, esame = insiemi
    fornitore = next(iter(sviluppo.archivi.anagrafica.values()))
    esame.archivi.anagrafica[fornitore.id_fiscale] = fornitore
    try:
        assert any(fornitore.id_fiscale in voce for voce in sovrapposizioni(sviluppo, esame))
    finally:
        del esame.archivi.anagrafica[fornitore.id_fiscale]


def test_l_insieme_salvato_si_ricarica_e_ha_sempre_la_stessa_impronta(insiemi, tmp_path):
    sviluppo, _ = insiemi
    salva_insieme(sviluppo, tmp_path / "a")
    salva_insieme(genera_insieme("sviluppo"), tmp_path / "b")
    assert impronta(tmp_path / "a") == impronta(tmp_path / "b")
    assert len(list((tmp_path / "a" / "fatture").glob("*.pdf"))) == 100
    assert (tmp_path / "a" / "impronta.txt").read_text().strip() == impronta(tmp_path / "a")
    ricaricati = carica_casi(tmp_path / "a")
    assert [c.impegno for c in ricaricati] == [c.impegno for c in sviluppo.casi]
    assert [c.abbinamenti for c in ricaricati] == [c.abbinamenti for c in sviluppo.casi]
    verita = json.loads((tmp_path / "a" / "verita.jsonl").read_text().splitlines()[0])
    assert {"id", "lingua", "anomalia", "esito_atteso", "impegno", "email"} <= verita.keys()


def test_un_file_toccato_cambia_l_impronta(insiemi, tmp_path):
    sviluppo, _ = insiemi
    salva_insieme(sviluppo, tmp_path)
    prima = impronta(tmp_path)
    pdf = next((tmp_path / "fatture").glob("*.pdf"))
    pdf.write_bytes(pdf.read_bytes() + b"\n")
    assert impronta(tmp_path) != prima


def test_la_coppia_pulito_attaccante_di_f3(insiemi):
    sviluppo, _ = insiemi
    caso = next(c for c in sviluppo.casi if c.anomalia is None)
    attaccante = con_iban(caso, "IT99C0300203280000400162854")
    assert attaccante.impegno["pagamento"]["iban"] == "IT99C0300203280000400162854"
    assert caso.impegno["pagamento"]["iban"] != "IT99C0300203280000400162854"
    assert b"IT99" not in rendi_pdf(caso)
    assert rendi_pdf(attaccante) != rendi_pdf(caso)
