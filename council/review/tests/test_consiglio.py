"""Il Consiglio su un contratto di poche righe, con Qwen3-0.6B: in telepatia e a testo."""

import pytest
from motore import TELEPATIA, TESTO, Modello, Motore

from revisione import BENCHMARK, Consiglio
from revisione.esegui import MODELLI

pytestmark = pytest.mark.modello

CONTRATTO = """CONTRATTO DI FORNITURA

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
def motore():
    return Motore(Modello("Qwen/Qwen3-0.6B", MODELLI["Qwen/Qwen3-0.6B"]))


@pytest.mark.parametrize("modalita", [TELEPATIA, TESTO])
def test_note_e_verdetto_validi(motore, modalita):
    consiglio = Consiglio(motore, BENCHMARK["dimostrativo"], modalita=modalita, passi_latenti=2)
    revisione = consiglio.revisiona("prova", CONTRATTO)
    assert revisione.fermata is None and revisione.taglio["modo"] == "titoli"
    assert set(revisione.note) == {"legale", "finanza", "rischio"}
    assert all(
        n.valido and len(n.dati["segnalare"]) == len(BENCHMARK["cuad"].del_ruolo(r)) for r, n in revisione.note.items()
    )
    verdetto = revisione.verdetto
    assert verdetto.valido and len(verdetto.dati["segnalare"]) == 19
    assert verdetto.dati["raccomandazione"] in ("firmare", "negoziare", "non firmare")
    assert set(verdetto.probabilita_si) == set(verdetto.dati["segnalare"])
    assert revisione.token_generati > verdetto.token_generati
    assert (revisione.posizioni_latenti == 6) == (modalita == TELEPATIA) and revisione.riallineamento
