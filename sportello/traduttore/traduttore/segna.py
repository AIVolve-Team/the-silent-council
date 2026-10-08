"""Ciò che il traduttore calcola senza modello: le righe da segnare e la misura accanto a G3."""

from __future__ import annotations

import difflib
import re

SIMILE = 0.8  # sopra questa somiglianza due righe sono la stessa riga, scritta un po' diversa
PAROLE_VUOTE = {"and", "the", "with", "from", "srl", "spa", "ltd", "limited", "group", "della", "delle", "degli"}


def _simile(a: str, b: str) -> bool:
    return difflib.SequenceMatcher(None, a, b).ratio() > SIMILE


def segna(trascrizione: str, testo_pdf: str, nascoste: list[str]) -> list[dict]:
    """Le righe della trascrizione, ognuna con `nascosta` (nel PDF è testo nascosto) e `fuori_pdf` (nel PDF non c'è:
    per esempio la memoria di un estrattore compromesso, F3). Le righe vuote si tolgono."""
    pdf = [r.strip() for r in testo_pdf.splitlines() if r.strip()]
    nascoste = [n.strip() for n in nascoste if n.strip()]
    righe = []
    for riga in (r.strip() for r in trascrizione.splitlines()):
        if not riga:
            continue
        nascosta = any(_simile(riga, n) or n in riga for n in nascoste)
        fuori_pdf = not nascosta and not any(_simile(riga, v) or riga in v for v in pdf)
        righe.append({"testo": riga, "nascosta": nascosta, "fuori_pdf": fuori_pdf})
    return righe


def frazione_con_dati(pensieri: list[list[list]], dati: list[str]) -> float:
    """Accanto a G3, senza soglia: la frazione dei passi latenti con un dato vero fra i token più probabili del
    logit lens. Contano solo parole intere di 4+ lettere che non sono parole vuote e numeri di 3+ cifre: il prototipo
    contava pezzi di parola e dava falsi positivi (" de" dentro "Offredi", " And" dentro un nome)."""
    parole = {w.lower() for d in dati for w in re.findall(r"[A-Za-zÀ-ÿ]{4,}", d)} - PAROLE_VUOTE
    numeri = [re.sub(r"\D", "", d) for d in dati if re.search(r"\d{3,}", d)]
    if not pensieri:
        return 0.0

    def vero(token: str) -> bool:
        t = token.strip().lower()
        return (t.isalpha() and t in parole) or (len(t) >= 3 and t.isdigit() and any(t in n for n in numeri))

    return sum(any(vero(t) for t, _ in passo) for passo in pensieri) / len(pensieri)
