"""La taratura del Consiglio sul set di sviluppo: quanti passi latenti e quali soglie di confidenza.

Legge i giri di `revisione.esegui` con più valori dei passi (per esempio `--passi 0 10 20 40`) e scrive le tabelle da
incollare nel ticket, solo con numeri aggregati.

Uso:
    python -m revisione.taratura risultati --benchmark cuad
"""

from __future__ import annotations

import argparse
import json
import re
from itertools import pairwise
from pathlib import Path

from .esegui import _contratti_e_risposte
from .punteggio import accordo, vota

# I passi fra cui si sceglie: 10, 20 e 40 di «Eval pre-registrato», e lo 0, che è la sua verifica anticipata dei pensieri. Con la stessa
# regola dei pareggi, lo 0 vince solo se nessun valore con i pensieri lo batte di almeno 1 punto: allora i pensieri non
# aiutano e il sistema si corregge prima del congelamento, come «Eval pre-registrato» permette (PREREGISTRAZIONE.md).
CANDIDATI = (0, 10, 20, 40)
PAREGGIO = 1.0
# Le soglie si propongono su una griglia: la confidenza è la probabilità della posizione scelta, fra 0,5 e 1.
GRIGLIA = (0.6, 0.7, 0.8, 0.85, 0.9, 0.95, 0.99)
GIUSTE_ALTA, GIUSTE_MEDIA = 0.9, 0.7

_NOME = re.compile(
    r"^(?P<benchmark>[a-z]+)-sviluppo-(?P<modalita>telepatia|testo)-m(?P<passi>\d+)-(?P<modello>.+?)"
    r"(?P<senza>-senza-riallineamento)?$"
)


def scegli_passi(f1: dict[int, float]) -> int:
    """Vince l'F1 più alto fra 0, 10, 20 e 40; sotto 1 punto di differenza vince il valore con meno passi."""
    candidati = [m for m in CANDIDATI if m in f1]
    if not candidati:
        raise ValueError("servono i giri con 0, 10, 20 o 40 passi")
    migliore = max(f1[m] for m in candidati)
    return min(m for m in candidati if migliore - f1[m] < PAREGGIO)


def decisioni(revisioni: list[dict], giuste: dict) -> list[tuple[float, bool]]:
    """(confidenza della posizione scelta, giusta) per ogni sì/no del verdetto e delle note."""
    fuori = []
    for r in revisioni:
        scritti = [r.get("verdetto")] + list((r.get("note") or {}).values())
        for scritto in scritti:
            if not scritto or not scritto.get("dati"):
                continue
            for categoria, si in scritto["dati"]["segnalare"].items():
                p = scritto.get("probabilita_si", {}).get(categoria)
                giusta = giuste.get((r["contratto"], categoria))
                if p is not None and giusta is not None:
                    fuori.append((p if si else 1 - p, si == giusta))
    return fuori


def proponi_soglie(voci: list[tuple[float, bool]]) -> tuple[float, float] | None:
    """Una proposta, da rivedere: "alta" è la soglia più bassa della griglia sopra cui il modello ha ragione almeno
    9 volte su 10; "media" la più bassa sotto "alta" fra cui e "alta" ha ragione almeno 7 volte su 10."""

    def quota(dentro: list[bool]) -> float:
        return sum(dentro) / len(dentro) if dentro else 0.0

    alte = [t for t in GRIGLIA if quota([g for c, g in voci if c >= t]) >= GIUSTE_ALTA and any(c >= t for c, _ in voci)]
    if not alte:
        return None
    alta = min(alte)
    medie = [
        t
        for t in GRIGLIA
        if t < alta
        and quota([g for c, g in voci if t <= c < alta]) >= GIUSTE_MEDIA
        and any(t <= c < alta for c, _ in voci)
    ]
    return alta, min(medie) if medie else alta


def _n(x: float, cifre: int = 1) -> str:
    return f"{x:.{cifre}f}".replace(".", ",")


def rapporto(cartella: Path, benchmark: str) -> str:
    gruppi: dict[tuple[str, bool], dict[str, dict[int, list[dict]]]] = {}
    for f in sorted(cartella.glob(f"{benchmark}-sviluppo-*.jsonl")):
        nome = _NOME.match(f.stem)
        if not nome:
            continue
        righe = [json.loads(r) for r in f.read_text().splitlines() if r.strip()]
        chiave = (nome["modello"], not nome["senza"])
        gruppi.setdefault(chiave, {}).setdefault(nome["modalita"], {})[int(nome["passi"])] = righe
    if not gruppi:
        return f"Nessun giro di sviluppo di {benchmark} in {cartella}."
    _, giuste = _contratti_e_risposte(benchmark, "sviluppo")
    if not giuste:
        raise SystemExit(
            f"Mancano le risposte giuste di {benchmark}: per il set dimostrativo vedi CONSIGLIO_SET_DIMOSTRATIVO."
        )
    parti = [f"# Taratura su {benchmark}, set di sviluppo", ""]
    for (modello, riallineamento), modalita in gruppi.items():
        parti += [f"## {modello}, riallineamento {'acceso' if riallineamento else 'spento'}", ""]
        parti += [
            "| Modalità | Passi | Contratti | F1 | MCC | Note come verdetto | Accordo note-verdetto |",
            "|---|---|---|---|---|---|---|",
        ]
        for nome_modalita, giri in sorted(modalita.items()):
            for passi, righe in sorted(giri.items()):
                voto = vota(righe, giuste)
                uguali, confrontate = accordo(righe)
                parti.append(
                    f"| {nome_modalita} | {passi} | {len(righe)} | {_n(voto.f1)} | {_n(voto.mcc, 2)} | "
                    f"{_n(vota(righe, giuste, dalle_note=True).f1)} | {uguali}/{confrontate} |"
                )
        parti.append("")
        telepatia = modalita.get("telepatia", {})
        f1 = {m: vota(r, giuste).f1 for m, r in telepatia.items()}
        if any(m in f1 for m in CANDIDATI):
            scelto = scegli_passi(f1)
            parti.append(f"**Passi scelti:** {scelto} (F1 {_n(f1[scelto])}), con la regola di «Eval pre-registrato».")
            if scelto == 0:
                parti.append(
                    "Con i pensieri l'F1 non sale di almeno 1 punto: sul set di sviluppo i pensieri non aiutano. Per «Eval pre-registrato» il "
                    "sistema si corregge prima del congelamento: 0 passi, niente prove sui pensieri, frase di riserva."
                )
            voci = decisioni(telepatia[scelto], giuste) + decisioni(modalita.get("testo", {}).get(scelto, []), giuste)
            parti += ["", "**Confidenza** (verdetti e note, telepatia e testo con i passi scelti):", ""]
            parti += ["| Confidenza della posizione | Decisioni | Giuste |", "|---|---|---|"]
            bordi = (0.5, *GRIGLIA, 1.01)
            for basso, alto in pairwise(bordi):
                dentro = [g for c, g in voci if basso <= c < alto]
                if dentro:
                    giuste_quota = 100 * sum(dentro) / len(dentro)
                    parti.append(
                        f"| da {_n(basso, 2)} a {_n(min(alto, 1), 2)} | {len(dentro)} | {_n(giuste_quota, 0)}% |"
                    )
            proposta = proponi_soglie(voci)
            parti.append("")
            parti.append(
                f"**Soglie proposte** (da rivedere): alta da {_n(proposta[0], 2)}, media da {_n(proposta[1], 2)}."
                if proposta
                else "**Soglie:** con questi dati nessuna soglia arriva a 9 decisioni giuste su 10."
            )
        parti.append("")
    return "\n".join(parti)


def main() -> None:
    parser = argparse.ArgumentParser(description="Taratura di passi latenti e soglie di confidenza.")
    parser.add_argument("cartella", type=Path)
    parser.add_argument("--benchmark", default="cuad")
    argomenti = parser.parse_args()
    print(rapporto(argomenti.cartella, argomenti.benchmark))


if __name__ == "__main__":
    main()
