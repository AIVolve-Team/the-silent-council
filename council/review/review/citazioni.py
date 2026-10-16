"""Ogni citazione si cerca parola per parola nel contratto.

Una citazione che non c'è è inventata: la persona la vede segnalata, e la versione severa del voto non la conta.
Il confronto ignora maiuscole, spazi, virgolette e apostrofi tipografici, e i puntini di un taglio.
"""

from __future__ import annotations

import re

_SOSTITUZIONI = str.maketrans({"’": "'", "‘": "'", "“": '"', "”": '"', "«": '"', "»": '"', "–": "-", "—": "-"})


def normalizza(testo: str) -> str:
    testo = testo.translate(_SOSTITUZIONI).lower()
    return re.sub(r"\s+", " ", testo).strip()


def trovata(citazione: str, contratto: str) -> bool:
    """Ogni pezzo della citazione (separati da "..." o "…") compare nel contratto. Le citazioni di meno di tre parole
    non contano come prova."""
    pezzi = [p.strip(" \"'.,;:") for p in re.split(r"\.{3}|…", normalizza(citazione))]
    pezzi = [p for p in pezzi if p]
    if not pezzi or sum(len(p.split()) for p in pezzi) < 3:
        return False
    testo = normalizza(contratto)
    return all(p in testo for p in pezzi)


def verifica(dati: dict | None, contratto: str) -> dict[str, bool]:
    """Categoria → la citazione di nota o verdetto compare nel contratto."""
    if not dati:
        return {}
    voci = dati.get("citazioni") or dati.get("dettagli") or []
    return {v["categoria"]: trovata(v.get("testo") or v.get("citazione") or "", contratto) for v in voci}
