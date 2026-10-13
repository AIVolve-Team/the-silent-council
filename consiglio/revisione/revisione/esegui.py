"""Fa girare il Consiglio su un insieme di contratti e scrive una revisione per riga.

Esempi:
    python -m revisione.esegui --benchmark cuad --insieme sviluppo --modalita telepatia --passi 10
    python -m revisione.esegui --benchmark dimostrativo --modalita testo
    python -m revisione.esegui --benchmark cuad --insieme sviluppo --passi 0 10 20 40   # taratura dei passi
    python -m revisione.esegui --benchmark dimostrativo --senza-riallineamento --passi 0 10 40   # diagnosi
"""

from __future__ import annotations

import argparse
import gc
import json
from collections import Counter
from pathlib import Path

import torch
from motore import TELEPATIA, TESTO, Modello, Motore

from .categorie import BENCHMARK
from .consiglio import MAX_TOKEN_ANALISI, Consiglio
from .dati import contratti, dimostrativo, risposte_giuste
from .punteggio import accordo, vota

MODELLI = {
    "Qwen/Qwen3-0.6B": "c1899de289a04d12100db370d81485cdf75e47ca",
    "Qwen/Qwen3-1.7B": "70d244cc86ccca08cf5af4e1e306ecf908b1ad5e",
    "Qwen/Qwen3-4B": "1cfa9a7208912126459214e8b04321603b3df60c",
    "Qwen/Qwen3-8B": "b968826d9c46dd6066d109eabc6255188de91218",
    # Il modello del Consiglio, alla stessa revisione del tokenizer usato per contare i token.
    "Qwen/Qwen3-14B": "40c069824f4251a91eefaf281ebe4c544efd3e18",
}


def _contratti_e_risposte(benchmark: str, insieme: str) -> tuple[list[tuple[str, str]], dict]:
    if benchmark == "dimostrativo":
        voci = dimostrativo()
        giuste = {(cid, r["categoria"]): r["da_segnalare"] for cid, _, attesa in voci for r in attesa["righe"]}
        return [(cid, testo) for cid, testo, _ in voci], giuste
    return contratti(benchmark, insieme), risposte_giuste(benchmark, insieme)


def libera_memoria() -> None:
    """Fra un contratto e l'altro: su un Mac la cache della GPU non torna da sola al sistema."""
    gc.collect()
    if torch.backends.mps.is_available():
        torch.mps.empty_cache()
    elif torch.cuda.is_available():
        torch.cuda.empty_cache()


def sintesi(revisioni: list[dict], giuste: dict) -> str:
    voto = vota(revisioni, giuste)
    # Le note prese come verdetto e l'accordo con il verdetto dicono dove si perde una segnalazione: negli esperti o
    # nel relatore.
    dalle_note = vota(revisioni, giuste, dalle_note=True)
    uguali, confrontate = accordo(revisioni)
    note = [n for r in revisioni for n in r["note"].values()]
    validi = sum(r["verdetto"] is not None and r["verdetto"]["dati"] is not None for r in revisioni)
    dissensi = Counter(d["tipo"] for r in revisioni for d in r["dissensi"])
    n = len(revisioni) or 1
    return (
        f"{len(revisioni)} contratti | verdetti validi {validi}/{len(revisioni)} | note valide "
        f"{sum(x['dati'] is not None for x in note)}/{len(note)} | F1 {voto.f1:.1f} (P {voto.precisione:.1f}, "
        f"R {voto.richiamo:.1f}, MCC {voto.mcc:.2f}; sempre sì {voto.f1_sempre_si:.1f}) | note come verdetto F1 "
        f"{dalle_note.f1:.1f} (P {dalle_note.precisione:.1f}, R {dalle_note.richiamo:.1f}) | note e verdetto d'accordo "
        f"{uguali}/{confrontate} | dissensi {dict(dissensi)} | "
        f"token generati {sum(r['token_generati'] for r in revisioni) / n:.0f} e letti "
        f"{sum(r['token_letti'] for r in revisioni) / n:.0f} per contratto | {sum(r['secondi'] for r in revisioni) / n:.0f} s"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Fa girare il Consiglio su un insieme di contratti.")
    parser.add_argument("--benchmark", choices=sorted(BENCHMARK), required=True)
    parser.add_argument("--insieme", choices=["sviluppo", "test"], default="sviluppo")
    parser.add_argument("--modalita", choices=[TELEPATIA, TESTO], default=TELEPATIA)
    parser.add_argument("--passi", type=int, nargs="+", default=[10], help="passi latenti; più valori per la taratura")
    parser.add_argument("--modello", default="Qwen/Qwen3-1.7B")
    parser.add_argument("--revisione", help="revisione del modello su Hugging Face (di default quella fissata qui)")
    parser.add_argument("--limite", type=int, help="solo i primi N contratti, fra quelli entro --max-token")
    parser.add_argument(
        "--max-token", type=int, help="salta i contratti più lunghi (su un Mac la memoria della staffetta non basta)"
    )
    parser.add_argument("--traduci", action="store_true", help="traduzione italiana delle citazioni")
    parser.add_argument(
        "--senza-riallineamento",
        action="store_true",
        help="i passi latenti senza la matrice W_a di LatentMAS, che lì è spenta di default (diagnosi del 12/10)",
    )
    parser.add_argument(
        "--dtype",
        choices=["float32", "bfloat16", "float16"],
        help="di default bf16 su GPU, fp32 altrove; su un Mac da 16 GB conviene bf16",
    )
    parser.add_argument("--uscita", type=Path, default=Path("risultati"))
    argomenti = parser.parse_args()

    if argomenti.insieme == "test":
        raise SystemExit(
            "Il test si fa girare solo con l'eval pre-registrato, una volta, dopo il commit delle regole."
        )
    dtype = getattr(torch, argomenti.dtype) if argomenti.dtype else None
    modello = Modello(
        argomenti.modello,
        argomenti.revisione or MODELLI[argomenti.modello],
        dtype=dtype,
        riallinea=not argomenti.senza_riallineamento,
    )
    motore = Motore(modello, registro=argomenti.uscita / "registro", max_token_testo=MAX_TOKEN_ANALISI)
    voci, giuste = _contratti_e_risposte(argomenti.benchmark, argomenti.insieme)
    if argomenti.max_token:
        lunghezza = {cid: len(modello.tokenizer.encode(testo, add_special_tokens=False)) for cid, testo in voci}
        for cid, n in lunghezza.items():
            if n > argomenti.max_token:
                print(f"  saltato {cid[:60]}: {n} token, oltre {argomenti.max_token}", flush=True)
        voci = [(cid, testo) for cid, testo in voci if lunghezza[cid] <= argomenti.max_token]
    voci = voci[: argomenti.limite] if argomenti.limite else voci
    argomenti.uscita.mkdir(parents=True, exist_ok=True)
    for passi in argomenti.passi:
        consiglio = Consiglio(
            motore,
            BENCHMARK[argomenti.benchmark],
            modalita=argomenti.modalita,
            passi_latenti=passi,
            traduci=argomenti.traduci,
        )
        nome = f"{argomenti.benchmark}-{argomenti.insieme}-{argomenti.modalita}-m{passi}-{argomenti.modello.split('/')[-1]}"
        if argomenti.senza_riallineamento:
            nome += "-senza-riallineamento"  # i giri normali non si sovrascrivono
        revisioni = []
        with (argomenti.uscita / f"{nome}.jsonl").open("w") as f:
            for contratto, testo in voci:
                revisione = consiglio.revisiona(contratto, testo).come_dict()
                revisioni.append(revisione)
                f.write(json.dumps(revisione, ensure_ascii=False) + "\n")
                f.flush()
                print(f"  {contratto[:60]}: {revisione['secondi']:.0f} s", flush=True)
                libera_memoria()
        print(f"{nome}: {sintesi(revisioni, giuste)}", flush=True)


if __name__ == "__main__":
    main()
