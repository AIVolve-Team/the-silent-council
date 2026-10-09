"""Gli schemi JSON di ciò che scrivono i tre agenti, con la decodifica vincolata del motore.

I formati di "L'impegno" stanno negli schemi: date ISO, IBAN senza spazi e in maiuscolo, identificativo fiscale
con il prefisso del paese, importi come numeri, `null` per ciò che non c'è. Così il modello non può scriverli in un
altro modo, e una discordanza è una discordanza vera.
"""

from __future__ import annotations

# Mesi da 01 a 12 e giorni da 01 a 31: il 2026-15-09 scritto da un modello piccolo fermava le regole.
DATA = {
    "anyOf": [{"type": "string", "pattern": "^20[0-9]{2}-(0[1-9]|1[0-2])-(0[1-9]|[12][0-9]|3[01])$"}, {"type": "null"}]
}
IBAN = {"anyOf": [{"type": "string", "pattern": "^[A-Z]{2}[0-9]{2}[A-Z0-9]{10,30}$"}, {"type": "null"}]}
ID_FISCALE = {"anyOf": [{"type": "string", "pattern": "^[A-Z]{2}[A-Z0-9]{2,13}$"}, {"type": "null"}]}
IMPORTO = {"anyOf": [{"type": "number"}, {"type": "null"}]}


def testo(n: int) -> dict:
    return {"anyOf": [{"type": "string", "maxLength": n}, {"type": "null"}]}


def oggetto(proprieta: dict) -> dict:
    return {"type": "object", "properties": proprieta, "required": list(proprieta), "additionalProperties": False}


RIGA = oggetto({
    "n": {"type": "integer"},
    "num_item": {"anyOf": [{"type": "string", "pattern": "^[0-9]{1,3}$"}, {"type": "null"}]},  # solo il numero
    "codice": testo(20),
    "descrizione": {"type": "string", "maxLength": 120},
    "quantita": {"type": "number"},
    "prezzo_unitario": {"type": "number"},
    "prezzo_totale": {"type": "number"},
    "aliquota": {"type": "number"},
})  # fmt: skip

SCHEMA_IMPEGNO = oggetto({
    "fornitore": oggetto({"id_fiscale": ID_FISCALE, "denominazione": testo(120)}),
    "cliente_piva": ID_FISCALE,
    "documento": oggetto({"tipo": {"enum": ["TD01"]}, "numero": testo(30), "data": DATA, "divisa": {"enum": ["EUR"]}}),
    "ordine": oggetto({"numero": testo(30)}),
    "righe": {"type": "array", "minItems": 1, "maxItems": 20, "items": RIGA},
    "riepilogo": {
        "type": "array", "minItems": 1, "maxItems": 4,
        "items": oggetto({"aliquota": {"type": "number"}, "imponibile": {"type": "number"}, "imposta": {"type": "number"}}),
    },
    "totale_documento": {"type": "number"},
    "pagamento": oggetto({
        "modalita": {"enum": ["MP05"]}, "iban": IBAN, "beneficiario": testo(120), "scadenza": DATA, "importo": IMPORTO,
    }),
})  # fmt: skip

# La lettura del verificatore: gli 8 dati critici, nella stessa forma dell'impegno.
SCHEMA_LETTURA = oggetto({
    "fornitore": oggetto({"id_fiscale": ID_FISCALE}),
    "documento": oggetto({"numero": testo(30), "data": DATA}),
    "totale_documento": IMPORTO,
    "pagamento": oggetto({"iban": IBAN, "importo": IMPORTO, "scadenza": DATA}),
    "ordine": oggetto({"numero": testo(30)}),
})  # fmt: skip


def lettura_da(impegno: dict) -> dict:
    """Gli 8 dati critici di un impegno, nella forma della lettura: è la lettura di un verificatore perfetto."""
    return {
        "fornitore": {"id_fiscale": impegno["fornitore"]["id_fiscale"]},
        "documento": {"numero": impegno["documento"]["numero"], "data": impegno["documento"]["data"]},
        "totale_documento": impegno["totale_documento"],
        "pagamento": {k: impegno["pagamento"][k] for k in ("iban", "importo", "scadenza")},
        "ordine": {"numero": impegno["ordine"]["numero"]},
    }


def schema_proposta() -> dict:
    """La proposta del decisore: IBAN e importo, esito proposto e motivazione. Il decisore non può bloccare: un
    blocco nasce sempre da una regola."""
    return oggetto({
        "iban": IBAN,
        "importo": IMPORTO,
        "esito": {"enum": ["pagare", "persona"]},
        "motivazione": {"type": "string", "maxLength": 240},
    })  # fmt: skip


def schema_abbinamenti(righe_libere: list[int]) -> dict:
    """L'abbinatore cieco (F7 di «Catalogo degli attacchi»): per ogni riga senza riferimento, la riga dell'ordine o null (A11)."""
    return oggetto({
        "abbinamenti": {
            "type": "array",
            "minItems": len(righe_libere),
            "maxItems": len(righe_libere),
            "items": oggetto(
                {"riga": {"enum": righe_libere}, "riga_ordine": {"anyOf": [{"type": "integer"}, {"type": "null"}]}}
            ),
        }
    })  # fmt: skip
