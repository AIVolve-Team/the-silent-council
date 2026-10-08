"""Gli insiemi su disco: archivi, verità, PDF e impronta.

    python -m fatture.insiemi                 # genera sviluppo ed esame in insiemi/, controlla che non abbiano
                                              # niente in comune e stampa le impronte

L'impronta dell'esame va scritta su “Pre-registered eval G1-G4” appena generato, prima di qualunque misura.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from dataclasses import asdict
from pathlib import Path

from .archivi import Archivi
from .genera import Caso, Insieme, genera_insieme
from .normalizza import iban, id_fiscale, numero_documento
from .pdf import rendi_pdf


def salva_insieme(insieme: Insieme, cartella: Path) -> str:
    insieme.archivi.salva(cartella)
    (cartella / "cliente.json").write_text(json.dumps(insieme.cliente, indent=1, ensure_ascii=False) + "\n")
    fatture = cartella / "fatture"
    fatture.mkdir(parents=True, exist_ok=True)
    with (cartella / "verita.jsonl").open("w") as f:
        for caso in insieme.casi:
            f.write(json.dumps(asdict(caso), ensure_ascii=False) + "\n")
            (fatture / f"{caso.id}.pdf").write_bytes(rendi_pdf(caso))
    valore = impronta(cartella)
    (cartella / "impronta.txt").write_text(valore + "\n")
    return valore


def carica_casi(cartella: Path) -> list[Caso]:
    casi = []
    for riga in (cartella / "verita.jsonl").read_text().splitlines():
        dati = json.loads(riga)
        dati["abbinamenti"] = {int(k): v for k, v in dati["abbinamenti"].items()}
        casi.append(Caso(**dati))
    return casi


def carica_archivi(cartella: Path) -> Archivi:
    return Archivi.carica(cartella)


def impronta(cartella: Path) -> str:
    """SHA-256 dell'elenco ordinato dei file con il loro SHA-256: cambia se cambia anche un solo byte."""
    elenco = hashlib.sha256()
    for file in sorted(p for p in cartella.rglob("*") if p.is_file() and p.name != "impronta.txt"):
        voce = f"{file.relative_to(cartella).as_posix()} {hashlib.sha256(file.read_bytes()).hexdigest()}\n"
        elenco.update(voce.encode("utf-8"))
    return elenco.hexdigest()


def chiavi(insieme: Insieme) -> dict[str, set[str]]:
    fornitori = {id_fiscale(i) for i in insieme.archivi.anagrafica}
    fornitori |= {id_fiscale(c.impegno["fornitore"]["id_fiscale"]) for c in insieme.casi}
    conti = {iban(f.iban) for f in insieme.archivi.anagrafica.values()}
    conti |= {iban(c.impegno["pagamento"]["iban"]) for c in insieme.casi if c.impegno["pagamento"]["iban"]}
    fatture = {
        f"{id_fiscale(c.impegno['fornitore']['id_fiscale'])} {numero_documento(c.impegno['documento']['numero'])}"
        for c in insieme.casi
    }
    return {"fornitore": fornitori, "IBAN": conti, "fattura": fatture}


def sovrapposizioni(a: Insieme, b: Insieme) -> list[str]:
    """Fornitori, IBAN o fatture che stanno in tutti e due gli insiemi: devono essere zero."""
    ka, kb = chiavi(a), chiavi(b)
    return [f"{tipo} {valore} in {a.nome} e {b.nome}" for tipo in ka for valore in sorted(ka[tipo] & kb[tipo])]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--uscita", type=Path, default=Path("insiemi"))
    argomenti = parser.parse_args()
    insiemi = [genera_insieme(nome) for nome in ("sviluppo", "esame")]
    comuni = sovrapposizioni(*insiemi)
    if comuni:
        sys.exit("Sviluppo ed esame hanno elementi in comune:\n" + "\n".join(comuni))
    for insieme in insiemi:
        valore = salva_insieme(insieme, argomenti.uscita / insieme.nome)
        print(f"{insieme.nome}: {len(insieme.casi)} fatture, impronta {valore}")


if __name__ == "__main__":
    main()
