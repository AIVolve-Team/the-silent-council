import json
import os

import pytest
from motore import Modello, Motore

from g1.esegui import esegui_giro
from g1.gsm8k import carica_problemi

NOME = os.environ.get("G1_MODELLO", "Qwen/Qwen3-0.6B")
REVISIONE = os.environ.get("G1_REVISIONE", "c1899de289a04d12100db370d81485cdf75e47ca")

pytestmark = pytest.mark.modello


@pytest.fixture(scope="module")
def motore():
    return Motore(Modello(NOME, REVISIONE), max_token_testo=24)


def test_i_tre_modi_su_un_problema_e_la_ripresa(motore, tmp_path):
    problemi = carica_problemi(1)
    righe = {
        modo: esegui_giro(motore, modo, problemi, tmp_path / f"{modo}.jsonl", max_token_risposta=48)
        for modo in ("testo", "telepatia", "senza_pensieri")
    }

    for modo, (riga,) in righe.items():
        assert riga["id"] == "gsm8k-test-0000"
        assert riga["modo"] == modo
        assert riga["risposta_giusta"] == "18"
        assert riga["corretto"] in (True, False)
        assert riga["fermata"] is None
    assert righe["testo"][0]["token_generati"] > righe["telepatia"][0]["token_generati"]
    assert righe["telepatia"][0]["posizioni_latenti"] == 30
    assert righe["senza_pensieri"][0]["posizioni_latenti"] == 0
    assert righe["testo"][0]["troncati"] >= 1  # con 24 token per agente almeno un messaggio si tronca

    file = tmp_path / "telepatia.jsonl"
    di_nuovo = esegui_giro(motore, "telepatia", problemi, file, max_token_risposta=48)
    assert di_nuovo == righe["telepatia"]
    assert len(file.read_text().splitlines()) == 1
    assert json.loads(file.read_text())["id"] == "gsm8k-test-0000"
