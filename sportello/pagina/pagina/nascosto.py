"""Le righe di testo nascosto di un PDF, per il pulsante "mostra testo nascosto" della pagina del caso.

Si riconoscono dal corpo del carattere (sotto i 3 punti): è il modo in cui le fatture di prova nascondono il testo
, insieme al bianco su bianco. Serve **solo a mostrarlo** alla persona dopo il blocco: lo Sportello non decide
mai da qui. Se bloccasse ogni fattura con testo minuscolo, fermerebbe gli attacchi con un controllo fra file e la
macchina della verità non servirebbe (lo stesso ragionamento di «Catalogo delle anomalie» sull'XML).
"""

from __future__ import annotations

import io

from pypdf import PdfReader

CORPO_MASSIMO = 3.0


def righe_nascoste(pdf: bytes) -> list[str]:
    righe: list[str] = []

    def guarda(testo, cm, tm, font, corpo):
        scala = abs(tm[0]) if tm else 1.0
        if testo.strip() and corpo and corpo * scala < CORPO_MASSIMO:
            righe.append(testo.strip())

    for pagina in PdfReader(io.BytesIO(pdf)).pages:
        pagina.extract_text(visitor_text=guarda)
    return righe
