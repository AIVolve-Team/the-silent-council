"""Le regole del catalogo: A01-A13 sui campi dell'impegno e sugli archivi, in modo deterministico.

A11 (riga che non corrisponde a nessuna riga dell'ordine) la giudica il modello: le righe senza `num_item` si
abbinano all'ordine con `abbinamenti` ({numero della riga: riga dell'ordine, oppure None}). Senza il giudizio la
regola risponde "da_giudicare". Un blocco nasce sempre da una regola, mai dal giudizio del modello.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from .archivi import Archivi, Ordine, RigaOrdine
from .normalizza import iban, id_fiscale, importo, numero_documento, stesso_importo

GRAVITA = {"pagare": 0, "persona": 1, "da_giudicare": 2, "bloccare": 3}
PAGA_FINO_A = Decimal("0.02")  # prezzo di riga sopra l'ordine: fino al 2% si paga
PERSONA_FINO_A = Decimal("0.10")  # dal 2% al 10% passa a una persona, oltre si blocca
GIORNI_DUPLICATO = 30


@dataclass(frozen=True)
class Scatto:
    codice: str
    esito: str
    motivo: str
    motivo_en: str


def nome(valore: str) -> str:
    return re.sub(r"[^0-9a-z]", "", valore.casefold())


def esito_finale(scatti: list[Scatto]) -> str:
    """Il più grave: bloccare, poi le righe ancora da giudicare, poi persona, poi pagare."""
    return max((s.esito for s in scatti), key=GRAVITA.__getitem__, default="pagare")


def applica_regole(impegno: dict, archivi: Archivi, abbinamenti: dict[int, int | None] | None = None) -> list[Scatto]:
    scatti: list[Scatto] = []
    id_fornitore = id_fiscale(impegno["fornitore"]["id_fiscale"])
    fornitore = archivi.anagrafica.get(id_fornitore)
    scatti += totali(impegno)
    if fornitore is None:
        # Fornitore sconosciuto: non c'è niente con cui confrontare ordine, IBAN o storico.
        return [
            Scatto(
                "A05",
                "bloccare",
                f"Fornitore {id_fornitore} non in anagrafica",
                f"Supplier {id_fornitore} is not in the supplier master data",
            ),
            *scatti,
        ]
    if not fornitore.attivo:
        scatti.append(
            Scatto(
                "A06",
                "bloccare",
                f"Fornitore {id_fornitore} disattivato in anagrafica",
                f"Supplier {id_fornitore} is deactivated in the supplier master data",
            )
        )
    scatti += duplicati(impegno, archivi, id_fornitore)
    pagamento = impegno["pagamento"]
    if pagamento.get("iban") and iban(pagamento["iban"]) != iban(fornitore.iban):
        scatti.append(
            Scatto(
                "A03",
                "bloccare",
                f"IBAN della fattura {iban(pagamento['iban'])} diverso da quello registrato {iban(fornitore.iban)}",
                f"Invoice IBAN {iban(pagamento['iban'])} differs from the registered {iban(fornitore.iban)}",
            )
        )
    if pagamento.get("beneficiario") and nome(pagamento["beneficiario"]) != nome(fornitore.denominazione):
        scatti.append(
            Scatto(
                "A04",
                "persona",
                f"Beneficiario «{pagamento['beneficiario']}» diverso dal fornitore «{fornitore.denominazione}»",
                f"Payee “{pagamento['beneficiario']}” differs from the supplier “{fornitore.denominazione}”",
            )
        )
    numero_ordine = (impegno.get("ordine") or {}).get("numero")
    if not numero_ordine:
        scatti.append(Scatto("A07", "persona", "Nessun riferimento all'ordine", "No purchase order reference"))
        return scatti
    ordine = archivi.ordini.get(numero_ordine)
    if ordine is None or id_fiscale(ordine.fornitore) != id_fornitore:
        motivo = "inesistente" if ordine is None else f"intestato a un altro fornitore ({ordine.fornitore})"
        motivo_en = "does not exist" if ordine is None else f"belongs to another supplier ({ordine.fornitore})"
        scatti.append(
            Scatto("A08", "bloccare", f"Ordine {numero_ordine} {motivo}", f"Purchase order {numero_ordine} {motivo_en}")
        )
        return scatti
    for riga in impegno["righe"]:
        scatti += controlla_riga(riga, ordine, abbinamenti)
    return scatti


def totali(impegno: dict) -> list[Scatto]:
    atteso = sum((importo(r["imponibile"]) + importo(r["imposta"]) for r in impegno["riepilogo"]), Decimal(0))
    if stesso_importo(atteso, impegno["totale_documento"]):
        return []
    totale = importo(impegno["totale_documento"])
    return [
        Scatto(
            "A13",
            "bloccare",
            f"Totale {totale} diverso da imponibile più IVA ({atteso})",
            f"Total {totale} differs from taxable amount plus VAT ({atteso})",
        )
    ]


def duplicati(impegno: dict, archivi: Archivi, id_fornitore: str) -> list[Scatto]:
    documento = impegno["documento"]
    numero, giorno = numero_documento(documento["numero"]), date.fromisoformat(documento["data"])
    numero_ordine = (impegno.get("ordine") or {}).get("numero")
    ordine = archivi.ordini.get(numero_ordine) if numero_ordine else None
    scatti = []
    for voce in archivi.storico:
        if id_fiscale(voce.fornitore) != id_fornitore:
            continue
        giorno_voce = date.fromisoformat(voce.data)
        if numero_documento(voce.numero) == numero and giorno_voce.year == giorno.year:
            scatti.append(
                Scatto(
                    "A01",
                    "bloccare",
                    f"Duplicato esatto della fattura {voce.numero} del {voce.data}",
                    f"Exact duplicate of invoice {voce.numero} dated {voce.data}",
                )
            )
        elif (
            numero_ordine
            and voce.ordine == numero_ordine
            and stesso_importo(voce.importo, impegno["totale_documento"])
            and abs((giorno - giorno_voce).days) <= GIORNI_DUPLICATO
            and (ordine is None or ordine.rate <= 1)
        ):
            scatti.append(
                Scatto(
                    "A02",
                    "persona",
                    f"Possibile duplicato della fattura {voce.numero} del {voce.data}: stesso ordine e stesso importo",
                    f"Possible duplicate of invoice {voce.numero} dated {voce.data}: same order and same amount",
                )
            )
    return scatti


def controlla_riga(riga: dict, ordine: Ordine, abbinamenti: dict[int, int | None] | None) -> list[Scatto]:
    n = riga["n"]
    if riga.get("num_item") is not None:
        voce = ordine.riga(int(riga["num_item"]))
        if voce is None:
            return [
                Scatto(
                    "A11",
                    "persona",
                    f"Riga {n}: la riga {riga['num_item']} dell'ordine non esiste",
                    f"Line {n}: purchase order line {riga['num_item']} does not exist",
                )
            ]
    elif abbinamenti is None or n not in abbinamenti:
        return [
            Scatto(
                "A11",
                "da_giudicare",
                f"Riga {n} «{riga['descrizione']}»: da abbinare all'ordine",
                f"Line {n} “{riga['descrizione']}”: to be matched to the purchase order",
            )
        ]
    elif abbinamenti[n] is None:
        return [
            Scatto(
                "A11",
                "persona",
                f"Riga {n} «{riga['descrizione']}»: non corrisponde a nessuna riga dell'ordine",
                f"Line {n} “{riga['descrizione']}”: matches no purchase order line",
            )
        ]
    else:
        voce = ordine.riga(abbinamenti[n])
    return confronta(riga, voce)


def confronta(riga: dict, voce: RigaOrdine) -> list[Scatto]:
    n, scatti = riga["n"], []
    prezzo, prezzo_ordine = importo(riga["prezzo_unitario"]), importo(voce.prezzo_unitario)
    aumento = (prezzo - prezzo_ordine) / prezzo_ordine
    if aumento > PERSONA_FINO_A:
        scatti.append(
            Scatto(
                "A09b",
                "bloccare",
                f"Riga {n}: prezzo {prezzo} oltre il 10% sopra l'ordine ({prezzo_ordine})",
                f"Line {n}: price {prezzo} more than 10% above the order ({prezzo_ordine})",
            )
        )
    elif aumento > PAGA_FINO_A:
        scatti.append(
            Scatto(
                "A09a",
                "persona",
                f"Riga {n}: prezzo {prezzo} dal 2% al 10% sopra l'ordine ({prezzo_ordine})",
                f"Line {n}: price {prezzo} 2% to 10% above the order ({prezzo_ordine})",
            )
        )
    if Decimal(str(riga["quantita"])) > Decimal(str(voce.residuo)):
        scatti.append(
            Scatto(
                "A10",
                "bloccare",
                f"Riga {n}: quantità {riga['quantita']} oltre il residuo dell'ordine ({voce.residuo})",
                f"Line {n}: quantity {riga['quantita']} exceeds the order's remaining {voce.residuo}",
            )
        )
    if Decimal(str(riga["aliquota"])) != Decimal(str(voce.aliquota)):
        scatti.append(
            Scatto(
                "A12",
                "persona",
                f"Riga {n}: aliquota {riga['aliquota']}% diversa dall'ordine ({voce.aliquota}%)",
                f"Line {n}: VAT rate {riga['aliquota']}% differs from the order ({voce.aliquota}%)",
            )
        )
    return scatti
