"""Il controllo a mano alla cieca del set dimostrativo.

Chi controlla non ha scritto né rivisto le risposte attese, non apre i loro `.json` e non sa quale verdetto viene
dal testo e quale dalla telepatia. Riceve i contratti e un foglio per verdetto, con nomi neutri e in ordine mescolato:
raccomandazione, clausole segnalate, obiezioni e dissensi. Niente modalità, token, tempi o pensieri.

    python -m revisione.cieca prepara esame --uscita cieca
        cieca/per-chi-controlla/verdetto-01.md …, scheda.csv     da dare a chi controlla, con i contratti
        cieca/chiave.json                                        resta a chi organizza
    python -m revisione.cieca conta cieca/per-chi-controlla/scheda.csv cieca/chiave.json
"""

from __future__ import annotations

import argparse
import csv
import json
import random
from pathlib import Path

from .categorie import BENCHMARK
from .misure import NOMI

CIECHE = ("testo", "telepatia")
SEME = 31
COLONNE = ("verdetto", "contratto", "raccomandazione_giusta", "dissenso_atteso_trovato", "importi_giusti", "note")
GIUDIZI = ("raccomandazione_giusta", "dissenso_atteso_trovato", "importi_giusti")
RUOLI = {"legale": "legale", "finanza": "di finanza", "rischio": "di rischio"}


def foglio(numero: str, revisione: dict) -> str:
    """Il foglio di un verdetto, senza niente che dica com'è stato fatto."""
    benchmark = BENCHMARK[revisione["benchmark"]]
    nomi = {c.chiave: c.nome for c in benchmark.categorie}
    ruoli = {c.chiave: c.ruolo for c in benchmark.categorie}
    dati = (revisione.get("verdetto") or {}).get("dati")
    righe = [f"# Verdetto {numero}", "", f"Contratto: `{revisione['contratto']}`", ""]
    if dati is None:
        return "\n".join([*righe, "Il Consiglio non ha dato un verdetto valido.", ""])
    righe += [f"## Raccomandazione: {dati['raccomandazione']}", "", dati.get("motivazione") or "", ""]
    dettagli = {d["categoria"]: d for d in dati.get("dettagli", [])}
    segnalate = [k for k, si in dati["segnalare"].items() if si]
    righe += ["## Clausole segnalate", ""]
    for k in segnalate:
        d = dettagli.get(k, {})
        citazione = f": «{d['citazione']}»" if d.get("citazione") else ""
        motivo = f" ({d['motivazione']})" if d.get("motivazione") else ""
        righe.append(f"- **{nomi.get(k, k)}**{citazione}{motivo}")
    righe += ["" if segnalate else "Nessuna.", ""]
    if dati.get("obiezioni"):
        righe += ["## Obiezioni", ""] + [
            f"- **{nomi.get(o['categoria'], o['categoria'])}**: {o['obiezione']}" for o in dati["obiezioni"]
        ]
        righe.append("")
    righe += ["## Dissensi fra esperti e verdetto", ""]
    for d in revisione.get("dissensi", []):
        esperto = "va segnalata" if d["tipo"] == "grave" else "non va segnalata"
        verdetto = "no" if d["tipo"] == "grave" else "sì"
        ruolo = RUOLI.get(d.get("ruolo") or ruoli.get(d["categoria"]), d.get("ruolo"))
        righe.append(
            f"- **{nomi.get(d['categoria'], d['categoria'])}**: per l'esperto {ruolo} {esperto}, il verdetto dice {verdetto}."
        )
    righe += ["" if revisione.get("dissensi") else "Nessuno.", ""]
    return "\n".join(righe)


def prepara(cartella: Path, uscita: Path, *, seme: int = SEME) -> int:
    voci = []
    for configurazione in CIECHE:
        f = cartella / f"dimostrativo-sviluppo-{configurazione}.jsonl"
        if not f.exists():
            raise SystemExit(f"Manca {f}: servono i giri a testo e in telepatia sul set dimostrativo.")
        voci += [(configurazione, json.loads(r)) for r in f.read_text().splitlines() if r.strip()]
    random.Random(seme).shuffle(voci)
    per_chi_controlla = uscita / "per-chi-controlla"
    per_chi_controlla.mkdir(parents=True, exist_ok=True)
    chiave, scheda = {}, []
    for i, (configurazione, revisione) in enumerate(voci, 1):
        numero = f"{i:02d}"
        (per_chi_controlla / f"verdetto-{numero}.md").write_text(foglio(numero, revisione))
        chiave[f"verdetto-{numero}"] = {"contratto": revisione["contratto"], "configurazione": configurazione}
        scheda.append({"verdetto": f"verdetto-{numero}", "contratto": revisione["contratto"]})
    with (per_chi_controlla / "scheda.csv").open("w", newline="") as f:
        scrittore = csv.DictWriter(f, fieldnames=COLONNE)
        scrittore.writeheader()
        scrittore.writerows(scheda)
    (uscita / "chiave.json").write_text(json.dumps({"seme": seme, "verdetti": chiave}, indent=2, ensure_ascii=False))
    return len(voci)


def conta(scheda: Path, chiave: Path) -> str:
    """Per configurazione, quante volte chi ha controllato ha scritto "sì" su ogni giudizio, fra le righe compilate."""
    verdetti = json.loads(chiave.read_text())["verdetti"]
    conti: dict[str, dict[str, list[int]]] = {c: {g: [0, 0] for g in GIUDIZI} for c in CIECHE}
    with scheda.open() as f:
        for riga in csv.DictReader(f):
            configurazione = verdetti[riga["verdetto"]]["configurazione"]
            for g in GIUDIZI:
                valore = (riga.get(g) or "").strip().lower()
                if valore in ("sì", "si", "no"):
                    conti[configurazione][g][0] += valore != "no"
                    conti[configurazione][g][1] += 1
    righe = [
        "| Configurazione | Raccomandazione giusta | Dissenso atteso trovato | Importi giusti |",
        "|---|---|---|---|",
    ]
    for c in CIECHE:
        celle = [f"{a}/{n}" for a, n in (conti[c][g] for g in GIUDIZI)]
        righe.append(f"| {NOMI[c]} | " + " | ".join(celle) + " |")
    return "\n".join(righe)


def main() -> None:
    parser = argparse.ArgumentParser(description="Il controllo a mano alla cieca.")
    comandi = parser.add_subparsers(dest="comando", required=True)
    p = comandi.add_parser("prepara")
    p.add_argument("cartella", type=Path, help="la cartella dell'eval con i giri sul set dimostrativo")
    p.add_argument("--uscita", type=Path, default=Path("cieca"))
    p.add_argument("--seme", type=int, default=SEME)
    c = comandi.add_parser("conta")
    c.add_argument("scheda", type=Path)
    c.add_argument("chiave", type=Path)
    argomenti = parser.parse_args()
    if argomenti.comando == "prepara":
        n = prepara(argomenti.cartella, argomenti.uscita, seme=argomenti.seme)
        print(
            f"{n} fogli in {argomenti.uscita / 'per-chi-controlla'}; la chiave resta in {argomenti.uscita / 'chiave.json'}"
        )
    else:
        print(conta(argomenti.scheda, argomenti.chiave))


if __name__ == "__main__":
    main()
