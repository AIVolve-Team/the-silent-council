"""La parte del Consiglio nel sito per i giudici: l'indice dei contratti e le pagine del verdetto.

    python -m revisione.vetrina --giro <giro telepatia>.jsonl --giro <giro testo>.jsonl \\
        --registrato "15/10/2026 sulla MI300X" --uscita vetrina-consiglio

La cartella che esce va passata a `casa/costruisci.py --consiglio <cartella>`. L'indice ha lo stile della home del sito,
una riga per contratto con telepatia e testo affiancati. Indice e pagine del verdetto si aprono in inglese, con
l'interruttore per l'italiano; `numeri.json` dà alla home le medie per la dimostrazione.

Il set dimostrativo resta privato fino alla consegna: senza `--consegna` le sue revisioni non escono, perché il sito
è pubblico.
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

from .categorie import BENCHMARK
from .dati import dimostrativo, risposte_esperti
from .vista import pagina, vista

INDICE = Path(__file__).resolve().parents[1] / "pagina" / "vetrina.html"
_SEGNAPOSTO = '<script id="dati" type="application/json">null</script>'

# Da dove vengono i contratti e le risposte giuste (dati/NOTICE.md): non sono nostri, e il giudice può controllarli.
# "chi" e "spiegazione" in tutte e due le lingue della pagina del verdetto.
FONTI = {
    "cuad": {
        "nome": "CUAD",
        "link": "https://github.com/TheAtticusProject/cuad",
        "chi": {"it": "gli esperti di CUAD", "en": "the CUAD experts"},
        "spiegazione": {
            "it": (
                "Il contratto e le risposte giuste vengono da CUAD, un dataset pubblico di contratti veri annotati da "
                "studenti di legge controllati da avvocati (The Atticus Project, NeurIPS 2021). Non li abbiamo scritti noi."
            ),
            "en": (
                "The contract and its right answers come from CUAD, a public dataset of real contracts annotated by law "
                "students under lawyers' supervision (The Atticus Project, NeurIPS 2021). We did not write them."
            ),
        },
    },
    "contractnli": {
        "nome": "ContractNLI",
        "link": "https://stanfordnlp.github.io/contract-nli/",
        "chi": {"it": "gli esperti di ContractNLI", "en": "the ContractNLI annotators"},
        "spiegazione": {
            "it": (
                "L'accordo e le risposte giuste vengono da ContractNLI, un dataset pubblico di accordi di riservatezza "
                "veri annotati a mano (Koreeda e Manning, Stanford, EMNLP 2021). Non li abbiamo scritti noi."
            ),
            "en": (
                "The agreement and its right answers come from ContractNLI, a public dataset of real non-disclosure "
                "agreements annotated by hand (Koreeda and Manning, Stanford, EMNLP 2021). We did not write them."
            ),
        },
    },
    "claudette": {
        "nome": "CLAUDETTE",
        "link": "https://github.com/lt-nlp-lab-unibo/Multilingual-Unfair-Clause-Detection",
        "chi": {"it": "gli esperti di CLAUDETTE", "en": "the CLAUDETTE annotators"},
        "spiegazione": {
            "it": (
                "Le condizioni d'uso e le risposte giuste vengono da CLAUDETTE, un dataset pubblico di condizioni d'uso "
                "vere annotate a mano da giuristi (Galassi e altri, Artificial Intelligence and Law, 2024). Non le "
                "abbiamo scritte noi."
            ),
            "en": (
                "The terms of service and their right answers come from CLAUDETTE, a public dataset of real terms "
                "annotated by legal scholars (Galassi et al., Artificial Intelligence and Law, 2024). We did not write "
                "them."
            ),
        },
    },
    "dimostrativo": {
        "nome": "risposte attese",
        "link": None,
        "chi": {"it": "le risposte attese", "en": "the expected answers"},
        "spiegazione": {
            "it": (
                "Le risposte attese le abbiamo scritte prima delle prove e bloccate con la loro impronta digitale nel "
                "repo: si può controllare che non siano cambiate dopo."
            ),
            "en": (
                "We wrote the expected answers before the runs and locked them with their fingerprint in the "
                "repository: anyone can check that they did not change afterwards."
            ),
        },
    },
}


class Privato(SystemExit):
    """Una revisione del set dimostrativo senza `--consegna`."""


def titolo_cuad(cid: str) -> str:
    """Un nome leggibile dall'id di CUAD, che è il nome del file depositato: "PenntexMidstreamPartnersLp_20150416_S-1A_
    EX-10.4_9042833_EX-10.4_Transportation Agreement" diventa "Penntex Midstream Partners Lp: transportation agreement".
    Il tipo di contratto è l'ultimo pezzo che parla di "agreement"; se manca, "contract"."""
    data = re.match(r"^(.*?)_(?:\d{2}_\d{2}_\d{4}|\d{8})", cid)
    azienda = data.group(1) if data else re.split(r" - |_|-", cid, maxsplit=1)[0]
    azienda = azienda.replace("_", " ").replace(",", ", ").replace("  ", " ").strip()
    if " " not in azienda and re.search(r"[a-z]", azienda):
        azienda = re.sub(r"(?<=[a-z])(?=[A-Z])", " ", azienda)  # PenntexMidstreamPartnersLp
    pezzi = re.findall(r"[A-Za-z][A-Za-z ,.&()_-]*?agreement(?: *\([^)]*\))?", cid.replace(" _ ", " & "), re.IGNORECASE)
    if not pezzi:
        return f"{azienda}: contract"
    parti = [x.strip() for x in re.split(r"[-_]", pezzi[-1]) if x.strip()]
    tipo = parti[-1]
    if len(parti) > 1 and len(parti[-2]) <= 3:
        tipo = f"{parti[-2]}-{tipo}"  # Co-Branding
    # minuscole fuori dalle parentesi, dove restano i nomi propri: "(Hyatt Ziva Cancun)"
    tipo = re.sub(r"[^()]+(?=\(|$)", lambda m: m.group(0).lower(), tipo, count=1)
    return f"{azienda}: {tipo}"


def titolo_di(revisione: dict, testi: dict[str, str]) -> str:
    """Per il set dimostrativo l'oggetto del contratto (o la prima riga), come in `prova.sh`; per CUAD un nome leggibile
    dall'id; per gli altri l'id."""
    testo = testi.get(revisione["contratto"])
    if not testo:
        return titolo_cuad(revisione["contratto"]) if revisione["benchmark"] == "cuad" else revisione["contratto"]
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


def numeri(revisioni: list[dict], viste: list[dict], registrato: str | None) -> dict | None:
    """Le medie per contratto di telepatia e testo per la dimostrazione della home: token scritti e letti, secondi
    e il conto severo delle clausole trovate. Solo sui contratti fatti in tutte e due le modalità, e su un benchmark con
    le risposte di esperti esterni (CUAD prima di tutto): il set dimostrativo l'abbiamo scritto noi."""
    for benchmark in ("cuad", "contractnli", "claudette"):
        coppie = {
            (r["contratto"], r["modalita"]): (r, v) for r, v in zip(revisioni, viste) if r["benchmark"] == benchmark
        }
        contratti = sorted({c for c, m in coppie if m == "telepatia"} & {c for c, m in coppie if m == "testo"})
        if not contratti:
            continue
        medie = {}
        for modalita in ("telepatia", "testo"):
            scelte = [coppie[(c, modalita)] for c in contratti]
            confronti = [v["confronto"] for _, v in scelte if v["confronto"]]
            medie[modalita] = {
                "token_generati": round(sum(r["token_generati"] for r, _ in scelte) / len(scelte)),
                "token_letti": round(sum(r["token_letti"] for r, _ in scelte) / len(scelte)),
                "secondi": round(sum(r["secondi"] for r, _ in scelte) / len(scelte), 1),
                "trovate": sum(c["trovate"] for c in confronti),
                "da_trovare": sum(c["da_trovare"] for c in confronti),
            }
        modelli = sorted({coppie[(c, m)][0]["modello"] for c in contratti for m in ("telepatia", "testo")})
        return {
            "registrato": registrato,
            "benchmark": benchmark,
            "fonte": FONTI[benchmark]["nome"],
            "modello": ", ".join(modelli),
            "contratti": len(contratti),
            **medie,
        }
    return None


def scrivi_vetrina(giri: list[Path], uscita: Path, *, registrato: str | None, consegna: bool = False) -> int:
    revisioni = [json.loads(r) for giro in giri for r in giro.read_text().splitlines() if r.strip()]
    if not consegna and any(r["benchmark"] == "dimostrativo" for r in revisioni):
        raise Privato(
            "Il set dimostrativo resta privato fino alla consegna e il sito è pubblico: "
            "togli quei giri, oppure aggiungi --consegna quando si consegna."
        )
    chiavi = [(r["benchmark"], r["contratto"], r["modalita"]) for r in revisioni]
    if len(set(chiavi)) < len(chiavi):
        # Per esempio due giri di telepatia con passi diversi: le pagine si sovrascriverebbero e le medie si mescolano.
        raise SystemExit(
            "Lo stesso contratto compare due volte nella stessa modalità: passa un giro solo per modalità."
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
    voci, viste = [], []
    for r in revisioni:
        esperti = (attese if r["benchmark"] == "dimostrativo" else risposte_esperti(r["benchmark"])).get(r["contratto"])
        fonte = FONTI[r["benchmark"]] if esperti else None
        v = vista(r, BENCHMARK[r["benchmark"]], titolo_di(r, testi), esperti=esperti, fonte=fonte)
        # Nel sito dei giudici la pagina si apre in inglese (chi legge può passare all'italiano) e torna all'indice.
        v |= {"lingua": "en", "indice": "index.html"}
        file = f"verdetto-{r['benchmark']}-{r['contratto'][:50].rstrip('-_. ')}-{r['modalita']}.html"
        file = file.replace("/", "_").replace(" ", "_")
        (uscita / file).write_text(pagina(v))
        voci.append(voce(r, v, file))
        viste.append(v)
    medie = numeri(revisioni, viste, registrato)
    if medie:
        (uscita / "numeri.json").write_text(json.dumps(medie, ensure_ascii=False, indent=1) + "\n")
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
