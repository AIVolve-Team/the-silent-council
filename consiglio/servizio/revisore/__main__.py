"""Avvia il server del Consiglio per Evolus: Qwen3 caricato una volta, i due tool via MCP e HTTP.

    export CONSIGLIO_SEGRETO=$(openssl rand -hex 32)      # lo stesso va nel connettore di Evolus
    python -m revisore --modello Qwen/Qwen3-14B --passi 10 \\
        --link "https://consiglio.example.org/verdetto/{id}?chiave={chiave}" --host-pubblico consiglio.example.org

Con `--modello-lungo google/gemma-4-31B-it` i contratti oltre `--soglia` token (6.000 di default) vanno a quel
modello, gli altri a `--modello` (`instradamento.py`). Gemma 4 vuole transformers 5.

Per le prove dal vivo dei giudici si aggiunge `--dal-vivo sviluppo` (e `test` solo dopo l'esame di «Eval del Consiglio»;
`--con-dimostrativo` solo alla consegna). Su un Mac piccolo, `--max-token 14000` lascia fuori i contratti lunghi.

Il TLS lo fa Caddy davanti (`caddy reverse-proxy --from consiglio.example.org --to 127.0.0.1:8001`), oppure uvicorn
con `--ssl-certfile`, `--ssl-keyfile` e `--host 0.0.0.0`. Ogni caso si salva in `--casi/<id>/`: revisione, vista,
pagina del verdetto e scelte della persona. Il testo del contratto non si salva.
"""

from __future__ import annotations

import argparse
import os
import sys
from collections.abc import Callable
from pathlib import Path

# Il Consiglio sta in consiglio/revisione, che non si installa: si usa da lì.
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "revisione"))

import torch
import uvicorn
from motore import Modello, Motore
from revisione import BENCHMARK, Consiglio
from revisione.dal_vivo import INSIEMI, catalogo
from revisione.esegui import MODELLI

from .gestore import Revisore
from .instradamento import SOGLIA, Instradamento
from .server import crea_app


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--modello", default="Qwen/Qwen3-14B", choices=list(MODELLI))
    parser.add_argument("--modello-lungo", choices=list(MODELLI), help="il modello dei contratti oltre la soglia")
    parser.add_argument("--soglia", type=int, default=SOGLIA, help="token del contratto, con il tokenizer di --modello")
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
    parser.add_argument(
        "--dal-vivo",
        nargs="+",
        choices=INSIEMI,
        help="accende le prove dal vivo dei giudici con i contratti CUAD di questi insiemi",
    )
    parser.add_argument("--con-dimostrativo", action="store_true", help="solo alla consegna: anche il set dimostrativo")
    parser.add_argument("--max-token", type=int, help="prove dal vivo: lascia fuori i contratti più lunghi")
    argomenti = parser.parse_args()

    segreto = os.environ.get("CONSIGLIO_SEGRETO", "")
    if len(segreto) < 32:
        sys.exit(
            "Serve CONSIGLIO_SEGRETO di almeno 32 caratteri, per esempio: export CONSIGLIO_SEGRETO=$(openssl rand -hex 32)"
        )

    def carica(nome: str) -> tuple[Modello, Callable[..., dict]]:
        modello = Modello(
            nome,
            MODELLI[nome],
            dtype=getattr(torch, argomenti.dtype) if argomenti.dtype else None,
            riallinea=not argomenti.senza_riallineamento,
        )
        motore = Motore(modello, registro=argomenti.casi / "registro")
        consigli: dict[tuple[str, str], Consiglio] = {}

        def revisiona(id_caso: str, testo: str, modalita: str, benchmark: str = "dimostrativo") -> dict:
            # Un Consiglio per benchmark e modalità: i contratti CUAD delle prove dal vivo con le regole di CUAD.
            if (benchmark, modalita) not in consigli:
                consigli[(benchmark, modalita)] = Consiglio(
                    motore, BENCHMARK[benchmark], modalita=modalita, passi_latenti=argomenti.passi
                )
            return consigli[(benchmark, modalita)].revisiona(id_caso, testo).come_dict()

        return modello, revisiona

    modello, revisiona = carica(argomenti.modello)

    def lunghezza(testo: str) -> int:
        return len(modello.tokenizer.encode(testo, add_special_tokens=False))

    if argomenti.modello_lungo:
        _, revisiona_lunghi = carica(argomenti.modello_lungo)
        revisiona = Instradamento(revisiona, revisiona_lunghi, lunghezza, argomenti.soglia)
        print(f"Instradamento: fino a {argomenti.soglia} token {argomenti.modello}, oltre {argomenti.modello_lungo}")

    voci = None
    if argomenti.dal_vivo:
        voci = catalogo(
            tuple(argomenti.dal_vivo),
            con_dimostrativo=argomenti.con_dimostrativo,
            lunghezza=lunghezza,
            max_token=argomenti.max_token,
        )
        print(f"Prove dal vivo accese: {len(voci)} contratti", flush=True)
    revisore = Revisore(revisiona, argomenti.casi, segreto=segreto, link=argomenti.link, catalogo=voci)
    app = crea_app(revisore, segreto, host_pubblici=tuple(argomenti.host_pubblico))
    uvicorn.run(app, host=argomenti.host, port=argomenti.porta, ssl_certfile=argomenti.ssl_certfile,
                ssl_keyfile=argomenti.ssl_keyfile)  # fmt: skip


if __name__ == "__main__":
    main()
