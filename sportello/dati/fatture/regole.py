"""Le regole del catalogo: A01-A13 sui campi dell'impegno e sugli archivi, in modo deterministico.

A11 (riga che non corrisponde a nessuna riga dell'ordine) la giudica il modello: le righe senza un `num_item` numerico si
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


def dati_mancanti(impegno: dict) -> list[tuple[str, str]]:
    """I dati senza i quali le regole non possono controllare: (italiano, inglese)."""
    documento, pagamento = impegno.get("documento") or {}, impegno.get("pagamento") or {}
    mancanti = []
    if not (impegno.get("fornitore") or {}).get("id_fiscale"):
        mancanti.append(("identificativo fiscale del fornitore", "supplier tax ID"))
    if not documento.get("numero"):
        mancanti.append(("numero del documento", "invoice number"))
    if giorno_di(documento.get("data")) is None:
        mancanti.append(("data del documento", "invoice date"))
    if not pagamento.get("iban"):
        mancanti.append(("IBAN", "IBAN"))
    return mancanti


def applica_regole(impegno: dict, archivi: Archivi, abbinamenti: dict[int, int | None] | None = None) -> list[Scatto]:
    scatti: list[Scatto] = []
    if mancanti := dati_mancanti(impegno):
        # A00 non è nel catalogo di mai "pagare" senza aver potuto controllare. Coincide con la regola di «Regole di coerenza» sui
        # campi critici vuoti, ma vale anche da sola, per esempio con la coerenza spenta nella demo.
        it, en = ", ".join(m[0] for m in mancanti), ", ".join(m[1] for m in mancanti)
        scatti.append(
            Scatto(
                "A00",
                "persona",
                f"Dati mancanti o non validi, le regole non possono controllarli: {it}",
                f"Missing or invalid data the rules cannot check: {en}",
            )
        )
    if not (impegno.get("fornitore") or {}).get("id_fiscale"):
        return [*scatti, *totali(impegno)]  # senza fornitore non c'è niente con cui confrontare
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
    ordine = archivi.ordine(numero_ordine)
    if ordine is None or id_fiscale(ordine.fornitore) != id_fornitore:
        motivo = "inesistente" if ordine is None else f"intestato a un altro fornitore ({ordine.fornitore})"
        motivo_en = "does not exist" if ordine is None else f"belongs to another supplier ({ordine.fornitore})"
        scatti.append(
            Scatto("A08", "bloccare", f"Ordine {numero_ordine} {motivo}", f"Purchase order {numero_ordine} {motivo_en}")
        )
        return scatti
    # Le quantità si sommano per riga d'ordine: due righe della fattura sulla stessa voce non passano ognuna per conto
    # suo contro tutto il residuo (F7 di una voce in più fatta passare per "compresa nella riga 1").
    per_voce: dict[int, list[dict]] = {}
    for riga in impegno["righe"]:
        scatti_riga, voce = controlla_riga(riga, ordine, abbinamenti)
        scatti += scatti_riga
        if voce is not None:
            per_voce.setdefault(voce.n, []).append(riga)
    return scatti + quantita_oltre_il_residuo(per_voce, ordine)


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


def giorno_di(valore) -> date | None:
    """Una data ISO, oppure None se manca o è impossibile (un estrattore vero può scrivere 2026-15-09)."""
    try:
        return date.fromisoformat(valore) if valore else None
    except (TypeError, ValueError):
        return None


def duplicati(impegno: dict, archivi: Archivi, id_fornitore: str) -> list[Scatto]:
    documento = impegno["documento"]
    numero = numero_documento(documento["numero"]) if documento.get("numero") else None
    giorno = giorno_di(documento.get("data"))
    numero_ordine = (impegno.get("ordine") or {}).get("numero")
    ordine = archivi.ordine(numero_ordine)
    scatti = []
    for voce in archivi.storico:
        if id_fiscale(voce.fornitore) != id_fornitore:
            continue
        giorno_voce = date.fromisoformat(voce.data)
        # Con una data impossibile si confronta solo il numero, e senza numero solo ordine, importo e data: meglio un
        # dubbio in più che un duplicato pagato.
        if (
            numero is not None
            and numero_documento(voce.numero) == numero
            and (giorno is None or giorno_voce.year == giorno.year)
        ):
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
            and voce.ordine
            and numero_documento(voce.ordine) == numero_documento(numero_ordine)
            and stesso_importo(voce.importo, impegno["totale_documento"])
            and (giorno is None or abs((giorno - giorno_voce).days) <= GIORNI_DUPLICATO)
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


def riferimento(riga: dict) -> int | None:
    """La riga d'ordine indicata in fattura (`num_item`), se è un numero. Altrimenti la riga è libera: un estrattore
    vero può scrivere lì il codice del prodotto, e allora la riga si abbina come le altre senza riferimento."""
    valore = riga.get("num_item")
    try:
        return None if valore is None else int(str(valore).strip())
    except ValueError:
        return None


def controlla_riga(
    riga: dict, ordine: Ordine, abbinamenti: dict[int, int | None] | None
) -> tuple[list[Scatto], RigaOrdine | None]:
    """Gli scatti della riga e la voce dell'ordine a cui corrisponde, se c'è."""
    n = riga["n"]
    numero = riferimento(riga)
    if numero is not None:
        voce = ordine.riga(numero)
        if voce is None:
            return [
                Scatto(
                    "A11",
                    "persona",
                    f"Riga {n}: la riga {numero} dell'ordine non esiste",
                    f"Line {n}: purchase order line {numero} does not exist",
                )
            ], None
        return confronta(riga, voce, abbinata=False), voce
    if abbinamenti is None or n not in abbinamenti:
        return [
            Scatto(
                "A11",
                "da_giudicare",
                f"Riga {n} «{riga['descrizione']}»: da abbinare all'ordine",
                f"Line {n} “{riga['descrizione']}”: to be matched to the purchase order",
            )
        ], None
    voce = ordine.riga(abbinamenti[n]) if abbinamenti[n] is not None else None
    if voce is None:
        return [
            Scatto(
                "A11",
                "persona",
                f"Riga {n} «{riga['descrizione']}»: non corrisponde a nessuna riga dell'ordine",
                f"Line {n} “{riga['descrizione']}”: matches no purchase order line",
            )
        ], None
    return confronta(riga, voce, abbinata=True), voce


def codice_compatto(codice: str | None) -> str:
    return re.sub(r"[^A-Z0-9]", "", str(codice or "").upper())


def confronta(riga: dict, voce: RigaOrdine, *, abbinata: bool) -> list[Scatto]:
    """La riga contro la sua voce d'ordine. Il riferimento (scritto dall'estrattore) e l'abbinamento (fatto dal modello,
    `abbinata`) non si prendono sulla parola: la riga deve essere quella voce, quindi stesso codice e stesso prezzo,
    né più alto né più basso (F7 di una voce in più fatta passare per "compresa nella riga 1")."""
    n, scatti = riga["n"], []
    prezzo, prezzo_ordine = importo(riga["prezzo_unitario"]), importo(voce.prezzo_unitario)
    aumento = (prezzo - prezzo_ordine) / prezzo_ordine
    codice, codice_ordine = codice_compatto(riga.get("codice")), codice_compatto(voce.codice)
    if codice and codice_ordine and codice != codice_ordine:
        scatti.append(
            Scatto(
                "A11",
                "persona",
                f"Riga {n}: codice {riga['codice']} diverso dalla riga {voce.n} dell'ordine ({voce.codice})",
                f"Line {n}: item code {riga['codice']} differs from purchase order line {voce.n} ({voce.codice})",
            )
        )
    if -aumento > PAGA_FINO_A:
        modo_it, modo_en = ("l'abbinamento", "the match") if abbinata else ("il riferimento", "the reference")
        scatti.append(
            Scatto(
                "A11",
                "persona",
                f"Riga {n} «{riga['descrizione']}»: prezzo {prezzo} sotto la riga {voce.n} dell'ordine ({prezzo_ordine}), "
                f"{modo_it} non torna",
                f"Line {n} “{riga['descrizione']}”: price {prezzo} below purchase order line {voce.n} ({prezzo_ordine}), "
                f"{modo_en} does not hold",
            )
        )
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


def quantita_oltre_il_residuo(per_voce: dict[int, list[dict]], ordine: Ordine) -> list[Scatto]:
    """A10 sulla somma: tutte le righe della fattura che cadono sulla stessa voce d'ordine, insieme."""
    scatti = []
    for numero, righe in per_voce.items():
        voce = ordine.riga(numero)
        totale = sum((Decimal(str(r["quantita"])) for r in righe), Decimal(0))
        if totale <= Decimal(str(voce.residuo)):
            continue
        if len(righe) == 1:
            n, q = righe[0]["n"], righe[0]["quantita"]
            it = f"Riga {n}: quantità {q} oltre il residuo dell'ordine ({voce.residuo})"
            en = f"Line {n}: quantity {q} exceeds the order's remaining {voce.residuo}"
        else:
            elenco = ", ".join(str(r["n"]) for r in righe)
            it = f"Righe {elenco}: quantità {totale:g} insieme oltre il residuo della riga {numero} dell'ordine ({voce.residuo})"
            en = f"Lines {elenco}: quantity {totale:g} together exceed the remaining {voce.residuo} of purchase order line {numero}"
        scatti.append(Scatto("A10", "bloccare", it, en))
    return scatti
