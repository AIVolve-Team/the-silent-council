"""Le prove dal vivo dei giudici: il giudice sceglie un contratto da un elenco, mai un testo qualsiasi.

Così la GPU non esamina testi di chiunque e ogni verdetto ha il confronto con gli esperti. Il catalogo ha i contratti
CUAD del campione (servono i file di `dati/cache`, che `prepara.py` scarica) e, solo alla consegna, il set
dimostrativo. La chiave di un contratto è "<benchmark>:<id>".

I contratti di test si aggiungono solo dopo l'esame pre-registrato: prima, farli girare dal vivo vorrebbe dire
guardare il test.
"""

from __future__ import annotations

from collections.abc import Callable

from .dati import contratti, risposte_esperti
from .vetrina import FONTI, attese_dimostrativo, titolo_cuad, titolo_di

INSIEMI = ("sviluppo", "test")


def catalogo(
    insiemi: tuple[str, ...] = ("sviluppo",),
    *,
    con_dimostrativo: bool = False,
    lunghezza: Callable[[str], int] | None = None,
    max_token: int | None = None,
) -> dict[str, dict]:
    """chiave → benchmark, id, insieme, testo, titolo, risposte degli esperti e fonte. Con `max_token` (e la
    `lunghezza` in token di un testo) restano fuori i contratti troppo lunghi, come in `revisione.esegui`."""
    if fuori := sorted(set(insiemi) - set(INSIEMI)):
        raise ValueError(f"insiemi sconosciuti: {', '.join(fuori)}")
    entro = (
        (lambda testo: True) if not max_token or lunghezza is None else (lambda testo: lunghezza(testo) <= max_token)
    )
    voci = {}
    esperti = risposte_esperti("cuad")
    for insieme in insiemi:
        for cid, testo in contratti("cuad", insieme):
            if entro(testo):
                voci[f"cuad:{cid}"] = {
                    "benchmark": "cuad",
                    "contratto": cid,
                    "insieme": insieme,
                    "testo": testo,
                    "titolo": titolo_cuad(cid),
                    "esperti": esperti.get(cid),
                    "fonte": FONTI["cuad"],
                }
    if con_dimostrativo:
        testi, attese = attese_dimostrativo()
        for cid, testo in testi.items():
            if entro(testo):
                voci[f"dimostrativo:{cid}"] = {
                    "benchmark": "dimostrativo",
                    "contratto": cid,
                    "insieme": "dimostrativo",
                    "testo": testo,
                    "titolo": titolo_di({"contratto": cid, "benchmark": "dimostrativo"}, testi),
                    "esperti": attese.get(cid),
                    "fonte": FONTI["dimostrativo"],
                }
    return voci


def elenco(voci: dict[str, dict]) -> list[dict]:
    """Quello che il giudice vede per scegliere: chiave, titolo e da dove viene. Il testo resta sul server."""
    return [
        {"chiave": k, "titolo": v["titolo"], "benchmark": v["benchmark"], "insieme": v["insieme"]}
        for k, v in voci.items()
    ]
