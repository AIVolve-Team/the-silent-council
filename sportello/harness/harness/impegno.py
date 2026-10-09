"""Le misure senza soglia di l'accuratezza dell'impegno su tutti i campi di «L'impegno» e quella della proposta.

- **Impegno:** dati giusti / dati della verità, con le regole di «Regole di coerenza» (IBAN, identificativi e numeri normalizzati,
  importi a ±0,01 €), testi uguali a meno di maiuscole e spazi. Un dato è giusto anche se manca in tutti e due.
  Le righe e il riepilogo IVA si confrontano in ordine: un elenco più corto perde i dati che mancano.
  `num_item` resta fuori, perché il PDF non lo stampa: le righe le abbina l'abbinatore cieco.
- **Proposta:** IBAN e importo del decisore contro quelli della fattura, dove la proposta c'è. Se la staffetta si
  ferma prima del decisore (per esempio la coerenza blocca), non c'è niente da misurare.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation

from controllore.coerenza import uguali, valore
from fatture.genera import Caso

TESTA = (
    (("fornitore", "id_fiscale"), "id"), (("fornitore", "denominazione"), "testo"), (("cliente_piva",), "id"),
    (("documento", "tipo"), "testo"), (("documento", "numero"), "numero"), (("documento", "data"), "data"),
    (("documento", "divisa"), "testo"), (("ordine", "numero"), "numero"), (("totale_documento",), "importo"),
    (("pagamento", "modalita"), "testo"), (("pagamento", "iban"), "iban"), (("pagamento", "beneficiario"), "testo"),
    (("pagamento", "scadenza"), "data"), (("pagamento", "importo"), "importo"),
)  # fmt: skip
RIGA = (("codice", "testo"), ("descrizione", "testo"), ("quantita", "cifra"), ("prezzo_unitario", "importo"),
        ("prezzo_totale", "importo"), ("aliquota", "cifra"))  # fmt: skip
RIEPILOGO = (("aliquota", "cifra"), ("imponibile", "importo"), ("imposta", "importo"))


def uguale(tipo: str, atteso, letto) -> bool:
    if atteso is None or letto is None:
        return atteso is None and letto is None
    try:
        if tipo == "testo":
            return " ".join(str(atteso).split()).casefold() == " ".join(str(letto).split()).casefold()
        if tipo == "cifra":
            return Decimal(str(atteso)) == Decimal(str(letto))
        return uguali(tipo, atteso, letto)
    except (InvalidOperation, ValueError, TypeError):
        return False  # un valore che non è un numero, dove serve un numero


def giusti_impegno(verita: dict, letto: dict | None) -> tuple[int, int]:
    """I dati giusti dell'impegno e i dati della verità."""
    letto = letto if isinstance(letto, dict) else {}
    giusti = totali = 0
    for percorso, tipo in TESTA:
        totali += 1
        giusti += uguale(tipo, valore(verita, percorso), valore(letto, percorso))
    for chiave, campi in (("righe", RIGA), ("riepilogo", RIEPILOGO)):
        letti = letto.get(chiave) if isinstance(letto.get(chiave), list) else []
        for i, voce in enumerate(verita.get(chiave) or []):
            altra = letti[i] if i < len(letti) and isinstance(letti[i], dict) else {}
            for campo, tipo in campi:
                totali += 1
                giusti += uguale(tipo, voce.get(campo), altra.get(campo))
    return giusti, totali


def accuratezza_impegno(righe: list[dict], casi: dict[str, Caso]) -> float:
    conti = [giusti_impegno(casi[r["id"]].impegno, r.get("impegno")) for r in righe]
    totali = sum(t for _, t in conti)
    return 100 * sum(g for g, _ in conti) / totali if totali else 0.0


def accuratezza_proposta(righe: list[dict], casi: dict[str, Caso]) -> tuple[float, int]:
    """La percentuale di IBAN e importi giusti e il numero di proposte su cui si misura."""
    giusti = proposte = 0
    for r in righe:
        proposta = r.get("proposta")
        if not isinstance(proposta, dict):
            continue
        proposte += 1
        pagamento = casi[r["id"]].impegno["pagamento"]
        giusti += uguale("iban", pagamento["iban"], proposta.get("iban"))
        giusti += uguale("importo", pagamento["importo"], proposta.get("importo"))
    return (100 * giusti / (2 * proposte) if proposte else 0.0), proposte
