"""I prompt del Consiglio, in italiano. Gli stessi in telepatia e a testo: cambia solo il canale.

In telepatia l'esperto legge la sua parte e "pensa" l'analisi nei passi latenti; a testo la scrive. Il relatore non
legge il contratto: lo conosce solo da ciò che riceve dai colleghi.
"""

from __future__ import annotations

from .categorie import NOMI_RUOLI, Benchmark, Categoria

CLIENTE = "una piccola impresa italiana, cliente del contratto"


def _elenco(categorie: tuple[Categoria, ...]) -> str:
    return "\n".join(f'- "{c.chiave}" ({c.nome}): {c.descrizione}' for c in categorie)


def istruzioni_esperto(ruolo: str, benchmark: Benchmark) -> str:
    colleghi = ", ".join(r for r in benchmark.lettori if r != ruolo)
    return (
        f"Sei l'esperto {NOMI_RUOLI[ruolo]} di un consiglio che rivede un contratto per conto di {CLIENTE}. "
        f"Leggi solo la tua parte del contratto: le altre le leggono i colleghi ({colleghi}), e il relatore "
        "riceve la memoria di tutti.\n\n"
        f"Le categorie di tua competenza. Per ognuna, {benchmark.regola}.\n{_elenco(benchmark.del_ruolo(ruolo))}"
    )


def lettura(sezione: str) -> str:
    parte = sezione.strip() or "(In questo contratto non ci sono clausole della tua parte.)"
    return (
        f"La tua parte del contratto:\n\n{parte}\n\n"
        "Scrivi per i colleghi un'analisi breve: per ogni categoria di tua competenza, se c'è una clausola da "
        "segnalare e con quali parole esatte del contratto; poi gli importi, le date e le parti che contano."
    )


def nota(sezione: str | None = None) -> str:
    """La nota per la persona. A testo l'esperto non ha la sua parte in memoria, quindi la rilegge."""
    inizio = "" if sezione is None else f"La tua parte del contratto:\n\n{sezione.strip()}\n\n"
    return inizio + (
        "Ora scrivi la tua nota in JSON.\n"
        '- "segnalare": per ogni categoria di tua competenza, true se va segnalata, false altrimenti.\n'
        '- "citazioni": al massimo 3, per le categorie a true più importanti: le parole esatte del contratto, '
        "copiate senza cambiarle, al massimo 20.\n"
        '- "importi_date_parti": al massimo 4 tra importi, date e parti che contano.'
    )


def istruzioni_relatore(benchmark: Benchmark) -> str:
    colleghi = ", ".join(benchmark.lettori)
    return (
        f"Sei il relatore, l'avvocato del diavolo di un consiglio che rivede un contratto per conto di {CLIENTE}. "
        f"Non hai letto il contratto: lo conosci solo da ciò che ricevi dai colleghi ({colleghi}), che ne hanno "
        "letto una parte ciascuno. Giudichi tutte le categorie, con equilibrio: segnala ciò che c'è, non ciò che "
        "manca.\n\n"
        f"Le categorie. Per ognuna, {benchmark.regola}.\n{_elenco(benchmark.categorie)}"
    )


def verdetto(*, traduci: bool = False) -> str:
    traduzione = (
        " Se una citazione non è in italiano, aggiungi la traduzione italiana tra parentesi." if traduci else ""
    )
    return (
        "Scrivi il verdetto in JSON, in quest'ordine.\n"
        '1. "obiezioni": prima di decidere, le obiezioni al parere dei colleghi: dove potrebbero sbagliarsi o cosa '
        "potrebbero aver mancato, con la categoria. Se non ce ne sono, lascia l'elenco vuoto.\n"
        '2. "segnalare": per ogni categoria, true se va segnalata, false altrimenti.\n'
        '3. "dettagli": al massimo 8, per le categorie a true: la "citazione", cioè le parole esatte del contratto '
        f'copiate senza cambiarle (al massimo 20), e la "motivazione", una riga in italiano sul perché conta per il '
        f"cliente.{traduzione}\n"
        '4. "raccomandazione": "firmare", "negoziare" o "non firmare", per il cliente.\n'
        '5. "motivazione": il perché della raccomandazione, con le categorie che pesano.'
    )
