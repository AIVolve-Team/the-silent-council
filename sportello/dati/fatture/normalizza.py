"""I formati di "L'impegno": lo stesso dato si scrive sempre allo stesso modo, così le regole e la
coerenza non trovano discordanze false."""

from __future__ import annotations

import re
from decimal import ROUND_HALF_UP, Decimal

CENTESIMO = Decimal("0.01")


def numero_documento(numero: str) -> str:
    """Come in A01: `FT/0012/2026` = `ft 12 2026`. Minuscole, separatori come spazi, niente zeri iniziali."""
    pezzi = re.findall(r"[a-z]+|\d+", numero.lower())
    return " ".join(str(int(p)) if p.isdigit() else p for p in pezzi)


def iban(valore: str) -> str:
    return re.sub(r"\s+", "", valore).upper()


def id_fiscale(valore: str) -> str:
    """Partita IVA o identificativo estero con il prefisso del paese, senza spazi né punti."""
    return re.sub(r"[^0-9A-Za-z]", "", valore).upper()


def importo(valore) -> Decimal:
    return Decimal(str(valore)).quantize(CENTESIMO, rounding=ROUND_HALF_UP)


def stesso_importo(a, b) -> bool:
    """±0,01 €, come i totali in “Anomaly catalogue” e gli importi in “Coherence rules”."""
    return abs(importo(a) - importo(b)) <= CENTESIMO
