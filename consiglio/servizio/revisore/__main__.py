"""Avvia il server del Consiglio per Evolus: Qwen3 caricato una volta, i due tool via MCP e HTTP.

    export CONSIGLIO_SEGRETO=$(openssl rand -hex 32)      # lo stesso va nel connettore di Evolus
    python -m revisore --modello Qwen/Qwen3-14B --passi 10 \\
        --link "https://consiglio.example.org/verdetto/{id}?chiave={chiave}" --host-pubblico consiglio.example.org

Il TLS lo fa Caddy davanti (`caddy reverse-proxy --from consiglio.example.org --to 127.0.0.1:8001`), oppure uvicorn
con `--ssl-certfile`, `--ssl-keyfile` e `--host 0.0.0.0`. Ogni caso si salva in `--casi/<id>/`: revisione, vista,
pagina del verdetto e scelte della persona. Il testo del contratto non si salva.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

# Il Consiglio sta in consiglio/revisione, che non si installa: si usa da lì.
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "revisione"))

import torch
import uvicorn
from motore import TELEPATIA, TESTO, Modello, Motore
from revisione import BENCHMARK, Consiglio
from revisione.esegui import MODELLI

from .gestore import Revisore
from .server import crea_app


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--modello", default="Qwen/Qwen3-14B", choices=list(MODELLI))
    parser.add_argument("--dtype", choices=["float32", "bfloat16", "float16"], help="di default bf16 su GPU")
    parser.add_argument("--passi", type=int, default=10, help="passi latenti: quelli scelti in “Council on the engine”")
    parser.add_argument("--senza-riallineamento", action="store_true")
    parser.add_argument(
        "--link", required=True, help='la pagina, con {id} e {chiave}: "https://…/verdetto/{id}?chiave={chiave}"'
    )
    parser.add_argument("--casi", type=Path, default=Path.home() / ".consiglio" / "casi")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--porta", type=int, default=8001)
    parser.add_argument("--host-pubblico", action="append", default=[], help="il nome con cui si raggiunge da fuori")
    parser.add_argument("--ssl-certfile", default=None)
    parser.add_argument("--ssl-keyfile", default=None)
    argomenti = parser.parse_args()

    segreto = os.environ.get("CONSIGLIO_SEGRETO", "")
    if len(segreto) < 32:
        sys.exit(
            "Serve CONSIGLIO_SEGRETO di almeno 32 caratteri, per esempio: export CONSIGLIO_SEGRETO=$(openssl rand -hex 32)"
        )
    modello = Modello(
        argomenti.modello,
        MODELLI[argomenti.modello],
        dtype=getattr(torch, argomenti.dtype) if argomenti.dtype else None,
        riallinea=not argomenti.senza_riallineamento,
    )
    motore = Motore(modello, registro=argomenti.casi / "registro")
    consigli = {
        m: Consiglio(motore, BENCHMARK["dimostrativo"], modalita=m, passi_latenti=argomenti.passi)
        for m in (TELEPATIA, TESTO)
    }

    def revisiona(id_caso: str, testo: str, modalita: str) -> dict:
        return consigli[modalita].revisiona(id_caso, testo).come_dict()

    revisore = Revisore(revisiona, argomenti.casi, segreto=segreto, link=argomenti.link)
    app = crea_app(revisore, segreto, host_pubblici=tuple(argomenti.host_pubblico))
    uvicorn.run(app, host=argomenti.host, port=argomenti.porta, ssl_certfile=argomenti.ssl_certfile,
                ssl_keyfile=argomenti.ssl_keyfile)  # fmt: skip


if __name__ == "__main__":
    main()
