"""Le pagine del caso e l'indice con le proposte da approvare: HTML statico con i dati incorporati.

    python -m pagina.pagina <risultati>/telepatia.jsonl ../dati/insiemi/sviluppo --uscita pagine/ --registrato "15/10/2026 sulla MI300X"

Come la pagina del verdetto del Consiglio: niente server per mostrarle, quindi vanno bene anche su Vercel.
Le scelte della persona restano nel browser; con `--api` partono anche verso Evolus attraverso una funzione.
"""

from __future__ import annotations

import argparse
import html
import json
from importlib.resources import files
from pathlib import Path

CAMPI_ELENCO = ("id", "esito", "motivo", "fattura", "sigillo", "testimoni", "proposta")


def incorpora(dati) -> str:
    """JSON dentro <script>: `<`, `>` e `&` diventano `\\u003c`, `\\u003e` e `\\u0026`, che JSON legge uguali. Così nessun
    testo della fattura può chiudere il tag né far cambiare stato al parser HTML (`<!--<script`)."""
    testo = json.dumps(dati, ensure_ascii=False)
    return testo.replace("&", "\\u0026").replace("<", "\\u003c").replace(">", "\\u003e")


def pagina_caso(
    vista: dict,
    *,
    registrato: str | None = None,
    registro: str | None = None,
    api: str | None = None,
    pdf_url: str | None = None,
) -> str:
    """Con `pdf_url` la pagina mostra il PDF accanto a sé: Chrome spesso non apre un PDF incorporato come `data:`."""
    dati = {**vista, "registrato": registrato, "registro": registro}
    if pdf_url:
        dati = {k: v for k, v in dati.items() if k != "pdf"} | {"pdf_url": pdf_url}
    modello = files("pagina").joinpath("caso.html").read_text(encoding="utf-8")
    pagina = modello.replace("@@DATI@@", incorpora(dati))
    return pagina.replace('<body data-api="">', f'<body data-api="{html.escape(api or "", quote=True)}">')


def elenco(viste: list[dict], *, registrato: str | None = None) -> str:
    casi = [{k: v.get(k) for k in CAMPI_ELENCO} for v in viste]
    modello = files("pagina").joinpath("elenco.html").read_text(encoding="utf-8")
    return modello.replace("@@DATI@@", incorpora(casi)).replace("@@REGISTRATO@@", html.escape(registrato or ""))


def main() -> None:
    from fatture.insiemi import carica_archivi

    from .vista import vista_caso

    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("risultati", type=Path, help="un file .jsonl di un giro della pipeline")
    parser.add_argument("insieme", type=Path, help="la cartella dell'insieme, per archivi e PDF")
    parser.add_argument("--uscita", type=Path, default=Path("pagine"))
    parser.add_argument("--registrato", default=None, help='per esempio "15/10/2026 sulla MI300X"')
    parser.add_argument("--api", default=None, help="l'indirizzo della funzione che porta le scelte a Evolus")
    argomenti = parser.parse_args()
    archivi = carica_archivi(argomenti.insieme)
    argomenti.uscita.mkdir(parents=True, exist_ok=True)
    viste = []
    for riga in argomenti.risultati.read_text().splitlines():
        r = json.loads(riga)
        if r.get("esito") == "errore":
            continue
        pdf = (argomenti.insieme / "fatture" / f"{r['id']}.pdf").read_bytes()
        vista = vista_caso({**r, "id_caso": r["id"]}, archivi, pdf=pdf)
        (argomenti.uscita / f"{r['id']}.pdf").write_bytes(pdf)
        (argomenti.uscita / f"{r['id']}.html").write_text(
            pagina_caso(vista, registrato=argomenti.registrato, api=argomenti.api, pdf_url=f"{r['id']}.pdf"),
            encoding="utf-8",
        )
        viste.append(vista)
    (argomenti.uscita / "index.html").write_text(elenco(viste, registrato=argomenti.registrato), encoding="utf-8")
    print(f"{len(viste)} pagine in {argomenti.uscita}")


if __name__ == "__main__":
    main()
