"""Un giro della pipeline su un insieme del generatore: una riga per fattura in `<uscita>/<modalità>.jsonl`.

    python -m pipeline.giro ../dati/insiemi/sviluppo --modalita telepatia --passi 10 --limite 10 --uscita risultati/

Ogni fattura finita si scrive subito: rilanciando lo stesso comando si riparte dalla prima che manca. Il registro di
ogni caso (messaggi firmati, esito, chiavi pubbliche) va in `<uscita>/registro/<modalità>/`.
"""

from __future__ import annotations

import argparse
import json
import traceback
from pathlib import Path

import torch
from fatture.insiemi import carica_archivi, carica_casi
from motore import Modello
from motore.messaggio import TELEPATIA, TESTO

from .sportello import Chiavi, chiavi_di_prova, esamina

# Le stesse revisioni del Consiglio (consiglio/revisione/revisione/esegui.py): stessi pesi per i due progetti.
MODELLI = {
    "Qwen/Qwen3-0.6B": "c1899de289a04d12100db370d81485cdf75e47ca",
    "Qwen/Qwen3-1.7B": "70d244cc86ccca08cf5af4e1e306ecf908b1ad5e",
    "Qwen/Qwen3-4B": "1cfa9a7208912126459214e8b04321603b3df60c",
    "Qwen/Qwen3-8B": "b968826d9c46dd6066d109eabc6255188de91218",
    "Qwen/Qwen3-14B": "40c069824f4251a91eefaf281ebe4c544efd3e18",
}
DTYPE = {"bfloat16": torch.bfloat16, "float16": torch.float16, "float32": torch.float32}


def esegui_giro(
    modello: Modello,
    cartella: Path,
    modalita: str,
    uscita: Path,
    chiavi: Chiavi,
    *,
    passi_latenti: int = 10,
    limite: int | None = None,
    livello2: bool = True,
    max_token_testo: int = 1024,
) -> list[dict]:
    casi = carica_casi(cartella)[:limite]
    archivi = carica_archivi(cartella)
    file = uscita / f"{modalita}.jsonl"
    fatte = {r["id"]: r for r in map(json.loads, file.read_text().splitlines())} if file.exists() else {}
    uscita.mkdir(parents=True, exist_ok=True)
    with file.open("a") as f:
        for caso in casi:
            if caso.id in fatte:
                continue
            pdf = (cartella / "fatture" / f"{caso.id}.pdf").read_bytes()
            try:
                r = esamina(
                    modello, pdf, caso.email, archivi, chiavi, modalita=modalita, passi_latenti=passi_latenti,
                    livello2=livello2, max_token_testo=max_token_testo, registro=uscita / "registro" / modalita,
                    id_caso=caso.id,
                )  # fmt: skip
            except Exception as errore:  # noqa: BLE001 - un errore su una fattura non deve fermare un giro di ore
                r = {
                    "id_caso": caso.id,
                    "esito": "errore",
                    "errore": f"{type(errore).__name__}: {errore}",
                    "traccia": traceback.format_exc(limit=8),
                    "token": {"generati": 0, "letti": 0},
                    "secondi": 0.0,
                }
            riga = {"id": caso.id, "modalita": modalita, "passi_latenti": passi_latenti, "esito_atteso": caso.esito_atteso,
                    "anomalia": caso.anomalia, "al_limite": caso.al_limite, **r}  # fmt: skip
            f.write(json.dumps(riga, ensure_ascii=False, default=str) + "\n")
            f.flush()
            fatte[caso.id] = riga
            segno = "✓" if riga["esito"] == caso.esito_atteso else "✗"
            giro = f"{modalita}, {passi_latenti} passi" if modalita == TELEPATIA else modalita
            print(f"{giro} {caso.id}: {riga['esito']} (atteso {caso.esito_atteso}) {segno} "
                  f"{riga['token']['generati']} token, {riga['secondi']} s", flush=True)  # fmt: skip
    return [fatte[c.id] for c in casi]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("insieme", type=Path, help="cartella di un insieme salvato da `python -m fatture.insiemi`")
    parser.add_argument("--modalita", choices=[TELEPATIA, TESTO], default=TELEPATIA)
    parser.add_argument("--passi", type=int, default=10, help="passi latenti (in telepatia)")
    parser.add_argument("--limite", type=int, default=None, help="solo le prime N fatture")
    parser.add_argument("--modello", default="Qwen/Qwen3-14B", choices=list(MODELLI))
    parser.add_argument("--dtype", choices=list(DTYPE), default=None, help="predefinito: bf16 su GPU, fp32 altrove")
    parser.add_argument("--uscita", type=Path, default=Path("risultati"))
    parser.add_argument(
        "--chiavi",
        type=Path,
        default=Path.home() / ".sportello" / "chiavi-prova",
        help="le private restano qui, fuori dal repo e dai risultati; nel registro vanno solo le pubbliche",
    )
    parser.add_argument("--max-token-testo", type=int, default=1024, help="per agente, nel modo a testo")
    argomenti = parser.parse_args()
    dtype = DTYPE.get(argomenti.dtype) if argomenti.dtype else None
    modello = Modello(argomenti.modello, MODELLI[argomenti.modello], dtype=dtype)
    chiavi = chiavi_di_prova(argomenti.chiavi)
    esegui_giro(
        modello, argomenti.insieme, argomenti.modalita, argomenti.uscita, chiavi, passi_latenti=argomenti.passi,
        limite=argomenti.limite, max_token_testo=argomenti.max_token_testo,
    )  # fmt: skip


if __name__ == "__main__":
    main()
