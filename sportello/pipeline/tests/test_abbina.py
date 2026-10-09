"""L'abbinatore cieco (F7 di «Catalogo degli attacchi»): abbina all'ordine le righe senza riferimento vedendo solo le righe estratte e
l'ordine, mai la memoria del documento, dove può esserci una nota nascosta. Un motore finto registra le chiamate."""

import json

from fatture.archivi import Ordine, RigaOrdine
from motore.modello import Generazione

from pipeline.sportello import Conteggio, abbina

ORDINE = Ordine("PO-2026-0042", "IT01234567890", "2026-08-30", [RigaOrdine(1, "ART-7", "Toner nero", 10, 12.5, 22, 10)])
LIBERE = [{"n": 2, "num_item": None, "codice": None, "descrizione": "Cartuccia toner nera", "quantita": 1,
           "prezzo_unitario": 12.5, "prezzo_totale": 12.5, "aliquota": 22}]  # fmt: skip


class MotoreFinto:
    def __init__(self, risposta: str):
        self.risposta, self.chiamate = risposta, []

    def scrivi(self, agente, testo, ricevuti, **opzioni):
        self.chiamate.append({"agente": agente.nome, "testo": testo, "ricevuti": ricevuti, **opzioni})
        return Generazione(self.risposta, [], token_letti=100)


def test_l_abbinatore_non_riceve_la_memoria_del_documento():
    motore = MotoreFinto(json.dumps({"abbinamenti": [{"riga": 2, "riga_ordine": 1}]}))

    abbinamenti = abbina(motore, ORDINE, LIBERE, Conteggio(), modalita="telepatia")

    assert abbinamenti == {2: 1}
    (chiamata,) = motore.chiamate
    assert chiamata["ricevuti"] == []  # nessun messaggio latente, quindi nessun testo della fattura, nascosto compreso
    assert "Toner nero" in chiamata["testo"] and "Cartuccia toner nera" in chiamata["testo"]


def test_senza_righe_libere_non_si_chiama_nessuno_e_una_risposta_interrotta_passa_a_una_persona():
    motore = MotoreFinto('{"abbinamenti": [{"riga": 2, "riga_or')

    assert abbina(motore, ORDINE, [], Conteggio(), modalita="telepatia") == {}
    assert abbina(motore, ORDINE, LIBERE, Conteggio(), modalita="telepatia") == {2: None}  # A11: decide una persona
    assert len(motore.chiamate) == 1
