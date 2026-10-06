"""Il voto sulle coppie (contratto, categoria): F1, precisione, richiamo, MCC e la base "sempre sì".

Una versione minima, per la taratura dei passi latenti sul set di sviluppo. L'eval completo è di «Eval del Consiglio».
"""

from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass
class Voto:
    vp: int
    fp: int
    fn: int
    vn: int
    non_valide: int

    @property
    def f1(self) -> float:
        return 100 * 2 * self.vp / (2 * self.vp + self.fp + self.fn) if self.vp else 0.0

    @property
    def precisione(self) -> float:
        return 100 * self.vp / (self.vp + self.fp) if self.vp + self.fp else 0.0

    @property
    def richiamo(self) -> float:
        return 100 * self.vp / (self.vp + self.fn) if self.vp + self.fn else 0.0

    @property
    def mcc(self) -> float:
        numeratore = self.vp * self.vn - self.fp * self.fn
        denominatore = math.sqrt((self.vp + self.fp) * (self.vp + self.fn) * (self.vn + self.fp) * (self.vn + self.fn))
        return numeratore / denominatore if denominatore else 0.0

    @property
    def f1_sempre_si(self) -> float:
        positivi, totale = self.vp + self.fn, self.vp + self.fp + self.fn + self.vn
        return 100 * 2 * positivi / (positivi + totale) if positivi else 0.0


def vota(revisioni: list[dict], giuste: dict[tuple[str, str], bool]) -> Voto:
    """Confronta i verdetti con le risposte giuste. Un verdetto non valido o mancante conta come "no" su tutte le
    sue coppie, e si conta a parte."""
    verdetti = {r["contratto"]: r["verdetto"] for r in revisioni}
    vp = fp = fn = vn = non_valide = 0
    for (contratto, categoria), giusta in giuste.items():
        if contratto not in verdetti:
            continue
        verdetto = verdetti[contratto]
        dati = verdetto["dati"] if verdetto else None
        if dati is None:
            non_valide += 1
        detta = bool(dati and dati["segnalare"].get(categoria))
        vp += detta and giusta
        fp += detta and not giusta
        fn += giusta and not detta
        vn += not giusta and not detta
    return Voto(vp, fp, fn, vn, non_valide)
