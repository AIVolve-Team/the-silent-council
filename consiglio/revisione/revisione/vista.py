"""Dalla revisione del Consiglio alla vista per la pagina del verdetto, con le regole di «Verdetto e dissenso».

- In cima la raccomandazione; poi le righe di tutte le categorie, con citazione, motivazione e confidenza.
- Il dissenso grave con l'esperto sicuro (confidenza alta) è sempre in evidenza; gli altri si aprono con un clic.
- Il sigillo è integro se la catena è stata consegnata e verificata; altrimenti la pagina mostra l'avviso rosso.

Uso: python -m revisione.vista risultati/<giro>.jsonl --contratto <id> --titolo "..." --uscita vista.json
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from .categorie import BENCHMARK, Benchmark
from .confidenza import livello

NOMI = {"legale": "Legale", "finanza": "Finanza", "rischio": "Rischio", "relatore": "Relatore"}
PAGINA = Path(__file__).resolve().parents[1] / "pagina" / "verdetto.html"
_SEGNAPOSTO = '<script id="dati" type="application/json">null</script>'
TAGLIO_PROVA = 400


def pagina(vista_: dict) -> str:
    """La pagina del verdetto con la vista dentro: un file solo, da aprire o allegare."""
    html = PAGINA.read_text()
    assert html.count(_SEGNAPOSTO) == 1
    dati = json.dumps(vista_, ensure_ascii=False).replace("</", "<\\/")
    return html.replace(_SEGNAPOSTO, f'<script id="dati" type="application/json">{dati}</script>')


def _livello(scritto: dict | None, chiave: str) -> str | None:
    if not scritto or not scritto.get("dati"):
        return None
    p = scritto["probabilita_si"].get(chiave)
    posizione = scritto["dati"]["segnalare"].get(chiave)
    return None if p is None or posizione is None else livello(p, posizione)


def _citazioni_nota(nota: dict) -> dict[str, tuple[str, bool]]:
    if not nota.get("dati"):
        return {}
    trovate = nota.get("citazioni_trovate", {})
    return {c["categoria"]: (c["testo"], trovate.get(c["categoria"], False)) for c in nota["dati"]["citazioni"]}


def _esperti(risposta: dict | None, segnalare: bool | None) -> dict | None:
    if risposta is None:
        return None
    return {
        "da_segnalare": risposta["da_segnalare"],
        "d_accordo": None if segnalare is None else segnalare == risposta["da_segnalare"],
        # Al massimo due pezzi annotati, tagliati: bastano a far vedere dove guardare.
        "prove": [p if len(p) <= TAGLIO_PROVA else p[:TAGLIO_PROVA].rstrip() + "…" for p in risposta["prove"][:2]],
    }


def vista(
    revisione: dict,
    benchmark: Benchmark,
    titolo: str,
    *,
    esperti: dict[str, dict] | None = None,
    fonte: dict | None = None,
) -> dict:
    """`esperti` (categoria → {"da_segnalare", "prove"}) e `fonte` ({"nome", "link"}) solo per il sito dei giudici
: ogni riga dice anche cosa hanno risposto gli esperti del dataset. La PMI cliente non li ha."""
    nomi = {c.chiave: c.nome for c in benchmark.categorie}
    verdetto = revisione.get("verdetto")
    dati = verdetto["dati"] if verdetto else None
    dettagli = {d["categoria"]: d for d in (dati or {}).get("dettagli", [])}
    trovate = (verdetto or {}).get("citazioni_trovate", {})
    dissensi = {d["categoria"]: d for d in revisione["dissensi"]}
    note = revisione["note"]

    righe = []
    for categoria in benchmark.categorie:
        dettaglio = dettagli.get(categoria.chiave, {})
        dissenso = dissensi.get(categoria.chiave)
        segnalare = None if dati is None else dati["segnalare"].get(categoria.chiave)
        riga = {
            "chiave": categoria.chiave,
            "nome": categoria.nome,
            "ruolo": categoria.ruolo,
            "segnalare": segnalare,
            "confidenza": _livello(verdetto, categoria.chiave),
            "citazione": dettaglio.get("citazione"),
            "citazione_trovata": trovate.get(categoria.chiave) if dettaglio else None,
            "motivazione": dettaglio.get("motivazione"),
            "dissenso": None,
            "esperti": _esperti((esperti or {}).get(categoria.chiave), segnalare),
        }
        if dissenso:
            citazione, trovata = _citazioni_nota(note.get(dissenso["ruolo"], {})).get(categoria.chiave, (None, None))
            riga["dissenso"] = {
                "tipo": dissenso["tipo"],
                "ruolo": dissenso["ruolo"],
                "nome_ruolo": NOMI[dissenso["ruolo"]],
                "esperto_dice": dissenso["tipo"] == "grave",
                "confidenza_esperto": dissenso["confidenza_esperto"],
                "confidenza_verdetto": dissenso["confidenza_verdetto"],
                "citazione_esperto": citazione,
                "citazione_esperto_trovata": trovata,
                # il dissenso grave con l'esperto sicuro si vede sempre.
                "in_evidenza": dissenso["tipo"] == "grave" and dissenso["confidenza_esperto"] == "alta",
            }
        righe.append(riga)

    note_vista = []
    for ruolo in benchmark.lettori:
        nota = note.get(ruolo)
        if nota is None:
            continue
        citazioni = _citazioni_nota(nota)
        note_vista.append(
            {
                "ruolo": ruolo,
                "nome": NOMI[ruolo],
                "valida": nota.get("dati") is not None,
                "righe": [
                    {
                        "chiave": c.chiave,
                        "nome": c.nome,
                        "segnalare": (nota.get("dati") or {}).get("segnalare", {}).get(c.chiave),
                        "confidenza": _livello(nota, c.chiave),
                    }
                    for c in benchmark.del_ruolo(ruolo)
                ],
                "citazioni": [
                    {"chiave": k, "nome": nomi.get(k, k), "testo": t, "trovata": f} for k, (t, f) in citazioni.items()
                ],
                "importi_date_parti": (nota.get("dati") or {}).get("importi_date_parti", []),
            }
        )

    confrontate = [r for r in righe if r["esperti"] and r["esperti"]["d_accordo"] is not None]
    # Il conto severo: l'accordo da solo è alto anche per chi risponde sempre "niente", perché le clausole presenti
    # sono poche. Una clausola senza risposta del Consiglio (verdetto mancante) conta come non trovata.
    da_trovare = [r for r in righe if r["esperti"] and r["esperti"]["da_segnalare"]]
    fermata = revisione.get("fermata")
    return {
        "titolo": titolo,
        "contratto": revisione["contratto"],
        "benchmark": revisione["benchmark"],
        "modalita": revisione["modalita"],
        "modello": revisione["modello"],
        "raccomandazione": None
        if dati is None
        else {"valore": dati["raccomandazione"], "motivazione": dati["motivazione"]},
        "obiezioni": [
            {"chiave": o["categoria"], "nome": nomi.get(o["categoria"], o["categoria"]), "obiezione": o["obiezione"]}
            for o in (dati or {}).get("obiezioni", [])
        ],
        "sigillo": {
            "integro": fermata is None and bool(revisione["impronte"]),
            "messaggi": len(revisione["impronte"]),
            "impronte": revisione["impronte"],
            "controllo": None if fermata is None else fermata["controllo"],
            "motivo": None if fermata is None else fermata["motivo"],
        },
        "righe": righe,
        "confronto": None
        if esperti is None
        else {
            **(fonte or {}),
            "d_accordo": sum(r["esperti"]["d_accordo"] for r in confrontate),
            "confrontate": len(confrontate),
            "trovate": sum(r["segnalare"] is True for r in da_trovare),
            "da_trovare": len(da_trovare),
        },
        "note": note_vista,
        "costo": {
            "token_generati": revisione["token_generati"],
            "token_letti": revisione["token_letti"],
            "posizioni_latenti": revisione["posizioni_latenti"],
            "secondi": round(revisione["secondi"], 1),
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Esporta la vista di una revisione per la pagina del verdetto.")
    parser.add_argument("giro", type=Path, help="file .jsonl scritto da revisione.esegui")
    parser.add_argument("--contratto", required=True)
    parser.add_argument("--titolo")
    parser.add_argument("--uscita", type=Path, default=Path("vista.json"))
    parser.add_argument(
        "--html", type=Path, help="scrive anche la pagina del verdetto con i dati dentro, in un file solo"
    )
    argomenti = parser.parse_args()
    revisioni = [json.loads(r) for r in argomenti.giro.open()]
    revisione = next(r for r in revisioni if r["contratto"] == argomenti.contratto)
    risultato = vista(revisione, BENCHMARK[revisione["benchmark"]], argomenti.titolo or argomenti.contratto)
    argomenti.uscita.write_text(json.dumps(risultato, ensure_ascii=False, indent=2) + "\n")
    print(f"Scritto {argomenti.uscita}")
    if argomenti.html:
        argomenti.html.write_text(pagina(risultato))
        print(f"Scritto {argomenti.html}")


if __name__ == "__main__":
    main()
