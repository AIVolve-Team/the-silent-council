"""G2 e la scelta dei passi latenti: la lettura del verificatore sugli 8 dati critici, telepatia contro testo.

    python -m harness.g2 esegui ../dati/insiemi/sviluppo --modello Qwen/Qwen3-14B --uscita risultati/g2
    python -m harness.g2 rapporto risultati/g2 ../dati/insiemi/sviluppo

- **Accuratezza per campo** = dati giusti / dati totali, sulle 100 fatture di sviluppo, contro la verità del generatore;
  un `null` dove la verità ha un valore conta come errore.
- **Soglia:** telepatia ≥ testo − 3 punti. Intervallo al 95% con bootstrap appaiato sulla differenza: "dimostrato" se
  anche il limite inferiore sta entro i −3 punti, altrimenti "compatibile". Sotto i −3 punti G2 non passa.
- **Passi latenti:** 10, 20 e 40; vince l'accuratezza più alta, e sotto 1 punto di differenza vince il valore con meno
  passi. `m=0` si misura nella stessa prova, ma non è un candidato.
"""

from __future__ import annotations

import json
import random
from dataclasses import dataclass
from pathlib import Path

from fatture.genera import Caso
from fatture.insiemi import carica_casi
from pipeline.riepilogo import dati_giusti
from pipeline.schemi import lettura_da

SOGLIA = -3.0
CANDIDATI = (10, 20, 40)
CAMPI = 8


@dataclass(frozen=True)
class Intervallo:
    differenza: float  # telepatia meno testo, in punti percentuali
    basso: float
    alto: float


def differenza(telepatia: list[int], testo: list[int], campi: int = CAMPI) -> float:
    return round(100 * (sum(telepatia) - sum(testo)) / (campi * len(telepatia)), 4)


def bootstrap(
    telepatia: list[int], testo: list[int], *, campi: int = CAMPI, ripetizioni: int = 10_000, seme: int = 50
) -> Intervallo:
    """Bootstrap appaiato: si ricampionano le fatture, con le due letture della stessa fattura sempre insieme."""
    if len(telepatia) != len(testo) or not telepatia:
        raise ValueError("servono le stesse fatture nei due modi: le coppie devono essere appaiate")
    rng = random.Random(seme)
    n = len(telepatia)
    campioni = []
    for _ in range(ripetizioni):
        scelte = [rng.randrange(n) for _ in range(n)]
        campioni.append(differenza([telepatia[i] for i in scelte], [testo[i] for i in scelte], campi))
    campioni.sort()
    basso = campioni[round(0.025 * (ripetizioni - 1))]
    alto = campioni[round(0.975 * (ripetizioni - 1))]
    return Intervallo(differenza(telepatia, testo, campi), basso, alto)


def esito_g2(intervallo: Intervallo) -> str:
    if intervallo.differenza < SOGLIA:
        return "no"
    return "dimostrato" if intervallo.basso >= SOGLIA else "compatibile"


def scegli_passi(accuratezze: dict[int, float]) -> int:
    candidati = {m: a for m, a in accuratezze.items() if m in CANDIDATI}
    migliore = max(candidati.values())
    return min(m for m, a in candidati.items() if migliore - a < 1.0)


@dataclass
class RisultatoG2:
    accuratezze: dict  # "testo" e ogni numero di passi latenti → accuratezza per campo, in percento
    passi: int | None
    intervallo: Intervallo | None
    esito: str | None
    fatture: int | None = None  # quelle finite in tutti i giri, le sole su cui si confronta


def giusti_per_fattura(file: Path, casi: dict[str, Caso]) -> dict[str, int]:
    """Per ogni fattura, quanti degli 8 dati critici la lettura ha giusti. Senza lettura (staffetta fermata prima, o
    errore): zero, come un `null` dove la verità ha un valore."""
    righe = [json.loads(r) for r in file.read_text().splitlines()]
    return {r["id"]: dati_giusti(lettura_da(casi[r["id"]].impegno), r.get("lettura")) for r in righe}


def risultato_g2(cartella: Path, casi: dict[str, Caso]) -> RisultatoG2:
    giri = {"testo": cartella / "testo" / "testo.jsonl"}
    giri |= {m: cartella / f"m{m}" / "telepatia.jsonl" for m in (0, *CANDIDATI)}
    giusti = {chiave: giusti_per_fattura(file, casi) for chiave, file in giri.items() if file.exists()}
    giusti = {chiave: v for chiave, v in giusti.items() if v}
    # Se il tempo finisce a metà di una fattura, si confronta solo sulle fatture finite in tutti i giri.
    comuni = sorted(set.intersection(*(set(v) for v in giusti.values()))) if giusti else []
    if not comuni:
        return RisultatoG2({}, None, None, None, 0)
    accuratezze = {k: 100 * sum(v[i] for i in comuni) / (CAMPI * len(comuni)) for k, v in giusti.items()}
    candidati = {m: a for m, a in accuratezze.items() if m in CANDIDATI}
    passi = scegli_passi(candidati) if candidati else None
    if passi is None or "testo" not in giusti:
        return RisultatoG2(accuratezze, passi, None, None, len(comuni))
    intervallo = bootstrap([giusti[passi][i] for i in comuni], [giusti["testo"][i] for i in comuni])
    return RisultatoG2(accuratezze, passi, intervallo, esito_g2(intervallo), len(comuni))


def punti(x: float) -> str:
    return ("+" if x >= 0 else "−") + f"{abs(x):.1f}".replace(".", ",")


def testo_g2(r: RisultatoG2) -> str:
    righe = ["## G2: la telepatia conserva i numeri delle fatture?", "", "| Giro | Lettura giusta |", "|---|---|"]
    for chiave in ("testo", 0, *CANDIDATI):
        if chiave in r.accuratezze:
            nome = "testo" if chiave == "testo" else f"telepatia, {chiave} passi"
            righe.append(f"| {nome} | {r.accuratezze[chiave]:.1f}% |".replace(".", ","))
    righe.append("")
    if r.fatture is not None:
        righe += [f"Misurata sulle {r.fatture} fatture finite in tutti i giri.", ""]
    if r.passi is not None:
        righe.append(f"Passi scelti: **{r.passi} passi latenti** (il migliore; sotto 1 punto vince chi ne ha meno).")
    if r.intervallo is None:
        righe.append("Manca un giro: G2 non si può ancora calcolare.")
        return "\n".join(righe) + "\n"
    i = r.intervallo
    righe.append(
        f"Telepatia meno testo: **{punti(i.differenza)} punti**, intervallo al 95% da {punti(i.basso)} a {punti(i.alto)}"
        " (bootstrap appaiato, soglia −3 punti)."
    )
    righe += ["", f"**G2 passa: {r.esito}**" if r.esito != "no" else "**G2 non passa: si passa al Consiglio**"]
    return "\n".join(righe) + "\n"


def esegui(argomenti) -> None:
    """I cinque giri sullo sviluppo, una fattura alla volta in tutti: se il tempo finisce, i confronti restano."""
    from motore import Modello
    from pipeline.giro import DTYPE, MODELLI, esegui_giro
    from pipeline.sportello import chiavi_di_prova

    modello = Modello(argomenti.modello, MODELLI[argomenti.modello], dtype=DTYPE.get(argomenti.dtype))
    chiavi = chiavi_di_prova(argomenti.chiavi)
    giri = [("testo", "testo", 0)] + [(f"m{m}", "telepatia", m) for m in (0, *CANDIDATI)]
    n = len(carica_casi(argomenti.insieme)) if argomenti.limite is None else argomenti.limite
    for k in range(1, n + 1):
        for cartella, modalita, passi in giri:
            esegui_giro(modello, argomenti.insieme, modalita, argomenti.uscita / cartella, chiavi, passi_latenti=passi,
                        limite=k)  # fmt: skip


def main() -> None:
    import argparse

    from pipeline.giro import DTYPE, MODELLI

    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    comandi = parser.add_subparsers(dest="comando", required=True)
    e = comandi.add_parser("esegui", help="i cinque giri sulle fatture di sviluppo")
    e.add_argument("insieme", type=Path)
    e.add_argument("--modello", default="Qwen/Qwen3-14B", choices=list(MODELLI))
    e.add_argument("--dtype", choices=list(DTYPE), default=None)
    e.add_argument("--limite", type=int, default=None)
    e.add_argument("--uscita", type=Path, default=Path("risultati/g2"))
    e.add_argument("--chiavi", type=Path, default=Path.home() / ".sportello" / "chiavi-prova")
    r = comandi.add_parser("rapporto", help="G2 e i passi scelti, da pubblicare")
    r.add_argument("cartella", type=Path)
    r.add_argument("insieme", type=Path)
    argomenti = parser.parse_args()
    if argomenti.comando == "esegui":
        esegui(argomenti)
    else:
        casi = {c.id: c for c in carica_casi(argomenti.insieme)}
        print(testo_g2(risultato_g2(argomenti.cartella, casi)))


if __name__ == "__main__":
    main()
