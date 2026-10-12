"""Avvia il server del motore: Qwen3 caricato una volta, i due tool via MCP e HTTP.

    export SPORTELLO_SEGRETO=$(openssl rand -hex 32)      # lo stesso va nel connettore di Evolus e nella funzione Vercel
    python -m servizio ../dati/insiemi/sviluppo --modello Qwen/Qwen3-14B --passi 20 \\
        --link "https://<casa dei giudici>/caso.html?id={id}" --host-pubblico motore.example.org

Il TLS lo fa Caddy davanti (`caddy reverse-proxy --from motore.example.org --to 127.0.0.1:8000`), oppure uvicorn con
`--ssl-certfile` e `--ssl-keyfile` e `--host 0.0.0.0`. Ogni caso si salva in `--casi/<id>/`: registro firmato della
pipeline, PDF, vista e decisioni;
`python -m motore.verifica <casi>/<id> --pubbliche <casi>/<id>/chiavi-pubbliche` lo controlla.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

import uvicorn
from fatture.insiemi import carica_archivi
from motore import Modello
from pipeline.giro import DTYPE, MODELLI
from pipeline.sportello import chiavi_di_prova, esamina

from .gestore import Sportello
from .server import crea_app


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument(
        "insieme", type=Path, help="la cartella di un insieme: l'anagrafica, gli ordini e lo storico"
    )
    parser.add_argument("--modello", default="Qwen/Qwen3-14B", choices=list(MODELLI))
    parser.add_argument("--dtype", choices=list(DTYPE), default=None, help="predefinito: bf16 su GPU, fp32 altrove")
    parser.add_argument("--passi", type=int, default=10, help="passi latenti: quelli scelti da G2")
    parser.add_argument("--link", required=True, help='la pagina del caso, con {id}: "https://…/caso.html?id={id}"')
    parser.add_argument("--casi", type=Path, default=Path.home() / ".sportello" / "casi")
    parser.add_argument("--chiavi", type=Path, default=Path.home() / ".sportello" / "chiavi-prova")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--porta", type=int, default=8000)
    parser.add_argument("--host-pubblico", action="append", default=[], help="il nome con cui si raggiunge da fuori")
    parser.add_argument("--host-pdf", action="append", default=[], help="host da cui si può scaricare pdf_url")
    parser.add_argument("--ssl-certfile", default=None)
    parser.add_argument("--ssl-keyfile", default=None)
    argomenti = parser.parse_args()

    segreto = os.environ.get("SPORTELLO_SEGRETO", "")
    if len(segreto) < 32:
        sys.exit(
            "Serve SPORTELLO_SEGRETO di almeno 32 caratteri, per esempio: export SPORTELLO_SEGRETO=$(openssl rand -hex 32)"
        )
    if "{id}" not in argomenti.link:
        sys.exit("--link deve contenere {id}")

    modello = Modello(argomenti.modello, MODELLI[argomenti.modello], dtype=DTYPE.get(argomenti.dtype or ""))
    chiavi = chiavi_di_prova(argomenti.chiavi)
    archivi = carica_archivi(argomenti.insieme)

    def staffetta(pdf: bytes, email: dict, modalita: str, id_caso: str) -> dict:
        return esamina(modello, pdf, email, archivi, chiavi, modalita=modalita, passi_latenti=argomenti.passi,
                       registro=argomenti.casi, id_caso=id_caso)  # fmt: skip

    sportello = Sportello(staffetta, archivi, argomenti.casi, link=argomenti.link)
    app = crea_app(sportello, segreto, host_pubblici=tuple(argomenti.host_pubblico), host_pdf=tuple(argomenti.host_pdf))
    uvicorn.run(app, host=argomenti.host, port=argomenti.porta, ssl_certfile=argomenti.ssl_certfile,
                ssl_keyfile=argomenti.ssl_keyfile)  # fmt: skip


if __name__ == "__main__":
    main()
