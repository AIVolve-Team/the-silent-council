"""Gli archivi che lo Sportello interroga: anagrafica fornitori, ordini e storico delle fatture."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path

from .normalizza import numero_documento


@dataclass
class Fornitore:
    id_fiscale: str
    denominazione: str
    iban: str
    attivo: bool = True
    # I contatti servono alla verifica guidata sulla pagina del caso: mai quelli scritti nella fattura.
    telefono: str = ""
    email: str = ""
    paese: str = "IT"


@dataclass
class RigaOrdine:
    n: int
    codice: str
    descrizione: str
    quantita: float
    prezzo_unitario: float
    aliquota: float
    residuo: float


@dataclass
class Ordine:
    numero: str
    fornitore: str
    data: str
    righe: list[RigaOrdine]
    # Più di una rata: le fatture ripetute sono previste (canoni), quindi non sono duplicati mascherati (A02).
    rate: int = 1

    def riga(self, n: int) -> RigaOrdine | None:
        return next((r for r in self.righe if r.n == n), None)


@dataclass
class VoceStorico:
    fornitore: str
    numero: str
    data: str
    importo: float
    ordine: str | None
    stato: str = "pagata"


@dataclass
class Archivi:
    anagrafica: dict[str, Fornitore] = field(default_factory=dict)
    ordini: dict[str, Ordine] = field(default_factory=dict)
    storico: list[VoceStorico] = field(default_factory=list)

    def ordine(self, numero: str | None) -> Ordine | None:
        """L'ordine scritto in fattura, con il numero normalizzato come quello del documento in A01:
        `PO/2026/42` è `PO-2026-0042`."""
        if not numero:
            return None
        chiave = numero_documento(numero)
        return next((o for k, o in self.ordini.items() if numero_documento(k) == chiave), None)

    def salva(self, cartella: Path) -> None:
        cartella.mkdir(parents=True, exist_ok=True)
        dati = {
            "anagrafica": [asdict(f) for f in self.anagrafica.values()],
            "ordini": [asdict(o) for o in self.ordini.values()],
            "storico": [asdict(v) for v in self.storico],
        }
        for nome, valore in dati.items():
            (cartella / f"{nome}.json").write_text(json.dumps(valore, indent=1, ensure_ascii=False) + "\n")

    @classmethod
    def carica(cls, cartella: Path) -> Archivi:
        leggi = lambda nome: json.loads((cartella / f"{nome}.json").read_text())
        ordini = []
        for o in leggi("ordini"):
            o["righe"] = [RigaOrdine(**r) for r in o["righe"]]
            ordini.append(Ordine(**o))
        return cls(
            {f["id_fiscale"]: Fornitore(**f) for f in leggi("anagrafica")},
            {o.numero: o for o in ordini},
            [VoceStorico(**v) for v in leggi("storico")],
        )
