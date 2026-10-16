"""Le configurazioni di confronto dell'eval e i pensieri scambiati, con Qwen3-0.6B su un contratto breve."""

import pytest
from motore import Modello, Motore

from revisione import BENCHMARK, Consiglio
from revisione.configurazioni import AgenteSolo, VotoFraQuattro
from revisione.esegui import MODELLI

from .test_consiglio import CONTRATTO

pytestmark = pytest.mark.modello

ALTRO = CONTRATTO.replace("componenti meccanici", "imballaggi").replace("€ 50.000,00", "€ 20.000,00")


@pytest.fixture(scope="module")
def motore():
    return Motore(Modello("Qwen/Qwen3-0.6B", MODELLI["Qwen/Qwen3-0.6B"]))


def test_agente_solo_e_voto_fra_quattro(motore):
    for classe in (AgenteSolo, VotoFraQuattro):
        riga = classe(motore, BENCHMARK["dimostrativo"]).revisiona("prova", CONTRATTO)
        dati = riga["verdetto"]["dati"]
        assert dati is not None and len(dati["segnalare"]) == 19 and "obiezioni" not in dati
        assert riga["modalita"] == classe.configurazione and riga["token_generati"] > 0
    assert len(riga["voti"]) == 4
    assert riga["token_generati"] == sum(v["token_generati"] for v in riga["voti"].values())


def test_pensieri_di_un_altro_contratto(motore):
    consiglio = Consiglio(motore, BENCHMARK["dimostrativo"], passi_latenti=2)
    consiglio.revisiona("altro", ALTRO)
    donatori = consiglio.pensieri
    assert set(donatori) == {"legale", "finanza", "rischio"}
    assert all(p.stati.shape[0] == 3 and p.stati.device.type == "cpu" for p in donatori.values())
    revisione = consiglio.revisiona("prova", CONTRATTO, pensieri_da=donatori)
    assert revisione.fermata is None and revisione.verdetto.valido
