"""Verifica dei messaggi latenti salvati: impronta, firma e catena, anche senza il motore.

Uso: python -m motore.verifica <cartella con i .safetensors> [--pubbliche <cartella delle chiavi pubbliche>]

Funziona anche sui file salvati senza KV: in quel caso controlla gli stati, il testo e l'etichetta, e la catena si
verifica lo stesso, perché ogni messaggio porta l'hash del precedente.
"""

from __future__ import annotations

import argparse
import sys
from collections import defaultdict
from pathlib import Path

from .controllo import Esito
from .messaggio import MessaggioLatente, hash_inizio, sha256
from .sigillo import ControlloSigillo, carica_pubbliche


def verifica_messaggio(messaggio: MessaggioLatente, sigillo: ControlloSigillo | None) -> Esito:
    if sha256(messaggio.manifesto()) != messaggio.etichetta.get("impronta"):
        return Esito(False, "impronta", "etichetta cambiata")
    attesi = messaggio.etichetta.get("hash_blocchi", {})
    trovati = messaggio.hash_blocchi()
    presenti = ["stati", "testo"] + (["lettura", "pensieri"] if messaggio.kv_lettura else [])
    for blocco in presenti:
        if attesi.get(blocco) != trovati[blocco]:
            return Esito(False, "impronta", f"blocco {blocco} cambiato")
    if sigillo is not None:
        return sigillo(messaggio, [])
    return Esito(True, "impronta")


def verifica_archivio(file: list[Path], pubbliche: Path | None = None) -> list[tuple[str, Esito]]:
    sigillo = ControlloSigillo(carica_pubbliche(pubbliche)) if pubbliche else None
    sessioni: dict[str, list[tuple[Path, MessaggioLatente]]] = defaultdict(list)
    for percorso in file:
        messaggio = MessaggioLatente.carica(percorso)
        sessioni[messaggio.etichetta["sessione"]].append((percorso, messaggio))
    risultati = []
    for sessione, voci in sorted(sessioni.items()):
        voci.sort(key=lambda voce: voce[1].etichetta["numero"])
        precedente = hash_inizio(sessione)
        for atteso, (percorso, messaggio) in enumerate(voci, start=1):
            esito = verifica_messaggio(messaggio, sigillo)
            if esito.passa and messaggio.etichetta["numero"] != atteso:
                esito = Esito(False, "catena", f"manca il messaggio {atteso}")
            elif esito.passa and messaggio.etichetta["hash_precedente"] != precedente:
                esito = Esito(False, "catena", "non segue il messaggio precedente")
            risultati.append((f"{sessione} #{messaggio.etichetta['numero']} ({percorso.name})", esito))
            precedente = messaggio.impronta
    return risultati


def main() -> None:
    parser = argparse.ArgumentParser(description="Verifica i messaggi latenti salvati.")
    parser.add_argument("cartella", type=Path)
    parser.add_argument("--pubbliche", type=Path, help="cartella delle chiavi pubbliche, per controllare le firme")
    argomenti = parser.parse_args()
    risultati = verifica_archivio(sorted(argomenti.cartella.glob("*.safetensors")), argomenti.pubbliche)
    for nome, esito in risultati:
        print(f"{'ok   ' if esito.passa else 'FERMO'} {nome}" + ("" if esito.passa else f": {esito.motivo}"))
    if not risultati:
        print("Nessun messaggio trovato.")
    sys.exit(0 if risultati and all(esito.passa for _, esito in risultati) else 1)


if __name__ == "__main__":
    main()
