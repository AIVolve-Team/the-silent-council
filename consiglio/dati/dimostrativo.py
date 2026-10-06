"""Controlla il set dimostrativo del Consiglio e ne calcola l'hash.

Ogni contratto è un file `<nome>.txt` in `set-dimostrativo/`, accanto alla sua risposta attesa `<nome>.json` nel
formato di "Verdetto e dissenso": la raccomandazione, le 19 righe CUAD, il dissenso atteso e gli importi e le
date che il verdetto deve riportare giusti. Il set resta fuori dal repo fino alla consegna; nel repo va solo
`set-dimostrativo.sha256`, scritto con --hash dopo la revisione di una persona del team.
"""

import argparse
import hashlib
import json
from pathlib import Path

from categorie import CUAD_CATEGORIE

QUI = Path(__file__).resolve().parent
CARTELLA = QUI / "set-dimostrativo"
MANIFESTO = QUI / "set-dimostrativo.sha256"
RACCOMANDAZIONI = {"firmare", "negoziare", "non firmare"}
POSIZIONI = {"sì", "no"}


def errori(risposta: dict, testo: str) -> list[str]:
    """Gli errori di una risposta attesa rispetto al suo contratto; lista vuota se è valida."""
    trovati = []
    if risposta.get("raccomandazione") not in RACCOMANDAZIONI:
        trovati.append(f"raccomandazione non valida: {risposta.get('raccomandazione')!r}")
    if not risposta.get("motivazione"):
        trovati.append("manca la motivazione della raccomandazione")
    righe = risposta.get("righe", [])
    if [r.get("categoria") for r in righe] != list(CUAD_CATEGORIE):
        trovati.append("le righe devono essere le 19 categorie CUAD, nell'ordine di categorie.py")
    for riga in righe:
        categoria = riga.get("categoria")
        if CUAD_CATEGORIE.get(categoria) != riga.get("ruolo"):
            trovati.append(f"{categoria}: ruolo {riga.get('ruolo')!r} diverso da categorie.py")
        if riga.get("da_segnalare") is True:
            if not riga.get("citazione") or riga["citazione"] not in testo:
                trovati.append(f"{categoria}: la citazione non compare nel contratto")
            if not riga.get("motivazione"):
                trovati.append(f"{categoria}: manca la motivazione")
        elif riga.get("da_segnalare") is False:
            if riga.get("citazione") is not None:
                trovati.append(f"{categoria}: una riga a 'no' non ha citazione")
        else:
            trovati.append(f"{categoria}: da_segnalare deve essere true o false")
    for dissenso in risposta.get("dissenso_atteso", []):
        categoria = dissenso.get("categoria")
        if categoria not in CUAD_CATEGORIE or CUAD_CATEGORIE[categoria] != dissenso.get("ruolo"):
            trovati.append(f"dissenso atteso: categoria o ruolo non validi ({categoria})")
            continue
        nota, verdetto = dissenso.get("nota_attesa"), dissenso.get("verdetto_atteso")
        if {nota, verdetto} != POSIZIONI:
            trovati.append(f"dissenso atteso su {categoria}: nota e verdetto devono essere uno 'sì' e uno 'no'")
            continue
        if dissenso.get("tipo") != ("grave" if nota == "sì" else "lieve"):
            trovati.append(
                f"dissenso atteso su {categoria}: 'grave' se la nota dice sì e il verdetto no, altrimenti 'lieve'"
            )
        # Il dissenso è plausibile anche quando sbaglia il verdetto: chi ha ragione lo dice la riga.
        giusta = {r["categoria"]: r["da_segnalare"] for r in righe}.get(categoria)
        if dissenso.get("ha_ragione") != ("esperto" if (nota == "sì") == giusta else "verdetto"):
            trovati.append(f"dissenso atteso su {categoria}: 'ha_ragione' non coincide con la risposta giusta")
        if not dissenso.get("perche"):
            trovati.append(f"dissenso atteso su {categoria}: manca il perché")
    for valore in risposta.get("importi_e_date", []):
        if valore not in testo:
            trovati.append(f"importo o data che non compare nel contratto: {valore!r}")
    return trovati


def contratti() -> list[Path]:
    return sorted(CARTELLA.glob("*.txt"))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--hash", action="store_true", help="scrive set-dimostrativo.sha256 (dopo la revisione)")
    argomenti = parser.parse_args()

    if not contratti():
        raise SystemExit(f"Nessun contratto in {CARTELLA}.")
    totale = 0
    for contratto in contratti():
        risposta = json.loads(contratto.with_suffix(".json").read_text())
        problemi = errori(risposta, contratto.read_text())
        totale += len(problemi)
        segnalate = sum(r["da_segnalare"] for r in risposta["righe"])
        print(
            f"{contratto.stem}: {risposta['raccomandazione']}, {segnalate}/19 da segnalare, stato: {risposta['stato']}"
        )
        for problema in problemi:
            print(f"  - {problema}")
    if totale:
        raise SystemExit(f"{totale} problemi da correggere.")
    if argomenti.hash:
        righe = [
            f"{hashlib.sha256(f.read_bytes()).hexdigest()}  set-dimostrativo/{f.name}"
            for f in sorted(CARTELLA.iterdir())
            if f.suffix in {".txt", ".json"}
        ]
        MANIFESTO.write_text("\n".join(righe) + "\n")
        print(f"Scritto {MANIFESTO.name}: verificabile con `shasum -a 256 -c {MANIFESTO.name}`.")


if __name__ == "__main__":
    main()
