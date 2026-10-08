"""Le risposte di GSM8K: quella giusta, scritta dopo `####`, e quella del modello, nell'ultimo `\\boxed{}`."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path

NUMERO = re.compile(r"-?\d[\d,]*(?:\.\d+)?|-?\.\d+")
RIQUADRO = re.compile(r"\\boxed\{((?:[^{}]|\{[^{}]*\})*)\}")

# Le prime 100 righe di grade_school_math/data/test.jsonl di openai/grade-school-math al commit 3101c7d (MIT).
# Il file intero (1.319 righe) ha impronta 3730d312…9d14; queste 100 righe hanno quella qui sotto.
FILE_PROBLEMI = Path(__file__).resolve().parent.parent / "dati" / "gsm8k-test-100.jsonl"
IMPRONTA_PROBLEMI = "1d266ea030421507ae8e9434bd76a7830553081c0f3d002250c429357b21ff90"


@dataclass(frozen=True)
class Problema:
    id: str
    domanda: str
    risposta: str


def carica_problemi(n: int = 100, *, file: Path = FILE_PROBLEMI) -> list[Problema]:
    """I primi `n` problemi del test di GSM8K, solo se il file è quello pre-registrato."""
    dati = file.read_bytes()
    if hashlib.sha256(dati).hexdigest() != IMPRONTA_PROBLEMI:
        raise ValueError(f"l'impronta di {file} non è quella pre-registrata: il file è stato toccato")
    righe = [json.loads(riga) for riga in dati.decode("utf-8").splitlines()]
    return [
        Problema(f"gsm8k-test-{i:04d}", riga["question"], risposta_giusta(riga["answer"]))
        for i, riga in enumerate(righe[:n])
    ]


def normalizza(numero: str) -> str | None:
    """`1,250.00` → `1250`, `.5` → `0.5`: lo stesso numero ha sempre la stessa scrittura."""
    try:
        valore = Decimal(numero.replace(",", ""))
    except InvalidOperation:
        return None
    if valore == valore.to_integral_value():
        return str(int(valore))
    return format(valore.normalize(), "f")


def ultimo_numero(testo: str) -> str | None:
    numeri = NUMERO.findall(testo)
    return normalizza(numeri[-1]) if numeri else None


def risposta_giusta(soluzione: str) -> str:
    risposta = ultimo_numero(soluzione.split("####")[-1])
    if risposta is None:
        raise ValueError(f"soluzione senza risposta dopo ####: {soluzione[-80:]!r}")
    return risposta


def estrai_risposta(testo: str) -> str | None:
    """L'ultimo numero dell'ultimo riquadro; senza riquadro, o se il riquadro non ha numeri, l'ultimo del testo."""
    riquadri = RIQUADRO.findall(testo)
    if riquadri and (dentro := ultimo_numero(riquadri[-1])) is not None:
        return dentro
    return ultimo_numero(testo)


def corretta(predetta: str | None, giusta: str) -> bool:
    if predetta is None:
        return False
    return Decimal(predetta) == Decimal(normalizza(giusta) or "NaN")
