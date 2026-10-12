"""La confidenza di nota e verdetto, dai logprob dei token true e false.

Per ogni categoria si guarda il passo in cui il modello scrive il booleano dentro `segnalare`: la probabilità di
"sì" è p(true) / (p(true) + p(false)), con la distribuzione del modello prima del vincolo dello schema.
"""

from __future__ import annotations

import math
import re

from motore import Generazione

# Soglie provvisorie: si fissano sul set di sviluppo con Qwen3-14B.
SOGLIE = (0.9, 0.7)

_CHIAVE = re.compile(r'"([^"]+)"\s*:\s*$')


def token_booleani(tokenizer) -> tuple[list[int], list[int]]:
    """Gli id dei token che scrivono true e false, con e senza spazio prima."""

    def ids(parole: list[str]) -> list[int]:
        trovati = []
        for parola in parole:
            codifica = tokenizer.encode(parola, add_special_tokens=False)
            if len(codifica) == 1:
                trovati.append(codifica[0])
        return sorted(set(trovati))

    return ids(["true", " true"]), ids(["false", " false"])


def probabilita_si(generazione: Generazione, veri: list[int], falsi: list[int]) -> dict[str, float]:
    """Categoria → probabilità che vada segnalata, per i booleani scritti dentro `segnalare`."""
    risultato: dict[str, float] = {}
    testo = ""
    for passo in generazione.passi:
        # Dopo `segnalare` vengono `citazioni` (nota) o `dettagli` (verdetto): lì i booleani non ci sono più.
        dentro = '"segnalare"' in testo and '"citazioni"' not in testo and '"dettagli"' not in testo
        chiave = _CHIAVE.search(testo) if dentro else None
        # Il passo del booleano: subito dopo `"chiave": `, e il token scritto comincia con t o f.
        if chiave and passo.osservati and passo.testo.strip()[:1] in ("t", "f"):
            p_vero = sum(math.exp(passo.osservati[t]) for t in veri if t in passo.osservati)
            p_falso = sum(math.exp(passo.osservati[t]) for t in falsi if t in passo.osservati)
            if p_vero + p_falso > 0:
                risultato[chiave.group(1)] = p_vero / (p_vero + p_falso)
        testo += passo.testo
    return risultato


def livello(probabilita_si: float, segnalare: bool, soglie: tuple[float, float] = SOGLIE) -> str:
    """Alta, media o bassa, per la posizione scelta."""
    p = probabilita_si if segnalare else 1 - probabilita_si
    if p >= soglie[0]:
        return "alta"
    return "media" if p >= soglie[1] else "bassa"
