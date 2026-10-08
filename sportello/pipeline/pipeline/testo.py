"""Dal PDF al testo: lo fa il motore, partendo dall'allegato originale, in modo deterministico.

L'estrazione legge anche il testo bianco su bianco e in corpo minuscolo: senza, l'attacco 2 della demo non arriverebbe
al motore. È un'estrazione di testo, non una lettura dell'immagine: le fatture scansionate restano fuori.
"""

from __future__ import annotations

import io

from pypdf import PdfReader


def estrai_testo(pdf: bytes) -> str:
    return "\n".join(pagina.extract_text() or "" for pagina in PdfReader(io.BytesIO(pdf)).pages).strip()
