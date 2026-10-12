"""La parte del Consiglio nel sito per i giudici, senza modello."""

import json
from pathlib import Path

import pytest

from revisione.vetrina import Privato, scrivi_vetrina

ESEMPIO = Path(__file__).parents[1] / "pagina" / "esempio-revisione.json"


def giro(tmp_path, **cambi):
    revisione = json.loads(ESEMPIO.read_text()) | cambi
    f = tmp_path / f"giro-{revisione['benchmark']}.jsonl"
    f.write_text(json.dumps(revisione) + "\n")
    return f


def test_il_set_dimostrativo_non_esce_prima_della_consegna(tmp_path):
    with pytest.raises(Privato, match="private until delivery"):
        scrivi_vetrina([giro(tmp_path)], tmp_path / "vetrina", registrato=None)
    assert not (tmp_path / "vetrina").exists()


def test_indice_e_pagine(tmp_path):
    uscita = tmp_path / "vetrina"
    n = scrivi_vetrina(
        [giro(tmp_path, benchmark="cuad", contratto="ESEMPIO-SUPPLY AGREEMENT")], uscita, registrato="oggi"
    )
    assert n == 1
    indice = (uscita / "index.html").read_text()
    dati = json.loads(indice.split('<script id="dati" type="application/json">')[1].split("</script>")[0])
    voce = dati["verdetti"][0]
    assert dati["registrato"] == "oggi" and voce["raccomandazione"] == "negoziare" and voce["categorie"] == 19
    assert voce["sigillo_integro"] and (uscita / voce["pagina"]).exists()
    assert "citazione" not in json.dumps(voce)  # nell'indice solo conteggi, niente frasi del contratto
