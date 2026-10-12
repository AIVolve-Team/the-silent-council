"""Accesso ai dati di `consiglio/dati`: categorie, contratti del campione, risposte giuste, set dimostrativo."""

from __future__ import annotations

import importlib.util
import json
import os
import sys
from functools import cache
from pathlib import Path
from types import ModuleType

DATI = Path(__file__).resolve().parents[2] / "dati"


def _modulo(nome: str) -> ModuleType:
    """Carica uno script di `consiglio/dati` come modulo, senza copiarne il codice."""
    if str(DATI) not in sys.path:
        sys.path.insert(0, str(DATI))
    spec = importlib.util.spec_from_file_location(f"dati_{nome}", DATI / f"{nome}.py")
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


@cache
def categorie_dati() -> ModuleType:
    return _modulo("categorie")


@cache
def _testi(benchmark: str) -> dict[str, str]:
    prepara = _modulo("prepara")
    lettori = {
        "cuad": lambda: prepara.leggi_cuad(DATI / "cache" / "cuad.zip"),
        "contractnli": lambda: prepara.leggi_contractnli(DATI / "cache" / "contractnli.zip"),
        "claudette": lambda: prepara.leggi_claudette(DATI / "cache" / "claudette.tar.gz"),
    }
    return {c["id"]: c["testo"] for insieme in lettori[benchmark]().values() for c in insieme}


def contratti(benchmark: str, insieme: str) -> list[tuple[str, str]]:
    """(id, testo) dei contratti del campione, nell'ordine di `campione.json`. Servono i file in `dati/cache`,
    che `prepara.py` scarica."""
    campione = json.loads((DATI / "set-di-misura" / "campione.json").read_text())
    testi = _testi(benchmark)
    return [(cid, testi[cid]) for cid in campione[benchmark][insieme]]


def _righe(benchmark: str, insieme: str):
    for r in (DATI / "set-di-misura" / "risposte-giuste.jsonl").open():
        riga = json.loads(r)
        if riga["benchmark"] == benchmark and riga["insieme"] == insieme:
            yield riga


def risposte_giuste(benchmark: str, insieme: str) -> dict[tuple[str, str], bool]:
    """(contratto, categoria) → da segnalare."""
    return {(r["contratto"], r["categoria"]): r["da_segnalare"] for r in _righe(benchmark, insieme)}


def prove(benchmark: str, insieme: str) -> dict[tuple[str, str], list[str]]:
    """(contratto, categoria) → i pezzi di testo annotati, per la versione severa del voto. Per il set
    dimostrativo sono le citazioni delle risposte attese."""
    if benchmark == "dimostrativo":
        return {
            (cid, r["categoria"]): [r["citazione"]] if r.get("citazione") else []
            for cid, _, attesa in dimostrativo()
            for r in attesa["righe"]
        }
    return {(r["contratto"], r["categoria"]): r["prove"] for r in _righe(benchmark, insieme)}


def risposte_grado_3(insieme: str) -> dict[tuple[str, str], bool]:
    """CLAUDETTE con il solo grado 3 (chiaramente abusiva): la vista a parte chiesta in «Contratti di prova e risposte giuste»."""
    return {(r["contratto"], r["categoria"]): r["da_segnalare_grado_3"] for r in _righe("claudette", insieme)}


def cartella_dimostrativo() -> Path:
    """Il set dimostrativo resta fuori dal repo: di default `dati/set-dimostrativo`, oppure
    `CONSIGLIO_SET_DIMOSTRATIVO`."""
    return Path(os.environ.get("CONSIGLIO_SET_DIMOSTRATIVO", DATI / "set-dimostrativo"))


def dimostrativo() -> list[tuple[str, str, dict]]:
    """(id, testo, risposta attesa) dei contratti del set dimostrativo."""
    cartella = cartella_dimostrativo()
    return [
        (f.stem, f.read_text(), json.loads(f.with_suffix(".json").read_text())) for f in sorted(cartella.glob("*.txt"))
    ]
