"""I tre giri di G1 su GSM8K: testo, telepatia con 10 passi latenti, telepatia senza pensieri.

    python -m g1.esegui --uscita risultati/

Ogni problema finito si scrive subito in `<uscita>/<modo>.jsonl`: se il giro si interrompe, rilanciando lo stesso
comando si riparte dal primo problema che manca.
"""

from __future__ import annotations

import argparse
import contextlib
import json
import platform
from datetime import UTC, datetime
from pathlib import Path

import torch
import transformers
from motore import Agente, Modello, Motore, Staffetta
from motore.messaggio import TELEPATIA, TESTO

from .gsm8k import Problema, carica_problemi, corretta, estrai_risposta

MODI = {"testo": (TESTO, 0), "telepatia": (TELEPATIA, 10), "senza_pensieri": (TELEPATIA, 0)}

# Tre agenti che ragionano e uno che risponde, come la catena di LatentMAS, con nomi e prompt nostri.
PIANIFICATORE = Agente(
    "pianificatore",
    "You are the first of three analysts working together on a math word problem. Read the problem carefully and "
    "work out a clear step-by-step plan to solve it: which quantities matter and which operations to do, in order. "
    "Do not give the final answer.",
)
REVISORE = Agente(
    "revisore",
    "You are the second of three analysts working together on a math word problem. You know the first analyst's "
    "plan. Check it step by step: find mistakes in reasoning or arithmetic and anything missing, and say how to fix "
    "them.",
)
PERFEZIONATORE = Agente(
    "perfezionatore",
    "You are the third of three analysts working together on a math word problem. You know the plan and the review "
    "of your colleagues. Combine them into a corrected, complete solution path, with the calculations.",
)
RISOLUTORE = Agente(
    "risolutore",
    "You solve math word problems using what your colleagues worked out. Reason briefly and compute carefully. "
    "End with the final answer as a number in the form \\boxed{answer}.",
)
ANALISTI = [PIANIFICATORE, REVISORE, PERFEZIONATORE]


def vincolo_sdpa(dispositivo: str, dtype: torch.dtype = torch.bfloat16):
    """Sulla MI300X niente ripiego sul backend math di SDPA: se i kernel veloci non bastano, meglio un errore.

    Fa eccezione il riferimento in fp32 del confronto: senza maschera Transformers passa a SDPA le 8 teste KV di
    Qwen3 con `enable_gqa`, che in fp32 nessun kernel veloce accetta (flash vuole bf16, efficient vuole le teste
    espanse). Il riferimento va sul math, così è anche indipendente dai kernel che controlla.
    """
    if dispositivo != "cuda":
        return contextlib.nullcontext()
    from torch.nn.attention import SDPBackend, sdpa_kernel

    if dtype == torch.float32:
        return sdpa_kernel([SDPBackend.MATH])
    return sdpa_kernel([SDPBackend.FLASH_ATTENTION, SDPBackend.EFFICIENT_ATTENTION])


def risolvi(motore: Motore, modo: str, problema: Problema, max_token_risposta: int) -> dict:
    modalita, passi = MODI[modo]
    staffetta = Staffetta(motore, ANALISTI, RISOLUTORE, modalita=modalita, passi_latenti=passi)
    testo = f"Problem:\n{problema.domanda}"
    testi = {agente.nome: testo for agente in [*ANALISTI, RISOLUTORE]}
    with vincolo_sdpa(motore.modello.dispositivo, motore.modello.dtype):
        esito = staffetta.esegui(f"g1-{modo}-{problema.id}", testi, max_token=max_token_risposta)
    finale = esito.finale.testo if esito.finale else None
    risposta = estrai_risposta(finale) if finale else None
    troncati = sum(m.etichetta["token_generati"] >= motore.max_token_testo for m in esito.messaggi if m.testo)
    if esito.finale and esito.finale.token_generati >= max_token_risposta:
        troncati += 1
    return {
        "id": problema.id,
        "modo": modo,
        "passi_latenti": passi,
        "risposta_giusta": problema.risposta,
        "risposta": risposta,
        "corretto": corretta(risposta, problema.risposta),
        "token_generati": esito.token_generati,
        "token_letti": esito.token_letti,
        "posizioni_latenti": esito.posizioni_latenti,
        "secondi": round(esito.secondi, 3),
        "troncati": troncati,
        "fermata": None if esito.fermata is None else f"{esito.fermata.controllo}: {esito.fermata.motivo}",
        "testo_finale": finale,
    }


def esegui_giro(
    motore: Motore, modo: str, problemi: list[Problema], uscita: Path, *, max_token_risposta: int = 1024
) -> list[dict]:
    """Risolve i problemi che mancano in `uscita` e restituisce tutte le righe, vecchie e nuove, nell'ordine."""
    fatte = {}
    if uscita.exists():
        fatte = {r["id"]: r for r in map(json.loads, uscita.read_text().splitlines())}
    uscita.parent.mkdir(parents=True, exist_ok=True)
    with uscita.open("a") as f:
        for problema in problemi:
            if problema.id in fatte:
                continue
            riga = risolvi(motore, modo, problema, max_token_risposta)
            f.write(json.dumps(riga, ensure_ascii=False) + "\n")
            f.flush()
            fatte[problema.id] = riga
            print(
                f"{modo} {problema.id}: {'giusta' if riga['corretto'] else 'sbagliata'} "
                f"({riga['token_generati']} token, {riga['secondi']} s)",
                flush=True,
            )
    return [fatte[p.id] for p in problemi]


def ambiente(modello: Modello, argomenti: argparse.Namespace) -> dict:
    dispositivo = modello.dispositivo
    return {
        "ora": datetime.now(UTC).isoformat(),
        "modello": modello.nome,
        "revisione": modello.revisione,
        "dtype": str(modello.dtype).removeprefix("torch."),
        "dispositivo": dispositivo,
        "gpu": torch.cuda.get_device_name(0) if dispositivo == "cuda" else platform.processor(),
        "torch": torch.__version__,
        "hip": getattr(torch.version, "hip", None),
        "transformers": transformers.__version__,
        "max_token_testo": argomenti.max_token_testo,
        "max_token_risposta": argomenti.max_token_risposta,
        "problemi": argomenti.problemi,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--modello", default="Qwen/Qwen3-14B")
    parser.add_argument("--revisione", default="40c069824f4251a91eefaf281ebe4c544efd3e18")
    parser.add_argument("--problemi", type=int, default=100)
    parser.add_argument("--modi", nargs="+", choices=list(MODI), default=list(MODI))
    parser.add_argument("--uscita", type=Path, default=Path("risultati"))
    parser.add_argument("--max-token-testo", type=int, default=1024, help="per agente, nel modo a testo")
    parser.add_argument("--max-token-risposta", type=int, default=1024, help="per la risposta finale, in tutti i modi")
    parser.add_argument(
        "--dtype", choices=["bf16", "fp32"], default=None, help="predefinito: bf16 su GPU, fp32 altrove"
    )
    argomenti = parser.parse_args()

    dtype = {"bf16": torch.bfloat16, "fp32": torch.float32, None: None}[argomenti.dtype]
    modello = Modello(argomenti.modello, argomenti.revisione, dtype=dtype)
    motore = Motore(modello, max_token_testo=argomenti.max_token_testo)
    argomenti.uscita.mkdir(parents=True, exist_ok=True)
    (argomenti.uscita / "ambiente.json").write_text(json.dumps(ambiente(modello, argomenti), indent=2) + "\n")
    # Un problema alla volta nei tre modi: se il tempo finisce, i problemi fatti si confrontano comunque.
    for problema in carica_problemi(argomenti.problemi):
        for modo in argomenti.modi:
            esegui_giro(
                motore,
                modo,
                [problema],
                argomenti.uscita / f"{modo}.jsonl",
                max_token_risposta=argomenti.max_token_risposta,
            )


if __name__ == "__main__":
    main()
