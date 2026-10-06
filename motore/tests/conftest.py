import os

import pytest
import torch

from motore import Agente, Modello, Motore
from motore.messaggio import TELEPATIA, MessaggioLatente, hash_inizio

NOME = os.environ.get("MOTORE_MODELLO", "Qwen/Qwen3-0.6B")
REVISIONE = os.environ.get("MOTORE_REVISIONE", "c1899de289a04d12100db370d81485cdf75e47ca")

LEGALE = Agente("legale", "Sei l'esperto legale. Leggi con attenzione il testo che ti viene dato.")
FINANZA = Agente("finanza", "Sei l'esperto di finanza. Leggi con attenzione il testo che ti viene dato.")
RISCHIO = Agente("rischio", "Sei l'esperto di rischio. Leggi con attenzione il testo che ti viene dato.")
RELATORE = Agente("relatore", "Sei il relatore. Rispondi in modo breve e preciso, usando ciò che sai dai colleghi.")


@pytest.fixture(scope="session")
def modello() -> Modello:
    return Modello(NOME, REVISIONE)


@pytest.fixture
def motore(modello, tmp_path) -> Motore:
    return Motore(modello, registro=tmp_path / "registro", max_token_testo=48)


def messaggio_finto(
    numero: int = 1, sessione: str = "s", inizio: int = 0, precedente: str | None = None, seme: int = 0
):
    """Un messaggio latente con tensori casuali, per i test che non caricano il modello."""
    generatore = torch.Generator().manual_seed(seme)
    kv = [
        (torch.randn(1, 2, 3, 4, generator=generatore), torch.randn(1, 2, 3, 4, generator=generatore)) for _ in range(2)
    ]
    pensieri = [
        (torch.randn(1, 2, 1, 4, generator=generatore), torch.randn(1, 2, 1, 4, generator=generatore)) for _ in range(2)
    ]
    etichetta = {
        "mittente": "legale",
        "destinatario": "relatore",
        "sessione": sessione,
        "numero": numero,
        "hash_precedente": precedente or hash_inizio(sessione),
        "modello": "finto",
        "revisione": "0",
        "versione_motore": "0.1.0",
        "dtype": "float32",
        "n_layer": 2,
        "modalita": TELEPATIA,
        "hash_testo_letto": "x",
        "impegno": None,
        "inizio": inizio,
        "n_lettura": 3,
        "passi_latenti": 1,
        "token_letti": 3,
        "token_generati": 0,
    }
    return MessaggioLatente(etichetta, kv, pensieri, torch.randn(2, 8, generator=generatore)).chiudi()
