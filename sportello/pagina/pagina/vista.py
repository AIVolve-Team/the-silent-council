"""I dati della pagina del caso, dal risultato della pipeline e dagli archivi.

Tutto ciò che la pagina mostra come testo passa da qui, e qui l'IBAN si abbrevia sempre (prime e ultime quattro cifre,
«Caso passato a una persona»): l'unico posto dove compare intero è il PDF originale, che è la prova di ciò che è arrivato.
"""

from __future__ import annotations

import base64
import re

from controllore.coerenza import CAMPI_CRITICI, uguali, valore
from fatture.archivi import Archivi
from fatture.normalizza import id_fiscale

from .nascosto import righe_nascoste

GRAVITA = {"pagare": 0, "persona": 1, "bloccare": 2}
MOTIVO_PREDEFINITO = {
    "pagare": ("Fattura conforme: pagamento proposto, in attesa di approvazione.",
               "Invoice matches: payment proposed, awaiting approval."),
    "persona": ("Serve una persona per decidere.", "A person needs to decide."),
    "bloccare": ("Pagamento bloccato.", "Payment blocked."),
}  # fmt: skip
CODICI_FRODE = {"pagamento.iban", "A03", "A04"}
IBAN_NEL_TESTO = re.compile(r"\b[A-Z]{2}[0-9]{2}(?:\s?[A-Z0-9]){10,30}\b")


def abbrevia(iban: str | None) -> str | None:
    if not iban:
        return None
    compatto = str(iban).replace(" ", "").upper()
    return f"{compatto[:4]}…{compatto[-4:]}"


def maschera(testo: str) -> str:
    """Gli IBAN dentro un testo, abbreviati: anche il testo nascosto mostrato alla persona non si copia."""
    return IBAN_NEL_TESTO.sub(lambda m: abbrevia(m.group(0)), testo)


def mostra(campo, dato):
    return abbrevia(dato) if campo.tipo == "iban" else dato


def motivo_principale(risultato: dict) -> dict:
    """Il primo motivo con l'esito finale: per un blocco, il controllo che ha bloccato."""
    esito = risultato["esito"]
    for m in risultato.get("motivi") or []:
        if m.get("esito") == esito:
            return {"it": m["motivo"], "en": m.get("motivo_en") or m["motivo"]}
    it, en = MOTIVO_PREDEFINITO.get(esito, ("", ""))
    return {"it": it, "en": en}


def testimoni(impegno: dict | None, lettura: dict | None, proposta: dict | None) -> list[dict]:
    proposta_annidata = (
        None if proposta is None else {"pagamento": {"iban": proposta.get("iban"), "importo": proposta.get("importo")}}
    )
    righe = []
    for campo in CAMPI_CRITICI:
        a, b = valore(impegno, campo.percorso), valore(lettura, campo.percorso)
        p = valore(proposta_annidata, campo.percorso) if campo.nome in ("pagamento.iban", "pagamento.importo") else None
        valori = [x for x in (a, b, p) if x is not None]
        diverso = any(not uguali(campo.tipo, valori[0], x) for x in valori[1:]) or (a is None) != (b is None)
        righe.append({
            "campo": campo.nome, "it": campo.it, "en": campo.en, "impegno": mostra(campo, a), "lettura": mostra(campo, b),
            "proposta": mostra(campo, p), "diverso": diverso,
        })  # fmt: skip
    return righe


def vista_caso(risultato: dict, archivi: Archivi, *, pdf: bytes) -> dict:
    impegno = risultato.get("impegno") or {}
    motivi = risultato.get("motivi") or []
    fornitore = archivi.anagrafica.get(id_fiscale((impegno.get("fornitore") or {}).get("id_fiscale") or ""))
    numero_ordine = (impegno.get("ordine") or {}).get("numero")
    ordine = archivi.ordini.get(numero_ordine) if numero_ordine else None
    documento = impegno.get("documento") or {}
    proposto = risultato.get("pagamento_proposto")
    return {
        "id": risultato["id_caso"],
        "esito": risultato["esito"],
        "motivo": motivo_principale(risultato),
        "fattura": {
            "fornitore": (impegno.get("fornitore") or {}).get("denominazione"),
            "id_fiscale": (impegno.get("fornitore") or {}).get("id_fiscale"),
            "numero": documento.get("numero"),
            "data": documento.get("data"),
            "totale": impegno.get("totale_documento"),
            "scadenza": (impegno.get("pagamento") or {}).get("scadenza"),
        },
        "sigillo": {"integro": risultato.get("sigillo") == "integro", "dettaglio": risultato.get("sigillo")},
        "testimoni": testimoni(risultato.get("impegno"), risultato.get("lettura"), risultato.get("proposta")),
        "regole": [m for m in motivi if m.get("livello") == "regole"],
        "altri_motivi": [m for m in motivi if m.get("livello") != "regole"],
        "ordine": None
        if ordine is None
        else {
            "numero": ordine.numero,
            "data": ordine.data,
            "righe": [
                {
                    "n": r.n,
                    "descrizione": r.descrizione,
                    "quantita": r.quantita,
                    "prezzo_unitario": r.prezzo_unitario,
                    "aliquota": r.aliquota,
                }
                for r in ordine.righe
            ],
        },
        "righe": impegno.get("righe") or [],
        "nascosto": [maschera(riga) for riga in righe_nascoste(pdf)],
        "contatti": None
        if fornitore is None
        else {
            "denominazione": fornitore.denominazione,
            "telefono": fornitore.telefono,
            "email": fornitore.email,
            "iban_registrato": abbrevia(fornitore.iban),
        },
        "frode_sospetta": risultato["esito"] != "pagare" and any(m.get("codice") in CODICI_FRODE for m in motivi),
        "proposta": None
        if not proposto
        else {
            "importo": proposto.get("importo"),
            "iban_registrato": None if fornitore is None else abbrevia(fornitore.iban),
        },
        # Un caso bloccato si approva solo con una nota di verifica fatta con i contatti in anagrafica.
        "nota_obbligatoria": risultato["esito"] == "bloccare",
        "email": risultato.get("email"),
        "pdf": base64.b64encode(pdf).decode("ascii"),
    }
