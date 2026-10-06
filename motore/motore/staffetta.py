"""La staffetta: gli agenti in fila, in telepatia o a testo, con gli stessi prompt."""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass

from .controllo import Esito
from .messaggio import TELEPATIA, MessaggioLatente
from .modello import Generazione
from .motore import Agente, Motore


@dataclass
class EsitoStaffetta:
    messaggi: list[MessaggioLatente]
    finale: Generazione | None
    fermata: Esito | None
    secondi: float

    @property
    def token_letti(self) -> int:
        return sum(m.etichetta["token_letti"] for m in self.messaggi) + (self.finale.token_letti if self.finale else 0)

    @property
    def token_generati(self) -> int:
        """Tutto quello che il modello scrive, note e verdetto compresi."""
        generati = sum(m.etichetta["token_generati"] for m in self.messaggi)
        return generati + (self.finale.token_generati if self.finale else 0)

    @property
    def posizioni_latenti(self) -> int:
        return sum(m.etichetta["passi_latenti"] for m in self.messaggi)


class Staffetta:
    def __init__(
        self,
        motore: Motore,
        agenti: list[Agente],
        ultimo: Agente,
        *,
        modalita: str = TELEPATIA,
        passi_latenti: int = 10,
    ) -> None:
        self.motore = motore
        self.agenti = agenti
        self.ultimo = ultimo
        self.modalita = modalita
        self.passi_latenti = passi_latenti

    def esegui(
        self,
        sessione: str,
        testi: dict[str, str],
        *,
        schema: dict | None = None,
        max_token: int | None = None,
        pensieri_da: dict[str, MessaggioLatente] | None = None,
        attacchi: dict[str, Callable[[MessaggioLatente], None]] | None = None,
    ) -> EsitoStaffetta:
        """Fa pensare gli agenti in ordine, consegna ogni messaggio e poi fa scrivere l'ultimo.

        `pensieri_da` sostituisce i pensieri di un agente con quelli di un altro messaggio (prova di «Eval pre-registrato»).
        `attacchi` manomette un messaggio dopo che è nato e prima della consegna (demo della macchina della verità).
        Se un controllo ferma un messaggio, la staffetta si ferma lì.
        """
        inizio = time.perf_counter()
        catena: list[MessaggioLatente] = []
        nomi = [a.nome for a in self.agenti] + [self.ultimo.nome]
        for i, agente in enumerate(self.agenti):
            messaggio = self.motore.pensa(
                agente,
                testi[agente.nome],
                catena,
                sessione=sessione,
                passi_latenti=self.passi_latenti,
                modalita=self.modalita,
                destinatario=nomi[i + 1],
            )
            if pensieri_da and agente.nome in pensieri_da:
                donatore = pensieri_da[agente.nome]
                origine = f"{donatore.etichetta['sessione']}#{donatore.etichetta['numero']}"
                messaggio = self.motore.ricalcola_pensieri(messaggio, catena, stati_da=donatore.stati, origine=origine)
            if attacchi and agente.nome in attacchi:
                attacchi[agente.nome](messaggio)
            consegna = self.motore.consegna(messaggio, catena)
            if not consegna.esito.passa:
                return EsitoStaffetta(catena, None, consegna.esito, time.perf_counter() - inizio)
            catena.append(consegna.copia)
        esito = self.motore.verifica_catena(catena)
        if not esito.passa:
            return EsitoStaffetta(catena, None, esito, time.perf_counter() - inizio)
        finale = self.motore.scrivi(
            self.ultimo, testi[self.ultimo.nome], catena, modalita=self.modalita, schema=schema, max_token=max_token
        )
        return EsitoStaffetta(catena, finale, None, time.perf_counter() - inizio)
