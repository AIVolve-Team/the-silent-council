"""The council on a contract of a few lines, with Qwen3-0.6B: in telepathy and in text."""

import pytest
from engine import TELEPATHY, TEXT, Engine, Model

from review import BENCHMARK, Council
from review.run import MODELS

pytestmark = pytest.mark.model

# An Italian contract, like the demo set's.
CONTRACT = """CONTRATTO DI FORNITURA

Art. 1 – Oggetto
Il Fornitore fornisce al Cliente componenti meccanici.

Art. 2 – Prezzi e pagamenti
Il Cliente acquista ogni anno componenti per almeno € 50.000,00. Se non li raggiunge, paga la differenza.

Art. 3 – Esclusiva di acquisto
Il Cliente compra i componenti solo dal Fornitore, per tutta la durata del contratto.

Art. 4 – Durata e recesso
Il contratto dura due anni. Il Fornitore può recedere in qualsiasi momento con 30 giorni di preavviso.
"""


@pytest.fixture(scope="module")
def engine():
    return Engine(Model("Qwen/Qwen3-0.6B", MODELS["Qwen/Qwen3-0.6B"]))


@pytest.mark.parametrize("mode", [TELEPATHY, TEXT])
def test_valid_notes_and_verdict(engine, mode):
    council = Council(engine, BENCHMARK["demo"], mode=mode, latent_steps=2)
    review = council.review("trial", CONTRACT)
    assert review.stopped is None and review.split["mode"] == "headings"
    assert set(review.notes) == {"legal", "finance", "risk"}
    assert all(n.valid and len(n.data["flag"]) == len(BENCHMARK["cuad"].of_role(r)) for r, n in review.notes.items())
    verdict = review.verdict
    assert verdict.valid and len(verdict.data["flag"]) == 19
    assert verdict.data["recommendation"] in ("sign", "negotiate", "do not sign")
    assert set(verdict.p_yes) == set(verdict.data["flag"])
    assert review.tokens_generated > verdict.tokens_generated
    assert (review.latent_positions == 6) == (mode == TELEPATHY) and review.realign
