"""Costruisce la casa per i giudici in `public/`: la home, lo Sportello (casi registrati e prove dal vivo) e, fino
a G4, il Consiglio. Si lancia con l'ambiente di `sportello/servizio`, che ha pagina, generatore e attacchi.

    sportello/servizio/.venv/bin/python casa/costruisci.py --insieme sportello/dati/insiemi/sviluppo \\
        --giro <risultati>/telepatia.jsonl --registri <risultati>/registro/telepatia --registrato "15/10/2026 on the MI300X" \\
        [--consiglio <pagine del verdetto>] [--repo https://github.com/…] [--api-decisione /api/decisione]
    cd casa && vercel deploy      # con la CLI: il piano gratuito non collega da solo i repo di un'organizzazione

Senza `--giro` (prima dei giri sulla MI300X) lo Sportello ha l'elenco vuoto e le prove dal vivo.
`--api-decisione` solo per le riprese e il palco: le scelte dei giudici restano nel browser.
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
from pathlib import Path

from attacchi.costruisci import costruisci
from fatture.genera import genera_insieme
from pagina.pagina import scrivi_pagine
from pagina.vista import maschera

QUI = Path(__file__).resolve().parent
ANOMALIE = {
    "A01": ("exact duplicate", "duplicato esatto"),
    "A02": ("possible duplicate", "possibile duplicato"),
    "A03": ("IBAN differs from the master data", "IBAN diverso dall'anagrafica"),
    "A04": ("payee differs from the supplier", "beneficiario diverso dal fornitore"),
    "A05": ("supplier not in the master data", "fornitore non in anagrafica"),
    "A06": ("supplier deactivated", "fornitore disattivato"),
    "A07": ("no purchase order reference", "nessun riferimento all'ordine"),
    "A08": ("purchase order problem", "problema con l'ordine"),
    "A09a": ("price 2-10% above the order", "prezzo dal 2 al 10% sopra l'ordine"),
    "A09b": ("price more than 10% above the order", "prezzo oltre il 10% sopra l'ordine"),
    "A10": ("quantity beyond the order", "quantità oltre l'ordine"),
    "A11": ("line to match to the order", "riga da abbinare all'ordine"),
    "A12": ("VAT rate differs from the order", "aliquota IVA diversa dall'ordine"),
    "A13": ("total differs from taxable amount plus VAT", "totale diverso da imponibile più IVA"),
}
SPORTELLO = {
    "id": "sportello",
    "nome": "Sportello telepatico",
    "en": "Invoices examined by agents that pass each other their memory, checked by a truth machine: seal, coherence "
    "and three witnesses. Hidden text, tampered messages and lying agents get caught before anything is paid.",
    "it": "Fatture esaminate da agenti che si passano la memoria, controllati da una macchina della verità: sigillo, "
    "coerenza e tre testimoni. Testo nascosto, messaggi manomessi e agenti che mentono si fermano prima di pagare.",
    "casi": "sportello/index.html",
    "prova": "sportello/prove.html",
    "numeri": None,
}
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


def fatture_da_provare(insieme: Path) -> list[dict]:
    """Le fatture che il giudice può far esaminare: due pulite per lingua e una per ogni anomalia del catalogo."""
    casi = [json.loads(r) for r in (insieme / "verita.jsonl").read_text().splitlines()]
    scelte, pulite = [], {"it": 0, "en": 0}
    for c in casi:
        if c["anomalia"] is None and c["al_limite"] is None and pulite[c["lingua"]] < 2:
            pulite[c["lingua"]] += 1
        elif c["anomalia"] is None or c["anomalia"] in {s["anomalia"] for s in scelte}:
            continue
        imp = c["impegno"]
        en, it = ANOMALIE.get(c["anomalia"], ("", "")) if c["anomalia"] else ("", "")
        scelte.append({
            "id": c["id"], "fornitore": imp["fornitore"]["denominazione"], "numero": imp["documento"]["numero"],
            "totale": imp["totale_documento"], "lingua": c["lingua"], "anomalia": c["anomalia"], "en": en, "it": it,
        })  # fmt: skip
    return sorted(scelte, key=lambda s: (s["anomalia"] is not None, s["anomalia"] or "", s["lingua"]))


def attacchi_della_demo(nome: str, attacco_1: str, attacco_2: str) -> dict:
    """Cosa la pagina delle prove racconta dei due attacchi, con l'IBAN dell'attaccante abbreviato."""
    attacchi = {a.id: a for a in costruisci(genera_insieme(nome))}
    a1, a2 = attacchi[attacco_1], attacchi[attacco_2]
    return {
        "1": {"famiglia": a1.famiglia, "modalita": list(a1.modalita)},
        "2": {"famiglia": a2.famiglia, "modalita": list(a2.modalita), "testo": maschera(a2.testo_nascosto or "")},
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--insieme", type=Path, required=True, help="la cartella dell'insieme")
    parser.add_argument("--giro", type=Path, default=None, help="il .jsonl di un giro registrato sulla MI300X")
    parser.add_argument("--registri", type=Path, default=None, help="i registri di quel giro (<id>/)")
    parser.add_argument("--registrato", default=None, help='per esempio "15/10/2026 on the MI300X"')
    parser.add_argument("--consiglio", type=Path, default=None, help="le pagine del Consiglio, fino a G4")
    parser.add_argument("--senza-sportello", action="store_true", help="da G4, se si consegna solo il Consiglio")
    parser.add_argument("--repo", default=None, help="il repo pubblico, quando lo è")
    parser.add_argument("--api-decisione", default=None, help="solo per riprese e palco: /api/decisione")
    parser.add_argument("--attacco-1", default="sviluppo-F1-03")
    parser.add_argument("--attacco-2", default="sviluppo-F4-01")
    parser.add_argument("--uscita", type=Path, default=QUI / "public")
    a = parser.parse_args()

    if a.uscita.exists():
        shutil.rmtree(a.uscita)
    shutil.copytree(QUI / "sorgenti", a.uscita)
    shutil.copy(QUI / "finestre.json", a.uscita / "finestre.json")
    progetti = []
    if not a.senza_sportello:
        progetti.append(SPORTELLO)
        sportello = a.uscita / "sportello"
        n = scrivi_pagine(
            a.giro, a.insieme, sportello, registrato=a.registrato, api=a.api_decisione, registri=a.registri, casa=True
        )
        dati = {
            "fatture": fatture_da_provare(a.insieme),
            "attacchi": attacchi_della_demo(a.insieme.resolve().name, a.attacco_1, a.attacco_2),
        }
        (sportello / "fatture.json").write_text(json.dumps(dati, ensure_ascii=False, indent=1))
        print(f"Sportello: {n} casi registrati, {len(dati['fatture'])} fatture per le prove dal vivo")
    else:
        shutil.rmtree(a.uscita / "sportello")
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
