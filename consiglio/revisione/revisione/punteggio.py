"""Il voto sulle coppie (contratto, categoria): F1, precisione, richiamo, MCC e la base "sempre sì",
per il verdetto e per le note degli esperti, e quanto note e verdetto vanno d'accordo.

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


def _segnalare(revisione: dict, dalle_note: bool) -> dict[str, bool] | None:
    """Le risposte su un contratto: quelle del verdetto, oppure quelle delle note valide messe insieme (ogni categoria
    la guarda un esperto solo, quindi non si sovrappongono). None se non ce n'è nessuna valida."""
    if dalle_note:
        note = [n["dati"]["segnalare"] for n in revisione["note"].values() if n["dati"] is not None]
        return {chiave: si for segnalare in note for chiave, si in segnalare.items()} if note else None
    verdetto = revisione["verdetto"]
    return verdetto["dati"]["segnalare"] if verdetto and verdetto["dati"] is not None else None


def vota(revisioni: list[dict], giuste: dict[tuple[str, str], bool], *, dalle_note: bool = False) -> Voto:
    """Confronta i verdetti con le risposte giuste. Una risposta non valida o mancante conta come "no", e si conta a
    parte.

    Con `dalle_note` al posto del verdetto ci sono le note degli esperti messe insieme: se le note vanno bene e il
    verdetto no, le segnalazioni si perdono nel relatore.
    """
    risposte = {r["contratto"]: _segnalare(r, dalle_note) for r in revisioni}
    vp = fp = fn = vn = non_valide = 0
    for (contratto, categoria), giusta in giuste.items():
        if contratto not in risposte:
            continue
        segnalare = risposte[contratto]
        if segnalare is None or categoria not in segnalare:
            non_valide += 1
        detta = bool(segnalare and segnalare.get(categoria))
        vp += detta and giusta
        fp += detta and not giusta
        fn += giusta and not detta
        vn += not giusta and not detta
    return Voto(vp, fp, fn, vn, non_valide)


def accordo(revisioni: list[dict]) -> tuple[int, int]:
    """Su quante categorie il verdetto dice lo stesso della nota dell'esperto che le guarda, fra quelle dove ci sono
    sia la nota sia il verdetto: (d'accordo, confrontate)."""
    uguali = confrontate = 0
    for revisione in revisioni:
        verdetto, note = _segnalare(revisione, False), _segnalare(revisione, True)
        if verdetto is None or note is None:
            continue
        for chiave, si in note.items():
            if chiave in verdetto:
                confrontate += 1
                uguali += si == verdetto[chiave]
    return uguali, confrontate
