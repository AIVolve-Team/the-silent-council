"""Il PDF di una fattura di prova, in italiano o in inglese, come arriverebbe per email.

Con `testo_nascosto` il PDF porta anche righe in bianco su bianco e in corpo 1: non si vedono, ma l'estrazione del
testo le legge, ed è così che arrivano al motore negli attacchi F4-F7. Lo stesso caso dà sempre gli stessi
byte (`invariant=1`), così l'impronta dell'esame resta quella pre-registrata.
"""

from __future__ import annotations

import io
from datetime import date

from reportlab.lib.pagesizes import A4
from reportlab.lib.utils import simpleSplit
from reportlab.pdfgen import canvas

from .genera import Caso

ETICHETTE = {
    "it": {
        "titolo": "FATTURA", "numero": "Numero", "data": "Data", "cliente": "Spett.le", "id": "P.IVA",
        "ordine": "Rif. ordine", "colonne": ("Codice", "Descrizione", "Q.tà", "Prezzo unit.", "IVA %", "Importo"),
        "aliquota": "Aliquota", "imponibile": "Imponibile", "imposta": "IVA", "totale": "Totale documento",
        "pagamento": "Pagamento: bonifico bancario", "beneficiario": "Beneficiario", "scadenza": "Scadenza",
        "da_pagare": "Importo da pagare", "tel": "Tel.", "email": "Email",
    },
    "en": {
        "titolo": "INVOICE", "numero": "Invoice no.", "data": "Date", "cliente": "Bill to", "id": "VAT no.",
        "ordine": "PO reference", "colonne": ("Code", "Description", "Qty", "Unit price", "VAT %", "Amount"),
        "aliquota": "VAT rate", "imponibile": "Taxable amount", "imposta": "VAT", "totale": "Invoice total",
        "pagamento": "Payment: bank transfer", "beneficiario": "Payee", "scadenza": "Due date",
        "da_pagare": "Amount due", "tel": "Phone", "email": "Email",
    },
}  # fmt: skip
INVERSIONE = "VAT reverse charge - Article 196, Council Directive 2006/112/EC"
MESI_EN = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")
MARGINE = 40
LARGHEZZA, ALTEZZA = A4


def soldi(valore: float, lingua: str) -> str:
    cifre = f"{valore:,.2f}"
    if lingua == "it":
        return cifre.replace(",", "X").replace(".", ",").replace("X", ".") + " €"
    return f"EUR {cifre}"  # in inglese "€49.14" con Helvetica sovrappone il simbolo alla prima cifra


def numero(valore: float, lingua: str) -> str:
    testo = f"{valore:g}"
    return testo.replace(".", ",") if lingua == "it" else testo


def giorno(iso: str | None, lingua: str) -> str:
    if not iso:
        return ""
    d = date.fromisoformat(iso)
    return f"{d:%d/%m/%Y}" if lingua == "it" else f"{d.day} {MESI_EN[d.month - 1]} {d.year}"


def gruppi(iban: str) -> str:
    return " ".join(iban[i : i + 4] for i in range(0, len(iban), 4))


def rendi_pdf(caso: Caso, *, testo_nascosto: str | None = None) -> bytes:
    lingua, e = caso.lingua, ETICHETTE[caso.lingua]
    impegno, fornitore, cliente = caso.impegno, caso.intestazione["fornitore"], caso.intestazione["cliente"]
    documento, pagamento = impegno["documento"], impegno["pagamento"]
    uscita = io.BytesIO()
    c = canvas.Canvas(uscita, pagesize=A4, invariant=1)
    c.setTitle(f"{e['titolo']} {documento['numero']}")
    c.setAuthor(fornitore["denominazione"])
    c.setCreator("sportello/dati")

    # Intestazione: fornitore a sinistra, documento a destra.
    y = ALTEZZA - MARGINE - 10
    c.setFont("Helvetica-Bold", 14)
    c.drawString(MARGINE, y, fornitore["denominazione"])
    c.setFont("Helvetica", 9)
    for riga in (
        fornitore["indirizzo"],
        f"{e['id']} {fornitore['id_fiscale']}",
        f"{e['tel']} {fornitore['telefono']}  ·  {e['email']} {fornitore['email']}",
    ):
        y -= 13
        c.drawString(MARGINE, y, riga)
    c.setFont("Helvetica-Bold", 18)
    c.drawRightString(LARGHEZZA - MARGINE, ALTEZZA - MARGINE - 10, e["titolo"])
    c.setFont("Helvetica", 10)
    c.drawRightString(LARGHEZZA - MARGINE, ALTEZZA - MARGINE - 28, f"{e['numero']}: {documento['numero']}")
    c.drawRightString(LARGHEZZA - MARGINE, ALTEZZA - MARGINE - 42, f"{e['data']}: {giorno(documento['data'], lingua)}")

    # Cliente e ordine.
    y -= 30
    c.setFont("Helvetica-Bold", 10)
    c.drawString(MARGINE, y, f"{e['cliente']}:")
    c.setFont("Helvetica", 10)
    for riga in (
        cliente["denominazione"],
        cliente["indirizzo"],
        f"{ETICHETTE['it']['id'] if lingua == 'it' else e['id']} {cliente['piva']}",
    ):
        y -= 13
        c.drawString(MARGINE + 60, y, riga)
    numero_ordine = (impegno.get("ordine") or {}).get("numero")
    if numero_ordine:
        y -= 20
        c.drawString(MARGINE, y, f"{e['ordine']}: {numero_ordine}")

    # Righe.
    colonne = (
        MARGINE,
        MARGINE + 70,
        LARGHEZZA - MARGINE - 215,
        LARGHEZZA - MARGINE - 160,
        LARGHEZZA - MARGINE - 95,
        LARGHEZZA - MARGINE,
    )
    y -= 28
    c.setFont("Helvetica-Bold", 9)
    for x, titolo in zip(colonne, e["colonne"], strict=True):
        (c.drawString if x < colonne[2] else c.drawRightString)(
            x if x < colonne[2] else x + 45 if x != colonne[-1] else x, y, titolo
        )
    c.line(MARGINE, y - 4, LARGHEZZA - MARGINE, y - 4)
    c.setFont("Helvetica", 9)
    for riga in impegno["righe"]:
        descrizione = simpleSplit(riga["descrizione"], "Helvetica", 9, colonne[2] - colonne[1] - 10)
        y -= 15
        c.drawString(colonne[0], y, riga["codice"] or "")
        for i, pezzo in enumerate(descrizione):
            c.drawString(colonne[1], y - 11 * i, pezzo)
        c.drawRightString(colonne[2] + 45, y, numero(riga["quantita"], lingua))
        c.drawRightString(colonne[3] + 45, y, soldi(riga["prezzo_unitario"], lingua))
        c.drawRightString(colonne[4] + 45, y, numero(riga["aliquota"], lingua))
        c.drawRightString(colonne[5], y, soldi(riga["prezzo_totale"], lingua))
        y -= 11 * (len(descrizione) - 1)
    c.line(MARGINE, y - 6, LARGHEZZA - MARGINE, y - 6)

    # Riepilogo IVA e totale.
    y -= 24
    for voce in impegno["riepilogo"]:
        testo = (
            f"{e['aliquota']} {numero(voce['aliquota'], lingua)}%   {e['imponibile']} {soldi(voce['imponibile'], lingua)}"
            f"   {e['imposta']} {soldi(voce['imposta'], lingua)}"
        )
        c.drawRightString(LARGHEZZA - MARGINE, y, testo)
        y -= 13
    c.setFont("Helvetica-Bold", 11)
    c.drawRightString(LARGHEZZA - MARGINE, y - 4, f"{e['totale']}: {soldi(impegno['totale_documento'], lingua)}")
    if fornitore.get("paese", "IT") != "IT":
        c.setFont("Helvetica-Oblique", 8)
        c.drawString(MARGINE, y - 4, INVERSIONE)

    # Pagamento.
    y -= 40
    c.setFont("Helvetica-Bold", 10)
    c.drawString(MARGINE, y, e["pagamento"])
    c.setFont("Helvetica", 10)
    righe_pagamento = []
    if pagamento.get("iban"):
        righe_pagamento.append(f"IBAN: {gruppi(pagamento['iban'])}")
    if pagamento.get("beneficiario"):
        righe_pagamento.append(f"{e['beneficiario']}: {pagamento['beneficiario']}")
    righe_pagamento.append(f"{e['scadenza']}: {giorno(pagamento.get('scadenza'), lingua)}")
    righe_pagamento.append(f"{e['da_pagare']}: {soldi(pagamento['importo'], lingua)}")
    for riga in righe_pagamento:
        y -= 14
        c.drawString(MARGINE, y, riga)

    if testo_nascosto:
        # Bianco su bianco, corpo 1, fra il pagamento e il fondo pagina: invisibile a chi guarda, non a chi estrae.
        c.setFillColorRGB(1, 1, 1)
        c.setFont("Helvetica", 1)
        for i, riga in enumerate(testo_nascosto.splitlines()):
            c.drawString(MARGINE, y - 30 - 2 * i, riga)
    c.showPage()
    c.save()
    return uscita.getvalue()
