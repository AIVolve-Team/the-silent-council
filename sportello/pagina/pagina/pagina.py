"""Le pagine del caso e l'indice con le proposte da approvare: HTML statico con i dati incorporati.

    python -m pagina.pagina <risultati>/telepatia.jsonl ../dati/insiemi/sviluppo --uscita pagine/ --registrato "15/10/2026 sulla MI300X" \
        --registri <risultati>/registro/telepatia

Come la pagina del verdetto del Consiglio: niente server per mostrarle, quindi vanno bene anche su Vercel.
Le scelte della persona restano nel browser; con `--api` partono anche verso Evolus attraverso una funzione.
"""

from __future__ import annotations

import argparse
import html
import io
import json
import zipfile
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


def pagina_dal_vivo(*, api: str | None = None) -> str:
    """La pagina dei casi nati dal vivo: senza dati, li prende dal browser che ha lanciato la prova."""
    modello = files("pagina").joinpath("caso.html").read_text(encoding="utf-8")
    pagina = modello.replace("@@DATI@@", "null")
    return pagina.replace('<body data-api="">', f'<body data-api="{html.escape(api or "", quote=True)}">')


def zip_registro(cartella: Path, id_caso: str) -> bytes:
    """Il registro del caso in un file solo, `registro-<id>/…`, come lo chiede il comando di verifica della pagina.
    Date fisse e ordine fisso: lo stesso registro dà sempre gli stessi byte."""
    uscita = io.BytesIO()
    with zipfile.ZipFile(uscita, "w", zipfile.ZIP_DEFLATED) as z:
        for file in sorted(p for p in cartella.rglob("*") if p.is_file()):
            info = zipfile.ZipInfo(f"registro-{id_caso}/{file.relative_to(cartella).as_posix()}", (1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            z.writestr(info, file.read_bytes())
    return uscita.getvalue()


def elenco(viste: list[dict], *, registrato: str | None = None, casa: bool = False) -> str:
    """Con `casa` l'indice sta nella casa per i giudici e porta alla home e alle prove dal vivo."""
    casi = [{k: v.get(k) for k in CAMPI_ELENCO} for v in viste]
    modello = files("pagina").joinpath("elenco.html").read_text(encoding="utf-8")
    pagina = modello.replace("@@DATI@@", incorpora(casi)).replace("@@REGISTRATO@@", html.escape(registrato or ""))
    return pagina.replace("@@CASA@@", "1" if casa else "")


def scrivi_pagine(
    risultati: Path | None,
    insieme: Path,
    uscita: Path,
    *,
    registrato: str | None = None,
    api: str | None = None,
    registri: Path | None = None,
    casa: bool = False,
) -> int:
    """Pagine dei casi, PDF e registri accanto, indice e pagina dal vivo in `uscita`. Senza `risultati` (prima dei
    giri sulla MI300X) solo l'indice vuoto e la pagina dal vivo. Restituisce quante pagine dei casi ha scritto."""
    from fatture.insiemi import carica_archivi

    from .vista import vista_caso

    archivi = carica_archivi(insieme)
    uscita.mkdir(parents=True, exist_ok=True)
    viste = []
    for riga in risultati.read_text().splitlines() if risultati else []:
        r = json.loads(riga)
        if r.get("esito") == "errore":
            continue
        pdf = (insieme / "fatture" / f"{r['id']}.pdf").read_bytes()
        vista = vista_caso({**r, "id_caso": r["id"]}, archivi, pdf=pdf)
        (uscita / f"{r['id']}.pdf").write_bytes(pdf)
        registro = None
        if registri and (registri / r["id"]).is_dir():
            registro = f"registro-{r['id']}.zip"
            (uscita / registro).write_bytes(zip_registro(registri / r["id"], r["id"]))
        (uscita / f"{r['id']}.html").write_text(
            pagina_caso(vista, registrato=registrato, registro=registro, api=api, pdf_url=f"{r['id']}.pdf"),
            encoding="utf-8",
        )
        viste.append(vista)
    (uscita / "index.html").write_text(elenco(viste, registrato=registrato, casa=casa), encoding="utf-8")
    (uscita / "dal-vivo.html").write_text(pagina_dal_vivo(api=api), encoding="utf-8")
    return len(viste)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("risultati", type=Path, help="un file .jsonl di un giro della pipeline")
    parser.add_argument("insieme", type=Path, help="la cartella dell'insieme, per archivi e PDF")
    parser.add_argument("--uscita", type=Path, default=Path("pagine"))
    parser.add_argument("--registrato", default=None, help='per esempio "15/10/2026 sulla MI300X"')
    parser.add_argument("--api", default=None, help="l'indirizzo della funzione che porta le scelte a Evolus")
    parser.add_argument(
        "--registri", type=Path, default=None, help="la cartella dei registri del giro (<id>/), da scaricare"
    )
    a = parser.parse_args()
    n = scrivi_pagine(a.risultati, a.insieme, a.uscita, registrato=a.registrato, api=a.api, registri=a.registri)
    print(f"{n} pagine in {a.uscita}")


if __name__ == "__main__":
    main()
