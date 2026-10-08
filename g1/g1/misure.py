"""Le altre misure di G1: memoria, impronta, ricalcolo dei pensieri e confronto con fp32.

    python -m g1.misure memoria --pesi-vllm-gb 71.9 --uscita risultati/memoria.json   # con vLLM acceso
    python -m g1.misure fp32 --problemi 5 --uscita risultati/fp32.json                  # con vLLM spento

Se il generatore delle fatture non c'è ancora, il testo lungo è fatto di problemi di GSM8K in fila.
"""

from __future__ import annotations

import argparse
import gc
import json
import shutil
import subprocess
import time
from pathlib import Path

import torch
from motore import Modello, Motore, Staffetta
from motore.controllo import ControlloImpronta

from .esegui import ANALISTI, RISOLUTORE, esegui_giro, vincolo_sdpa
from .gsm8k import carica_problemi

GB = 1e9


def testo_lungo(tokenizer, token: int) -> str:
    """Problemi di GSM8K uno dopo l'altro, finché il testo arriva ad almeno `token` token."""
    problemi = carica_problemi()
    pezzi: list[str] = []
    while True:
        pezzi.append(problemi[len(pezzi) % len(problemi)].domanda)
        testo = "\n\n".join(pezzi)
        if len(tokenizer(testo).input_ids) >= token:
            return testo


def byte_kv(messaggio) -> int:
    return sum(
        t.numel() * t.element_size() for kv in (messaggio.kv_lettura, messaggio.kv_pensieri) for p in kv for t in p
    )


def vram_rocm() -> dict | None:
    """La memoria della scheda vista da ROCm, compreso vLLM che gira in un altro processo."""
    if shutil.which("rocm-smi") is None:
        return None
    uscita = subprocess.run(
        ["rocm-smi", "--showmeminfo", "vram", "--json"], capture_output=True, text=True, check=False
    )
    return json.loads(uscita.stdout) if uscita.returncode == 0 else {"errore": uscita.stderr.strip()}


def picco_gb(dispositivo: str) -> float | None:
    if dispositivo == "cuda":
        return torch.cuda.max_memory_reserved() / GB
    if dispositivo == "mps":
        return torch.mps.driver_allocated_memory() / GB
    return None


def misura_motore(motore: Motore, *, token: int = 4000) -> dict:
    """La staffetta in telepatia su un testo lungo: memoria di picco, peso di un messaggio, tempo dell'impronta e
    ricalcolo dei pensieri, che con gli stati del messaggio stesso deve ridare la stessa KV."""
    modello = motore.modello
    if modello.dispositivo == "cuda":
        torch.cuda.reset_peak_memory_stats()
    testo = testo_lungo(modello.tokenizer, token)
    staffetta = Staffetta(motore, ANALISTI, RISOLUTORE, passi_latenti=10)
    with vincolo_sdpa(modello.dispositivo):
        esito = staffetta.esegui("g1-memoria", {a.nome: testo for a in [*ANALISTI, RISOLUTORE]}, max_token=16)
        primo = esito.messaggi[0]
        inizio = time.perf_counter()
        impronta = ControlloImpronta()(primo, [])
        secondi_impronta = time.perf_counter() - inizio
        ricalcolato = motore.ricalcola_pensieri(primo, [])
    identico = all(
        torch.equal(a, b)
        for (ka, va), (kb, vb) in zip(primo.kv_pensieri, ricalcolato.kv_pensieri, strict=True)
        for a, b in ((ka, kb), (va, vb))
    )
    return {
        "dispositivo": modello.dispositivo,
        "dtype": str(modello.dtype).removeprefix("torch."),
        "token_letti_primo_agente": primo.n_lettura,
        "kv_messaggio_gb": byte_kv(primo) / GB,
        "secondi_impronta": secondi_impronta,
        "impronta_ok": impronta.passa,
        "ricalcolo_identico": identico,
        "secondi_staffetta": esito.secondi,
        "fermata": None if esito.fermata is None else f"{esito.fermata.controllo}: {esito.fermata.motivo}",
        "picco_motore_gb": picco_gb(modello.dispositivo),
        "pesi_motore_gb": sum(p.numel() * p.element_size() for p in modello.rete.parameters()) / GB,
        "vram_rocm": vram_rocm(),
    }


def confronto_fp32(nome: str, revisione: str, problemi: int, cartella: Path, max_token_risposta: int) -> dict:
    """Gli stessi problemi in telepatia con il modello in fp32 e in bf16: le risposte devono coincidere."""
    righe = {}
    for dtype in (torch.float32, torch.bfloat16):
        etichetta = str(dtype).removeprefix("torch.")
        motore = Motore(Modello(nome, revisione, dtype=dtype), max_token_testo=1024)
        righe[etichetta] = esegui_giro(
            motore,
            "telepatia",
            carica_problemi(problemi),
            cartella / f"fp32-{etichetta}.jsonl",
            max_token_risposta=max_token_risposta,
        )
        del motore
        gc.collect()
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
    coppie = list(zip(righe["float32"], righe["bfloat16"], strict=True))
    return {
        "problemi": problemi,
        "risposte_uguali": sum(a["risposta"] == b["risposta"] for a, b in coppie),
        "testi_uguali": sum(a["testo_finale"] == b["testo_finale"] for a, b in coppie),
        "giuste_fp32": sum(a["corretto"] for a, _ in coppie),
        "giuste_bf16": sum(b["corretto"] for _, b in coppie),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("misura", choices=["memoria", "fp32"])
    parser.add_argument("--modello", default="Qwen/Qwen3-14B")
    parser.add_argument("--revisione", default="40c069824f4251a91eefaf281ebe4c544efd3e18")
    parser.add_argument("--token", type=int, default=4000, help="lunghezza del testo letto da ogni agente")
    parser.add_argument("--pesi-vllm-gb", type=float, default=None, help="dal log di vLLM: 'Model loading took …'")
    parser.add_argument("--problemi", type=int, default=5)
    parser.add_argument("--max-token-risposta", type=int, default=512)
    parser.add_argument("--uscita", type=Path, required=True)
    argomenti = parser.parse_args()
    argomenti.uscita.parent.mkdir(parents=True, exist_ok=True)

    if argomenti.misura == "fp32":
        risultato = confronto_fp32(
            argomenti.modello,
            argomenti.revisione,
            argomenti.problemi,
            argomenti.uscita.parent,
            argomenti.max_token_risposta,
        )
    else:
        try:
            risultato = misura_motore(Motore(Modello(argomenti.modello, argomenti.revisione)), token=argomenti.token)
            risultato["ok"] = risultato["fermata"] is None and risultato["impronta_ok"]
        except torch.OutOfMemoryError as errore:
            risultato = {"ok": False, "errore": f"memoria finita: {errore}"}
        risultato["pesi_vllm_gb"] = argomenti.pesi_vllm_gb
        if argomenti.pesi_vllm_gb is not None and "pesi_motore_gb" in risultato:
            risultato["pesi_due_modelli_gb"] = risultato["pesi_motore_gb"] + argomenti.pesi_vllm_gb
    argomenti.uscita.write_text(json.dumps(risultato, indent=2, ensure_ascii=False) + "\n")
    print(json.dumps(risultato, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
