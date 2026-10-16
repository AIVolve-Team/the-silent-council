"""Le categorie che il Consiglio giudica, per benchmark, con nome e descrizione in italiano per i prompt.

Ruoli e lettori vengono da `consiglio/dati/categorie.py`. Le chiavi sono il campo `categoria` di
`risposte-giuste.jsonl`, così il verdetto si confronta direttamente con la risposta giusta.
Le descrizioni di CUAD seguono le definizioni ufficiali delle categorie, quelle di ContractNLI riportano l'ipotesi.
"""

from __future__ import annotations

from dataclasses import dataclass

from .dati import categorie_dati

_DATI = categorie_dati()
LEGALE, FINANZA, RISCHIO = _DATI.LEGALE, _DATI.FINANZA, _DATI.RISCHIO


@dataclass(frozen=True)
class Categoria:
    chiave: str
    nome: str
    ruolo: str
    descrizione: str


@dataclass(frozen=True)
class Benchmark:
    nome: str
    famiglia: str
    lettori: tuple[str, ...]
    categorie: tuple[Categoria, ...]
    # Che cosa vuol dire "da segnalare" su questo benchmark.
    regola: str
    lingua: str

    def del_ruolo(self, ruolo: str) -> tuple[Categoria, ...]:
        return tuple(c for c in self.categorie if c.ruolo == ruolo)


_CUAD = {
    "Uncapped Liability": (
        "Responsabilità illimitata",
        (
            "la responsabilità di una parte per un inadempimento non ha tetto, anche solo per un tipo di violazione "
            "(per esempio proprietà intellettuale o riservatezza)"
        ),
    ),
    "Cap On Liability": (
        "Tetto alla responsabilità",
        (
            "c'è un limite alla responsabilità per inadempimento: un importo massimo, un termine per agire o "
            "l'esclusione di certi danni"
        ),
    ),
    "Ip Ownership Assignment": (
        "Cessione della proprietà intellettuale",
        "la proprietà intellettuale creata da una parte diventa dell'altra, per contratto o al verificarsi di un evento",
    ),
    "Joint Ip Ownership": (
        "Proprietà intellettuale condivisa",
        "la proprietà intellettuale è in comune o condivisa fra le parti",
    ),
    "Irrevocable Or Perpetual License": (
        "Licenza irrevocabile o perpetua",
        "il contratto concede una licenza irrevocabile o perpetua",
    ),
    "Covenant Not To Sue": (
        "Rinuncia a fare causa",
        (
            "una parte non può contestare la proprietà intellettuale dell'altra o farle causa per questioni estranee "
            "al contratto"
        ),
    ),
    "Non-Disparagement": ("Divieto di denigrazione", "una parte non può parlare male dell'altra"),
    "Liquidated Damages": (
        "Penale predeterminata",
        (
            "una parte deve pagare una somma fissata in anticipo per un inadempimento, oppure un costo per uscire "
            "dal contratto"
        ),
    ),
    "Minimum Commitment": (
        "Minimo d'acquisto",
        "una parte deve comprare dall'altra una quantità o un importo minimo in un certo periodo",
    ),
    "Volume Restriction": (
        "Limite di volume",
        "se l'uso di un prodotto o servizio supera una soglia, il prezzo aumenta o serve un consenso",
    ),
    "Most Favored Nation": (
        "Cliente più favorito",
        "se un terzo ottiene condizioni migliori per lo stesso bene o servizio, chi compra ha diritto alle stesse",
    ),
    "Change Of Control": (
        "Cambio di controllo",
        (
            "se una parte cambia proprietà (fusione, vendita delle quote o dell'azienda) l'altra può recedere, "
            "o serve il suo consenso o un avviso"
        ),
    ),
    "Anti-Assignment": (
        "Divieto di cessione",
        "per cedere il contratto a un terzo serve il consenso o un avviso all'altra parte",
    ),
    "Rofr/Rofo/Rofn": (
        "Diritto di prelazione",
        "una parte ha un diritto di prima offerta, di prelazione o di prima trattativa su beni, servizi o quote",
    ),
    "Termination For Convenience": (
        "Recesso senza motivo",
        "una parte può recedere senza giusta causa, con un semplice preavviso",
    ),
    "Non-Compete": (
        "Non concorrenza",
        "una parte non può fare concorrenza all'altra o operare in un territorio, settore o tecnologia",
    ),
    "Exclusivity": (
        "Esclusiva",
        (
            "c'è un impegno in esclusiva: comprare tutto da una parte, o non vendere o collaborare con altri, "
            "durante o dopo il contratto"
        ),
    ),
    "No-Solicit Of Customers": (
        "Divieto di sottrarre clienti",
        "una parte non può sollecitare o contrattare con i clienti o i partner dell'altra",
    ),
    "No-Solicit Of Employees": (
        "Divieto di assumere dipendenti",
        "una parte non può sollecitare o assumere dipendenti o collaboratori dell'altra",
    ),
}

_CONTRACTNLI = {
    "nda-1": "All Confidential Information shall be expressly identified by the Disclosing Party.",
    "nda-2": "Confidential Information shall only include technical information.",
    "nda-3": "Confidential Information may include verbally conveyed information.",
    "nda-4": "Receiving Party shall not use any Confidential Information for any purpose other than the purposes "
    "stated in Agreement.",
    "nda-5": "Receiving Party may share some Confidential Information with some of Receiving Party's employees.",
    "nda-7": "Receiving Party may share some Confidential Information with some third-parties (including "
    "consultants, agents and professional advisors).",
    "nda-8": "Receiving Party shall notify Disclosing Party in case Receiving Party is required by law, regulation "
    "or judicial process to disclose any Confidential Information.",
    "nda-10": "Receiving Party shall not disclose the fact that Agreement was agreed or negotiated.",
    "nda-11": "Receiving Party shall not reverse engineer any objects which embody Disclosing Party's Confidential "
    "Information.",
    "nda-12": "Receiving Party may independently develop information similar to Confidential Information.",
    "nda-13": "Receiving Party may acquire information similar to Confidential Information from a third party.",
    "nda-15": "Agreement shall not grant Receiving Party any right to Confidential Information.",
    "nda-16": "Receiving Party shall destroy or return some Confidential Information upon the termination of "
    "Agreement.",
    "nda-17": "Receiving Party may create a copy of some Confidential Information in some circumstances.",
    "nda-18": "Receiving Party shall not solicit some of Disclosing Party's representatives.",
    "nda-19": "Some obligations of Agreement may survive termination of Agreement.",
    "nda-20": "Receiving Party may retain some Confidential Information even after the return or destruction of "
    "Confidential Information.",
}

_CLAUDETTE = {
    "ltd": "il fornitore esclude o limita la propria responsabilità per danni, perdite o malfunzionamenti",
    "a": "le controversie vanno a un arbitrato invece che davanti a un giudice",
    "j": "le controversie si discutono davanti a un tribunale scelto dal fornitore, lontano dal consumatore",
    "law": "si applica una legge diversa da quella del paese del consumatore",
    "use": "il consumatore accetta le condizioni per il solo fatto di usare il servizio",
    "pinc": "accettando le condizioni si accetta anche il trattamento dei dati personali",
    "ch": "il fornitore può cambiare le condizioni o il servizio quando vuole",
    "ter": "il fornitore può sospendere o chiudere il servizio o l'account quando vuole",
    "cr": "il fornitore può rimuovere i contenuti dell'utente",
}

_COMMERCIALE = tuple(
    Categoria(chiave, nome, ruolo, descrizione)
    for chiave, ruolo in _DATI.CUAD_CATEGORIE.items()
    for nome, descrizione in [_CUAD[chiave]]
)

BENCHMARK = {
    "cuad": Benchmark(
        "cuad",
        "commerciale",
        tuple(_DATI.LETTORI["cuad"]),
        _COMMERCIALE,
        "true se nel contratto c'è una clausola di questo tipo, qualunque parte riguardi; false se non c'è",
        "en",
    ),
    "contractnli": Benchmark(
        "contractnli",
        "nda",
        tuple(_DATI.LETTORI["contractnli"]),
        tuple(
            Categoria(descrizione, descrizione, ruolo, f'ipotesi: "{_CONTRACTNLI[ipotesi]}"')
            for ipotesi, (descrizione, ruolo) in _DATI.CONTRACTNLI_IPOTESI.items()
        ),
        "true se l'accordo dice il contrario dell'ipotesi; false se la conferma o non ne parla",
        "en",
    ),
    "claudette": Benchmark(
        "claudette",
        "tos",
        tuple(_DATI.LETTORI["claudette"]),
        tuple(
            Categoria(nome, nome, ruolo, _CLAUDETTE[tag]) for tag, (nome, ruolo) in _DATI.CLAUDETTE_CATEGORIE.items()
        ),
        (
            "true se c'è una clausola di questo tipo potenzialmente o chiaramente abusiva per il consumatore; "
            "false altrimenti"
        ),
        "it",
    ),
}
# Il set dimostrativo usa le 19 categorie di CUAD e i quattro ruoli.
BENCHMARK["dimostrativo"] = Benchmark(
    "dimostrativo", "commerciale", BENCHMARK["cuad"].lettori, _COMMERCIALE, BENCHMARK["cuad"].regola, "it"
)

NOMI_RUOLI = {LEGALE: "legale", FINANZA: "di finanza", RISCHIO: "di rischio"}
