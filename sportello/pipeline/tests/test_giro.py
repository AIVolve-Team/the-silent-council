import json

import pytest
from fatture.genera import genera_insieme
from fatture.insiemi import salva_insieme

from pipeline import giro


@pytest.fixture(scope="module")
def cartella(tmp_path_factory):
    cartella = tmp_path_factory.mktemp("sviluppo")
    salva_insieme(genera_insieme("sviluppo"), cartella)
    return cartella


def test_una_fattura_che_va_in_errore_non_ferma_il_giro(cartella, tmp_path, monkeypatch):
    chiamate = []

    def esamina_finta(modello, pdf, email, archivi, chiavi, **opzioni):
        chiamate.append(opzioni["id_caso"])
        if len(chiamate) == 1:
            raise ValueError("month must be in 1..12")
        return {"id_caso": opzioni["id_caso"], "esito": "pagare", "token": {"generati": 1, "letti": 1}, "secondi": 0.1}

    monkeypatch.setattr(giro, "esamina", esamina_finta)
    righe = giro.esegui_giro(None, cartella, "telepatia", tmp_path, None, limite=2)
    assert [r["esito"] for r in righe] == ["errore", "pagare"]
    assert "month must be in 1..12" in righe[0]["errore"]
    assert len((tmp_path / "telepatia.jsonl").read_text().splitlines()) == 2
    assert json.loads((tmp_path / "telepatia.jsonl").read_text().splitlines()[0])["id"] == "sviluppo-0001"
