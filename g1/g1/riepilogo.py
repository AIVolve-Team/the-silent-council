"""Il verdetto di G1, come pre-registrato in memoria, token e tre zone sulla precisione.

python -m g1.riepilogo risultati/      # stampa il rapporto da pubblicare
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path

SOGLIA_TOKEN = 0.5  # token generati in telepatia almeno il 50% in meno del testo
DIMOSTRATO = -3.0  # entro 3 punti dal testo
STOP = -10.0  # più di 10 punti sotto: qualcosa nel motore è rotto
H100_GB = 80  # sopra, la frase del copione "su una H100 non ci starebbe" si può dire
GIRI = {"testo": "testo", "telepatia": "telepatia (10 passi)", "senza_pensieri": "senza pensieri (m=0)"}


def zona(differenza: float) -> str:
    """`differenza` = precisione della telepatia meno quella del testo, in punti percentuali."""
    if differenza >= DIMOSTRATO:
        return "dimostrato"
    if differenza >= STOP:
        return "si va avanti"
    return "stop"


@dataclass(frozen=True)
class EsitoG1:
    accuratezza: dict[str, float]
    token_generati: dict[str, int]
    riduzione_token: float
    differenza: float
    zona: str
    memoria_ok: bool | None
    passa: bool | None


def accuratezza(righe: list[dict]) -> float:
    return 100 * sum(r["corretto"] for r in righe) / len(righe)


def esito_g1(
    *, testo: list[dict], telepatia: list[dict], senza_pensieri: list[dict], memoria_ok: bool | None = None
) -> EsitoG1:
    giri = {"testo": testo, "telepatia": telepatia, "senza_pensieri": senza_pensieri}
    insiemi = {nome: {r["id"] for r in righe} for nome, righe in giri.items()}
    if len({frozenset(s) for s in insiemi.values()}) != 1:
        raise ValueError(f"i tre giri devono avere gli stessi problemi: { ({k: len(v) for k, v in insiemi.items()}) }")
    precisione = {nome: accuratezza(righe) for nome, righe in giri.items()}
    token = {nome: sum(r["token_generati"] for r in righe) for nome, righe in giri.items()}
    riduzione = 1 - token["telepatia"] / token["testo"]
    differenza = precisione["telepatia"] - precisione["testo"]
    zona_precisione = zona(differenza)
    passa = None if memoria_ok is None else memoria_ok and riduzione >= SOGLIA_TOKEN and zona_precisione != "stop"
    return EsitoG1(precisione, token, riduzione, differenza, zona_precisione, memoria_ok, passa)


def decimale(x: float, cifre: int = 1) -> str:
    return f"{x:.{cifre}f}".replace(".", ",")


def intero(n: int) -> str:
    return f"{n:,}".replace(",", ".")


def leggi(file: Path) -> list[dict]:
    return [json.loads(riga) for riga in file.read_text().splitlines()]


def rapporto(cartella: Path) -> str:
    """Il rapporto in italiano, dai tre giri e, se c'è, da `memoria.json`."""
    tutte = {nome: leggi(cartella / f"{nome}.jsonl") for nome in GIRI}
    # Se il giro si è interrotto, si contano solo i problemi finiti in tutti e tre i modi.
    finiti = set.intersection(*({r["id"] for r in righe} for righe in tutte.values()))
    righe = {nome: [r for r in righe_giro if r["id"] in finiti] for nome, righe_giro in tutte.items()}
    file_ambiente = cartella / "ambiente.json"
    attesi = json.loads(file_ambiente.read_text())["problemi"] if file_ambiente.exists() else len(finiti)
    file_memoria = cartella / "memoria.json"
    memoria = json.loads(file_memoria.read_text()) if file_memoria.exists() else None
    esito = esito_g1(**righe, memoria_ok=None if memoria is None else bool(memoria.get("ok")))

    tabella = [
        "| Giro | Precisione | Token generati | Token letti | Secondi per problema | Messaggi troncati |",
        "|---|---|---|---|---|---|",
    ]
    for nome, titolo in GIRI.items():
        r = righe[nome]
        secondi = sum(x["secondi"] for x in r) / len(r)
        tabella.append(
            f"| {titolo} | {decimale(esito.accuratezza[nome])}% | {intero(esito.token_generati[nome])} "
            f"| {intero(sum(x['token_letti'] for x in r))} | {decimale(secondi)} | {sum(x['troncati'] for x in r)} |"
        )

    riduzione = esito.riduzione_token * 100
    segno = "−" if riduzione >= 0 else "+"
    token_ok = "✓" if esito.riduzione_token >= SOGLIA_TOKEN else "✗"
    punti = ("+" if esito.differenza >= 0 else "−") + decimale(abs(esito.differenza))
    voci = [
        (
            f"- **Token generati in telepatia:** {segno}{decimale(abs(riduzione), 0)}% rispetto al testo "
            f"(soglia: almeno −50%) {token_ok}"
        ),
        f"- **Precisione:** telepatia meno testo = {punti} punti → zona **{esito.zona}**",
    ]
    if memoria is None:
        voci.append("- **Memoria:** manca la misura della memoria (`python -m g1.misure memoria`)")
    else:
        stato = "✓" if memoria.get("ok") else f"✗ {memoria.get('errore', '')}".rstrip()
        voci.append(f"- **Memoria:** motore e Qwen3.6 sulla stessa MI300X senza errori {stato}")
        pesi = memoria.get("pesi_due_modelli_gb")
        if pesi is not None:
            frase = "si può dire" if pesi > H100_GB else "non si può dire"
            voci.append(
                f'- **Pesi dei due modelli:** {decimale(pesi)} GB: la frase *"su una H100 non ci starebbe"* {frase} '
                f"(serve più di {H100_GB} GB)"
            )
    verdetto = {True: "**G1 passa**", False: "**G1 non passa**", None: "**G1 ancora aperto**"}[esito.passa]
    intestazione = ["## G1: il motore sulla MI300X", ""]
    if len(finiti) < attesi:
        parola = "problema" if len(finiti) == 1 else "problemi"
        intestazione += [f"> **Parziale: {len(finiti)} {parola} su {attesi}** finiti nei tre modi.", ""]
    return "\n".join([*intestazione, *tabella, "", *voci, "", verdetto, ""])


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("cartella", type=Path)
    print(rapporto(parser.parse_args().cartella))


if __name__ == "__main__":
    main()
