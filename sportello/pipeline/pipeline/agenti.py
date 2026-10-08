"""I tre agenti dello Sportello e i loro prompt.

I prompt sono in inglese, come le istruzioni che Qwen3 segue meglio; le fatture arrivano in italiano o in inglese
 e i valori si copiano come sono stampati. I nomi dei ruoli sono nostri: `planner`, `critic`, `refiner` e
`judger` sono vietati.
"""

from __future__ import annotations

from fatture.archivi import Ordine
from motore import Agente

ESTRATTORE = Agente(
    "estrattore",
    "You are the extractor of an accounts-payable desk. You read supplier invoices that arrive by email, in Italian "
    "or English, and you report exactly what is printed on them. Another agent will check your work.",
)
VERIFICATORE = Agente(
    "verificatore",
    "You are the verifier of an accounts-payable desk. You never see the invoice: you only have what the extractor "
    "passed to you, and you report only what you find there.",
)
DECISORE = Agente(
    "decisore",
    "You are the decision maker of an accounts-payable desk. You never see the invoice: you only have what your "
    "colleagues passed to you. You propose payments; a person approves them.",
)

LEGGI = (
    "Read this supplier invoice carefully: supplier and VAT number, invoice number and date, purchase order "
    "reference, every line, the VAT summary, the total and the payment details (IBAN, payee, due date, amount).\n\n"
    "Invoice:\n{fattura}"
)
SCRIVI_IMPEGNO = (
    "Write the data of the invoice as JSON. Copy every value exactly as printed. Dates as YYYY-MM-DD. Amounts as "
    "plain numbers. IBAN without spaces. Supplier and customer VAT numbers with the country prefix. Use null for "
    "anything that is not printed on the invoice. Never invent a value."
)
RICORDA = (
    "Recall the invoice the extractor read: the supplier, the invoice number and date, the total, the payment "
    "details and the purchase order."
)
SCRIVI_LETTURA = (
    "Write the critical payment data as JSON, using only what you received from the extractor: supplier VAT number "
    "with the country prefix, invoice number, invoice date (YYYY-MM-DD), invoice total, IBAN without spaces, amount "
    "due, due date (YYYY-MM-DD) and purchase order number. Use null for anything you cannot find."
)
DECIDI = (
    'Propose the payment for this invoice: the IBAN and the amount to pay, your proposed outcome ("pagare" to '
    'propose the payment, "persona" if something needs a person to check it) and a one-sentence reason.'
)


def prompt_decisore(ordine: Ordine | None, righe_libere: list[dict]) -> str:
    """Il decisore abbina all'ordine le righe senza riferimento (A11): l'ordine è un nostro archivio."""
    parti = [DECIDI]
    if ordine is not None:
        voci = "\n".join(
            f"{r.n}. {r.descrizione} — quantity {r.quantita:g}, unit price {r.prezzo_unitario:.2f}"
            for r in ordine.righe
        )
        parti.append(f"Our purchase order {ordine.numero} has these lines:\n{voci}")
        if righe_libere:
            libere = "\n".join(f"- invoice line {r['n']}: {r['descrizione']}" for r in righe_libere)
            parti.append(
                "These invoice lines have no order reference. For each one, give the number of the order line it "
                f"corresponds to, or null if it matches none:\n{libere}"
            )
    return "\n\n".join(parti)
