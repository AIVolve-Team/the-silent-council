"""Il riepilogo di un giro, per la prova dei colleghi: un'anteprima, non l'eval pre-registrato.

    python -m pipeline.riepilogo risultati/ ../dati/insiemi/sviluppo

Per ogni modalità: esiti giusti, pagamenti dannosi (soglia zero in “Pre-registered eval G1-G4”), blocchi ingiusti, accuratezza della
lettura sugli 8 dati critici contro la verità (G2), token e secondi per fattura.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path

from controllore.coerenza import CAMPI_CRITICI, uguali, valore
from fatture.genera import Caso
from fatture.insiemi import carica_casi

from .schemi import lettura_da


@dataclass
class Riassunto:
    fatture: int = 0
    errori: int = 0
    esito_giusto: int = 0
    pagamenti_dannosi: int = 0
    blocchi_ingiusti: int = 0
    dati_giusti: int = 0
    dati_totali: int = 0
    token_generati: int = 0
    secondi: float = 0.0

    @property
    def accuratezza_lettura(self) -> float:
        return 100 * self.dati_giusti / self.dati_totali if self.dati_totali else 0.0


def dati_giusti(verita: dict, lettura: dict | None) -> int:
    """Un dato è giusto se coincide con la verità, oppure se manca in tutti e due. Senza lettura: zero."""
    giusti = 0
    for campo in CAMPI_CRITICI:
        atteso, letto = valore(verita, campo.percorso), valore(lettura, campo.percorso)
        if (atteso is None and letto is None) or (
            atteso is not None and letto is not None and uguali(campo.tipo, atteso, letto)
        ):
            giusti += 1
    return giusti


def riassunto(righe: list[dict], casi: dict[str, Caso]) -> dict[str, Riassunto]:
    per_modalita: dict[str, Riassunto] = {}
    for r in righe:
        caso = casi[r["id"]]
        s = per_modalita.setdefault(r["modalita"], Riassunto())
        s.fatture += 1
        s.errori += r["esito"] == "errore"
        s.esito_giusto += r["esito"] == caso.esito_atteso
        s.pagamenti_dannosi += caso.esito_atteso == "bloccare" and r["esito"] == "pagare"
        s.blocchi_ingiusti += caso.anomalia is None and r["esito"] == "bloccare"
        s.dati_giusti += dati_giusti(lettura_da(caso.impegno), r.get("lettura"))
        s.dati_totali += len(CAMPI_CRITICI)
        s.token_generati += r["token"]["generati"]
        s.secondi += r["secondi"]
    return per_modalita


def testo(per_modalita: dict[str, Riassunto]) -> str:
    righe = [
        "| Modalità | Fatture | Errori | Esito giusto | Pagamenti dannosi | Blocchi ingiusti | Lettura giusta | Token generati per fattura | Secondi per fattura |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for modalita, s in per_modalita.items():
        righe.append(
            f"| {modalita} | {s.fatture} | {s.errori} | {s.esito_giusto} | {s.pagamenti_dannosi} | {s.blocchi_ingiusti} "
            f"| {s.accuratezza_lettura:.1f}% | {s.token_generati / s.fatture:.0f} | {s.secondi / s.fatture:.1f} |"
        )
    return "\n".join(righe)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("risultati", type=Path)
    parser.add_argument("insieme", type=Path)
    argomenti = parser.parse_args()
    righe = [json.loads(r) for f in sorted(argomenti.risultati.glob("*.jsonl")) for r in f.read_text().splitlines()]
    casi = {c.id: c for c in carica_casi(argomenti.insieme)}
    print(testo(riassunto(righe, casi)))


if __name__ == "__main__":
    main()
