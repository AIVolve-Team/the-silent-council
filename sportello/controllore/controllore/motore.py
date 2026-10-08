"""Il controllo di coerenza da aggiungere al motore: `Motore(modello, controlli=[ControlloSigillo(…), ControlloCoerenza()])`.

Nel motore ogni agente dichiara in chiaro nel campo `impegno` della sua etichetta, che il sigillo copre:
per l'estrattore è l'impegno, per il verificatore è la lettura. Il controllo li confronta quando il messaggio del
verificatore sta per arrivare al decisore: se non coincidono la staffetta si ferma, e il decisore non riceve mai la
memoria che ha mentito. I campi vuoti non la fermano: decide una persona alla fine (`valuta`).
"""

from __future__ import annotations

from motore.controllo import Esito
from motore.messaggio import MessaggioLatente

from .coerenza import confronta
from .valuta import motivi_coerenza


class ControlloCoerenza:
    nome = "coerenza"

    def __init__(self, *, estrattore: str = "estrattore", verificatore: str = "verificatore", attivo: bool = True):
        self.estrattore = estrattore
        self.verificatore = verificatore
        # Spento solo in modalità demo, per mostrare cosa succede senza la macchina della verità.
        self.attivo = attivo

    def __call__(self, messaggio: MessaggioLatente, catena: list[MessaggioLatente]) -> Esito:
        if not self.attivo or messaggio.mittente != self.verificatore:
            return Esito(True, self.nome)
        estrattore = next((m for m in catena if m.mittente == self.estrattore), None)
        if estrattore is None:
            return Esito(
                False, self.nome, f"manca il messaggio dell'estrattore ({self.estrattore}) prima del verificatore"
            )
        discordanze, _ = confronta(estrattore.etichetta.get("impegno"), messaggio.etichetta.get("impegno"))
        if discordanze:
            return Esito(False, self.nome, "; ".join(m.motivo for m in motivi_coerenza(discordanze, [])))
        return Esito(True, self.nome)
