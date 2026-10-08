"""Il confronto fra impegno e lettura sugli 8 dati critici.

L'impegno è ciò che l'estrattore dichiara; la lettura è ciò che il verificatore ricava dalla memoria, senza vedere la
fattura. Stessi formati di `fatture.normalizza`, così uno stesso dato scritto in due modi non è una discordanza.
"""

from __future__ import annotations

from dataclasses import dataclass

from fatture.normalizza import iban, id_fiscale, numero_documento, stesso_importo


@dataclass(frozen=True)
class Campo:
    nome: str
    percorso: tuple[str, ...]
    tipo: str  # id, numero, data, importo, iban
    it: str
    en: str


CAMPI_CRITICI = (
    Campo("fornitore.id_fiscale", ("fornitore", "id_fiscale"), "id", "identificativo fiscale del fornitore", "supplier tax ID"),
    Campo("documento.numero", ("documento", "numero"), "numero", "numero del documento", "invoice number"),
    Campo("documento.data", ("documento", "data"), "data", "data del documento", "invoice date"),
    Campo("totale_documento", ("totale_documento",), "importo", "totale", "invoice total"),
    Campo("pagamento.iban", ("pagamento", "iban"), "iban", "IBAN", "IBAN"),
    Campo("pagamento.importo", ("pagamento", "importo"), "importo", "importo da pagare", "amount due"),
    Campo("pagamento.scadenza", ("pagamento", "scadenza"), "data", "scadenza", "due date"),
    Campo("ordine.numero", ("ordine", "numero"), "numero", "numero d'ordine", "purchase order number"),
)  # fmt: skip


@dataclass(frozen=True)
class Discordanza:
    campo: str
    dichiarato: object
    letto: object


def valore(dichiarazione: dict | None, percorso: tuple[str, ...]):
    nodo = dichiarazione
    for pezzo in percorso:
        if not isinstance(nodo, dict):
            return None
        nodo = nodo.get(pezzo)
    return nodo


def uguali(tipo: str, a, b) -> bool:
    if tipo == "importo":
        return stesso_importo(a, b)
    if tipo == "iban":
        return iban(str(a)) == iban(str(b))
    if tipo == "id":
        return id_fiscale(str(a)) == id_fiscale(str(b))
    if tipo == "numero":
        return numero_documento(str(a)) == numero_documento(str(b))
    return str(a) == str(b)  # date ISO: uguaglianza esatta


def confronta(
    dichiarato: dict | None, letto: dict | None, campi: tuple[Campo, ...] = CAMPI_CRITICI
) -> tuple[list[Discordanza], list[str]]:
    """Le discordanze campo per campo e i campi vuoti (`null`) in uno dei due, che non si possono verificare."""
    discordanze, vuoti = [], []
    for campo in campi:
        a, b = valore(dichiarato, campo.percorso), valore(letto, campo.percorso)
        if a is None or b is None:
            vuoti.append(campo.nome)
        elif not uguali(campo.tipo, a, b):
            discordanze.append(Discordanza(campo.nome, a, b))
    return discordanze, vuoti
