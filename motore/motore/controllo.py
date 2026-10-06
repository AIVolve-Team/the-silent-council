"""I controlli che girano dentro `consegna`: rispondono "passa" o "ferma, perché…".

Ogni controllo è una funzione (messaggio, catena già consegnata) → Esito. Sigillo e coerenza si
aggiungono alla lista del motore senza cambiare l'interfaccia.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from .messaggio import TELEPATIA, MessaggioLatente, hash_inizio, sha256


@dataclass(frozen=True)
class Esito:
    passa: bool
    controllo: str
    motivo: str = ""


Controllo = Callable[[MessaggioLatente, list[MessaggioLatente]], Esito]


class ControlloImpronta:
    """Senza perdite: i byte e l'etichetta sono quelli di quando il messaggio è nato."""

    nome = "impronta"

    def __call__(self, messaggio: MessaggioLatente, catena: list[MessaggioLatente]) -> Esito:
        attesi = messaggio.etichetta.get("hash_blocchi", {})
        for blocco, trovato in messaggio.hash_blocchi().items():
            if attesi.get(blocco) != trovato:
                return Esito(False, self.nome, f"blocco {blocco}: atteso {attesi.get(blocco)}, trovato {trovato}")
        trovata = sha256(messaggio.manifesto())
        if trovata != messaggio.etichetta.get("impronta"):
            return Esito(
                False,
                self.nome,
                f"etichetta cambiata: impronta attesa {messaggio.etichetta.get('impronta')}, trovata {trovata}",
            )
        return Esito(True, self.nome)


class ControlloCatena:
    """Il messaggio è il successivo giusto: stesso modello e stessa sessione, numero progressivo,
    hash del messaggio precedente e, in telepatia, posizione d'inizio subito dopo l'ultimo pezzo."""

    nome = "catena"

    def __init__(self, modello: str, revisione: str) -> None:
        self.modello = modello
        self.revisione = revisione

    def __call__(self, messaggio: MessaggioLatente, catena: list[MessaggioLatente]) -> Esito:
        e = messaggio.etichetta
        if (e["modello"], e["revisione"]) != (self.modello, self.revisione):
            return Esito(False, self.nome, f"modello diverso: {e['modello']}@{e['revisione']}")
        if catena and e["sessione"] != catena[0].etichetta["sessione"]:
            return Esito(False, self.nome, f"sessione diversa: {e['sessione']}")
        if catena and e["modalita"] != catena[0].etichetta["modalita"]:
            return Esito(False, self.nome, f"modalità diversa: {e['modalita']}")
        if e["numero"] != len(catena) + 1:
            return Esito(False, self.nome, f"numero {e['numero']}, atteso {len(catena) + 1}")
        precedente = catena[-1].impronta if catena else hash_inizio(e["sessione"])
        if e["hash_precedente"] != precedente:
            return Esito(
                False, self.nome, "hash del messaggio precedente sbagliato: messaggio rispedito o fuori ordine"
            )
        if e["modalita"] == TELEPATIA:
            inizio = sum(m.lunghezza for m in catena)
            if e["inizio"] != inizio:
                return Esito(False, self.nome, f"inizio {e['inizio']}, atteso {inizio}: un pezzo non si sposta")
            if (messaggio.n_lettura, messaggio.n_pensieri) != (e["n_lettura"], e["passi_latenti"]):
                return Esito(False, self.nome, "le posizioni non corrispondono all'etichetta")
        return Esito(True, self.nome)
