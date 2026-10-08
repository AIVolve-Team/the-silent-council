import os

import pytest
from motore import Modello, Motore

from g1 import misure

NOME = os.environ.get("G1_MODELLO", "Qwen/Qwen3-0.6B")
REVISIONE = os.environ.get("G1_REVISIONE", "c1899de289a04d12100db370d81485cdf75e47ca")

pytestmark = pytest.mark.modello


@pytest.fixture(scope="module")
def motore():
    return Motore(Modello(NOME, REVISIONE), max_token_testo=16)


def test_il_testo_lungo_ha_almeno_i_token_chiesti(motore):
    testo = misure.testo_lungo(motore.modello.tokenizer, 4000)
    n = len(motore.modello.tokenizer(testo).input_ids)
    assert 4000 <= n < 4400


def test_le_misure_sul_testo_lungo(motore):
    risultato = misure.misura_motore(motore, token=600)
    assert risultato["token_letti_primo_agente"] >= 600
    assert risultato["kv_messaggio_gb"] > 0
    assert risultato["secondi_impronta"] > 0
    assert risultato["ricalcolo_identico"] is True  # in fp32 sul Mac la differenza è 0 (README del motore)
    assert risultato["fermata"] is None
