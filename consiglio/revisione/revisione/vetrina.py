"""La parte del Consiglio nel sito per i giudici: l'indice dei contratti e le pagine del verdetto.

    python -m revisione.vetrina --giro <giro telepatia>.jsonl --giro <giro testo>.jsonl \\
        --registrato "15/10/2026 sulla MI300X" --uscita vetrina-consiglio

La cartella che esce va passata a `casa/costruisci.py --consiglio <cartella>`. L'indice ha lo stile della home del sito
e l'interruttore inglese/italiano. Le pagine del verdetto restano in italiano, come per la PMI che le riceve.

Il set dimostrativo resta privato fino alla consegna: senza `--consegna` le sue revisioni non escono, perché il sito
è pubblico.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from .categorie import BENCHMARK
from .dati import dimostrativo, risposte_esperti
from .vista import pagina, vista

INDICE = Path(__file__).resolve().parents[1] / "pagina" / "vetrina.html"
_SEGNAPOSTO = '<script id="dati" type="application/json">null</script>'

# Da dove vengono i contratti e le risposte giuste (dati/NOTICE.md): non sono nostri, e il giudice può controllarli.
FONTI = {
    "cuad": {
        "nome": "CUAD",
        "chi": "gli esperti di CUAD",
        "link": "https://github.com/TheAtticusProject/cuad",
        "spiegazione": (
            "Il contratto e le risposte giuste vengono da CUAD, un dataset pubblico di contratti veri annotati da"
            " studenti di legge controllati da avvocati (The Atticus Project, NeurIPS 2021). Non li abbiamo "
            "scritti noi."
        ),
    },
    "contractnli": {
        "nome": "ContractNLI",
        "chi": "gli esperti di ContractNLI",
        "link": "https://stanfordnlp.github.io/contract-nli/",
        "spiegazione": (
            "L'accordo e le risposte giuste vengono da ContractNLI, un dataset pubblico di accordi di "
            "riservatezza veri annotati a mano (Koreeda e Manning, Stanford, EMNLP 2021). Non li abbiamo scritti "
            "noi."
        ),
    },
    "claudette": {
        "nome": "CLAUDETTE",
        "chi": "gli esperti di CLAUDETTE",
        "link": "https://github.com/lt-nlp-lab-unibo/Multilingual-Unfair-Clause-Detection",
        "spiegazione": (
            "Le condizioni d'uso e le risposte giuste vengono da CLAUDETTE, un dataset pubblico di condizioni "
            "d'uso vere annotate a mano da giuristi (Galassi e altri, Artificial Intelligence and Law, 2024). Non"
            " le abbiamo scritte noi."
        ),
    },
    "dimostrativo": {
        "nome": "risposte attese",
        "chi": "le risposte attese",
        "link": None,
        "spiegazione": (
            "Le risposte attese le abbiamo scritte prima delle prove e bloccate con la loro impronta digitale nel"
            " repo: si può controllare che non siano cambiate dopo."
        ),
    },
}


class Privato(SystemExit):
    """Una revisione del set dimostrativo senza `--consegna`."""


def titolo_di(revisione: dict, testi: dict[str, str]) -> str:
    """Per il set dimostrativo l'oggetto del contratto (o la prima riga), come in `prova.sh`; per gli altri l'id."""
    testo = testi.get(revisione["contratto"])
    if not testo:
        return revisione["contratto"]
    righe = [r.strip() for r in testo.splitlines() if r.strip()]
    oggetto = next((r.split(":", 1)[1].strip() for r in righe if r.lower().startswith("oggetto:")), None)
    titolo = oggetto or righe[0]
    return titolo[0].upper() + titolo[1:].lower()


def voce(revisione: dict, v: dict, file: str) -> dict:
    """Quello che l'indice mostra di un verdetto: niente frasi del contratto, solo conteggi e raccomandazione."""
    righe = v["righe"]
    return {
        "titolo": v["titolo"],
        "contratto": revisione["contratto"],
        "benchmark": revisione["benchmark"],
        "modalita": revisione["modalita"],
        "raccomandazione": (v["raccomandazione"] or {}).get("valore"),
        "segnalate": sum(bool(r["segnalare"]) for r in righe),
        "categorie": len(righe),
        "dissensi_gravi": sum(bool(r["dissenso"]) and r["dissenso"]["tipo"] == "grave" for r in righe),
        "dissensi_lievi": sum(bool(r["dissenso"]) and r["dissenso"]["tipo"] == "lieve" for r in righe),
        "sigillo_integro": v["sigillo"]["integro"],
        "fonte": (v["confronto"] or {}).get("nome"),
        "d_accordo": (v["confronto"] or {}).get("d_accordo"),
        "confrontate": (v["confronto"] or {}).get("confrontate"),
        "trovate": (v["confronto"] or {}).get("trovate"),
        "da_trovare": (v["confronto"] or {}).get("da_trovare"),
        "token_generati": revisione["token_generati"],
        "secondi": round(revisione["secondi"]),
        "modello": revisione["modello"],
        "pagina": file,
    }


def scrivi_vetrina(giri: list[Path], uscita: Path, *, registrato: str | None, consegna: bool = False) -> int:
    revisioni = [json.loads(r) for giro in giri for r in giro.read_text().splitlines() if r.strip()]
    if not consegna and any(r["benchmark"] == "dimostrativo" for r in revisioni):
        raise Privato(
            "Il set dimostrativo resta privato fino alla consegna e il sito è pubblico: "
            "togli quei giri, oppure aggiungi --consegna quando si consegna."
        )
    testi, attese = {}, {}
    if any(r["benchmark"] == "dimostrativo" for r in revisioni):
        for cid, testo, attesa in dimostrativo():
            testi[cid] = testo
            attese[cid] = {
                riga["categoria"]: {
                    "da_segnalare": riga["da_segnalare"],
                    "prove": [riga["citazione"]] if riga.get("citazione") else [],
                }
                for riga in attesa["righe"]
            }
    uscita.mkdir(parents=True, exist_ok=True)
    voci = []
    for r in revisioni:
        esperti = (attese if r["benchmark"] == "dimostrativo" else risposte_esperti(r["benchmark"])).get(r["contratto"])
        fonte = FONTI[r["benchmark"]] if esperti else None
        v = vista(r, BENCHMARK[r["benchmark"]], titolo_di(r, testi), esperti=esperti, fonte=fonte)
        file = f"verdetto-{r['benchmark']}-{r['contratto'][:50].rstrip('-_. ')}-{r['modalita']}.html"
        file = file.replace("/", "_").replace(" ", "_")
        (uscita / file).write_text(pagina(v))
        voci.append(voce(r, v, file))
    dati = json.dumps({"registrato": registrato, "verdetti": voci}, ensure_ascii=False).replace("</", "<\\/")
    html = INDICE.read_text()
    assert html.count(_SEGNAPOSTO) == 1
    (uscita / "index.html").write_text(
        html.replace(_SEGNAPOSTO, f'<script id="dati" type="application/json">{dati}</script>')
    )
    return len(voci)


def main() -> None:
    parser = argparse.ArgumentParser(description="La parte del Consiglio nel sito per i giudici.")
    parser.add_argument("--giro", type=Path, action="append", required=True, help="un .jsonl di revisioni registrate")
    parser.add_argument("--registrato", default=None, help='per esempio "15/10/2026 sulla MI300X"')
    parser.add_argument(
        "--consegna", action="store_true", help="solo alla consegna: pubblica anche il set dimostrativo"
    )
    parser.add_argument("--uscita", type=Path, default=Path("vetrina-consiglio"))
    argomenti = parser.parse_args()
    n = scrivi_vetrina(argomenti.giro, argomenti.uscita, registrato=argomenti.registrato, consegna=argomenti.consegna)
    print(f"{n} verdetti in {argomenti.uscita}: si passa a casa/costruisci.py --consiglio {argomenti.uscita}")


if __name__ == "__main__":
    main()
