"""Gli schemi JSON di nota e verdetto, per la decodifica vincolata.

Nota e verdetto hanno lo stesso schema per le categorie: `segnalare`, con true o false per ognuna. Il booleano è un
token solo, quindi la sua probabilità dà la confidenza. Citazioni e motivazioni stanno in elenchi con un numero
massimo di voci e di caratteri: così nota e verdetto stanno sempre nel loro limite di token e il JSON si chiude.
L'ordine dei campi è imposto: nel verdetto prima le obiezioni, poi le righe, alla fine la raccomandazione.
"""

from __future__ import annotations

from .categorie import Categoria

RACCOMANDAZIONI = ["firmare", "negoziare", "non firmare"]
MAX_CITAZIONI_NOTA = 3
MAX_DETTAGLI_VERDETTO = 8


def _segnalare(chiavi: list[str]) -> dict:
    return {
        "type": "object",
        "properties": {k: {"type": "boolean"} for k in chiavi},
        "required": list(chiavi),
        "additionalProperties": False,
    }


def _elenco(chiavi: list[str], campi: dict[str, int], massimo: int) -> dict:
    """Un elenco di oggetti {categoria, campi...}, con `massimo` voci e campi di testo con un massimo di caratteri."""
    proprieta = {"categoria": {"enum": chiavi}} | {c: {"type": "string", "maxLength": n} for c, n in campi.items()}
    return {
        "type": "array",
        "maxItems": massimo,
        "items": {
            "type": "object",
            "properties": proprieta,
            "required": list(proprieta),
            "additionalProperties": False,
        },
    }


def schema_nota(categorie: tuple[Categoria, ...]) -> dict:
    chiavi = [c.chiave for c in categorie]
    return {
        "type": "object",
        "properties": {
            "segnalare": _segnalare(chiavi),
            "citazioni": _elenco(chiavi, {"testo": 120}, MAX_CITAZIONI_NOTA),
            "importi_date_parti": {"type": "array", "maxItems": 4, "items": {"type": "string", "maxLength": 40}},
        },
        "required": ["segnalare", "citazioni", "importi_date_parti"],
        "additionalProperties": False,
    }


def schema_verdetto(categorie: tuple[Categoria, ...], *, obiezioni: bool = True) -> dict:
    """Senza `obiezioni` è il verdetto di chi lavora da solo (agente solo e voto fra 4 dell'eval): non ha
    colleghi a cui obiettare."""
    chiavi = [c.chiave for c in categorie]
    proprieta = {
        "obiezioni": _elenco(chiavi, {"obiezione": 150}, 3),
        "segnalare": _segnalare(chiavi),
        "dettagli": _elenco(chiavi, {"citazione": 120, "motivazione": 100}, MAX_DETTAGLI_VERDETTO),
        "raccomandazione": {"enum": RACCOMANDAZIONI},
        "motivazione": {"type": "string", "maxLength": 250},
    }
    if not obiezioni:
        del proprieta["obiezioni"]
    return {
        "type": "object",
        "properties": proprieta,
        "required": list(proprieta),
        "additionalProperties": False,
    }


def token_massimi(schema: dict) -> int:
    """Quanti token servono, al massimo, per scrivere un JSON valido per lo schema.

    Si conta un token per carattere: è il caso peggiore, quello di un modello che si incastra in una ripetizione
    di token corti. Con questo limite nota e verdetto si chiudono sempre.
    """
    if "enum" in schema:
        return max(len(str(v)) for v in schema["enum"]) + 2
    tipo = schema.get("type")
    if tipo == "boolean":
        return 5
    if tipo == "string":
        return schema["maxLength"] + 2
    if tipo == "array":
        return schema["maxItems"] * (token_massimi(schema["items"]) + 1) + 2
    if tipo == "object":
        return 2 + sum(len(k) + 4 + token_massimi(v) for k, v in schema["properties"].items())
    raise ValueError(f"schema senza limite: {schema}")
