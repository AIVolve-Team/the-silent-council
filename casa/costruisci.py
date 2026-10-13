"""Costruisce la casa per i giudici in `public/`: la home e le pagine del Consiglio. Basta Python 3, senza
dipendenze: le pagine del verdetto le prepara `consiglio/revisione` (vista e vetrina).

    python3 casa/costruisci.py --consiglio <pagine del verdetto> [--repo https://github.com/…]
    cd casa && vercel deploy      # con la CLI: il piano gratuito non collega da solo i repo di un'organizzazione
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
from pathlib import Path

QUI = Path(__file__).resolve().parent
CONSIGLIO = {
    "id": "consiglio",
    "nome": "Consiglio silenzioso",
    "en": "A council of agents reviews contracts in silence, passing each other their memory, and writes a verdict with "
    "its dissent.",
    "it": "Un consiglio di agenti rivede i contratti in silenzio, passandosi la memoria, e scrive un verdetto con il suo "
    "dissenso.",
    "casi": "consiglio/index.html",
    "prova": "consiglio/prova.html",
}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--consiglio", type=Path, default=None, help="le pagine del Consiglio")
    parser.add_argument("--repo", default=None, help="il repo pubblico, quando lo è")
    parser.add_argument("--uscita", type=Path, default=QUI / "public")
    a = parser.parse_args()

    if a.uscita.exists():
        shutil.rmtree(a.uscita)
    shutil.copytree(QUI / "sorgenti", a.uscita)
    shutil.copy(QUI / "finestre.json", a.uscita / "finestre.json")
    progetti = []
    if a.consiglio:
        # accanto alla prova dal vivo di sorgenti/consiglio: indice, pagine del verdetto e numeri della vetrina
        shutil.copytree(a.consiglio, a.uscita / "consiglio", dirs_exist_ok=True)
        # numeri.json (scritto da revisione.vetrina): le medie di telepatia e testo per la dimostrazione della home
        numeri = "consiglio/numeri.json" if (a.uscita / "consiglio" / "numeri.json").exists() else None
        progetti.append(CONSIGLIO | {"numeri": numeri})
        print(f"Consiglio: pagine da {a.consiglio}" + (", con i numeri per la home" if numeri else ""))
    else:
        shutil.rmtree(a.uscita / "consiglio")
    (a.uscita / "progetti.json").write_text(
        json.dumps({"progetti": progetti, "repo": a.repo}, ensure_ascii=False, indent=1)
    )

    # Nessun IBAN intero fuori dai PDF: è la regola di «Caso passato a una persona», e qui si controlla su tutto ciò che va online.
    iban = re.compile(r"\b[A-Z]{2}\d{2}(?:\s?[A-Z0-9]){12,30}\b")
    for f in a.uscita.rglob("*"):
        if f.suffix in (".html", ".json") and iban.search(f.read_text(encoding="utf-8")):
            raise SystemExit(f"IBAN intero in {f.relative_to(a.uscita)}: non si pubblica")
    print(f"casa in {a.uscita}")


if __name__ == "__main__":
    main()
