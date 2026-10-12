"""Il taglio del contratto in una sezione per lettore, con una regola sui titoli delle clausole.

Niente LLM né classificatori: riconoscere la categoria è il compito del Consiglio. Ogni clausola sta in una sola
sezione; preambolo, definizioni e clausole senza ruolo vanno al legale; con meno di tre titoli il contratto si divide
in parti contigue, una per lettore. Un errore di instradamento non è fatale, perché il relatore riceve tutto.
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field

LEGALE, FINANZA, RISCHIO = "legale", "finanza", "rischio"

# Parole chiave dei titoli, per famiglia di contratti e per ruolo: espressioni regolari, cercate dall'inizio di una
# parola. Vengono dalle categorie di ogni ruolo, in inglese e in italiano.
PAROLE_CHIAVE: dict[str, dict[str, list[str]]] = {
    # CUAD e set dimostrativo.
    "commerciale": {
        FINANZA: [
            r"payment",
            r"price",
            r"pricing",
            r"fees?\b",
            r"compensation",
            r"royalt",
            r"invoic",
            r"purchase",
            r"minimum",
            r"volume",
            r"quantit",
            r"forecast",
            r"rates?\b",
            r"rebate",
            r"most favou?red",
            r"liquidated damages",
            r"penalt",
            r"costs?\b",
            r"expenses",
            r"commission",
            r"financial",
            r"corrispettiv",
            r"prezz",
            r"pagament",
            r"fattur",
            r"penal",
            r"minim",
            r"compens",
            r"budget",
            r"canon",
            r"tariff",
            r"condizioni economiche",
            r"spese",
            r"commission",
        ],
        RISCHIO: [
            r"term\b",
            r"terminat",
            r"expiration",
            r"renewal",
            r"assign",
            r"change (of|in) control",
            r"exclusiv",
            r"non-?compet",
            r"compet",
            r"solicit",
            r"first (refusal|offer|negotiation)",
            r"employees",
            r"hiring",
            r"restrictive covenant",
            r"transfer",
            r"durata",
            r"recesso",
            r"risoluzione",
            r"rinnovo",
            r"cession",
            r"cambio di controllo",
            r"prelazione",
            r"esclusiv",
            r"concorren",
            r"personale",
            r"dipendenti",
            r"sollecit",
            r"storno",
        ],
        LEGALE: [
            r"liabilit",
            r"indemn",
            r"intellectual property",
            r"ownership",
            r"licen[cs]",
            r"covenant not to sue",
            r"disparag",
            r"warrant",
            r"confidential",
            r"governing law",
            r"dispute",
            r"arbitration",
            r"definitions",
            r"responsabilit",
            r"proprietà intellettuale",
            r"diritti",
            r"materiali",
            r"manleva",
            r"garanzi",
            r"riservatezz",
            r"legge applicabile",
            r"foro",
            r"controversi",
            r"definizion",
        ],
    },
    # ContractNLI: la finanza non è convocata.
    "nda": {
        RISCHIO: [
            r"use\b",
            r"purpose",
            r"employee",
            r"representative",
            r"third part",
            r"return",
            r"destr",
            r"term\b",
            r"terminat",
            r"surviv",
            r"solicit",
            r"independent",
            r"develop",
            r"possession",
            r"retain",
            r"residual",
            r"standstill",
        ],
        LEGALE: [
            r"confidential",
            r"definition",
            r"evaluation material",
            r"verbal",
            r"oral",
            r"compelled",
            r"required (by law|disclosure)",
            r"legal",
            r"reverse",
            r"cop(y|ies)",
            r"licen[cs]",
            r"property",
            r"rights",
            r"remed",
            r"governing law",
            r"jurisdiction",
        ],
    },
    # CLAUDETTE: ToS in italiano, la finanza non è convocata.
    "tos": {
        RISCHIO: [
            r"modific",
            r"variazion",
            r"aggiornament",
            r"recesso",
            r"sospension",
            r"cessazion",
            r"chiusura",
            r"risoluzion",
            r"rimozion",
            r"contenut",
            r"account",
            r"changes",
            r"terminat",
            r"suspen",
            r"content",
        ],
        LEGALE: [
            r"responsabilit",
            r"garanzi",
            r"arbitrat",
            r"foro",
            r"giurisdizion",
            r"tribunal",
            r"legge",
            r"privacy",
            r"dati personali",
            r"accett",
            r"condizioni d'uso",
            r"liabilit",
            r"law",
            r"dispute",
        ],
    },
}

# Prima i ruoli più specifici: il legale è quello di riserva.
PRIORITA = (FINANZA, RISCHIO, LEGALE)

_PAROLE_MINORI = {
    "of",
    "and",
    "the",
    "a",
    "an",
    "to",
    "for",
    "in",
    "on",
    "by",
    "with",
    "or",
    "its",
    "at",
    "as",
    "from",
    "upon",
}
_NUMERATO = re.compile(
    r"(?:^|(?<=\n)|(?<=\s\s))"
    r"(?P<testa>(?:(?:ARTICLE|Article|SECTION|Section|ART\.|Art\.|ARTICOLO|Articolo|CLAUSE|Clause)\s+)?"
    r"(?:\d{1,2}(?:\.\d{1,2})?|[IVXL]{1,6}(?=[.\s]))\.?)"
    r"[ \t]*[–—-]?[ \t]*"
    r"(?P<titolo>[A-ZÀ-Ý][^\n.:;]{1,70}?)"
    r"(?=\.\s|\.$|\n|:\s|\s{2,}|$|[ \t]+\d{1,2}\.\d{1,2}\b)"
)
# Titoli tutti in maiuscolo anche in mezzo a una riga: "...as follows: 1. INTERPRETATION 1.1 In this Agreement".
_MAIUSCOLO_IN_LINEA = re.compile(
    r"(?<=\s)(?P<testa>\d{1,2}\.)[ \t]+(?P<titolo>[A-Z][A-Z &,/'-]{2,60}[A-Z])(?=[ \t]+\d{1,2}\.\d{1,2}\b|\.\s|\s{2,}|\n|$)"
)


@dataclass
class Clausola:
    inizio: int
    titolo: str
    ruolo: str


@dataclass
class Taglio:
    sezioni: dict[str, str]
    clausole: list[Clausola] = field(default_factory=list)
    modo: str = "titoli"


@dataclass(frozen=True)
class Titolo:
    posizione: int
    testo: str
    numerato: bool


def _iniziali_maiuscole(titolo: str) -> bool:
    """Titolo all'inglese: tutto maiuscolo, oppure ogni parola importante con l'iniziale maiuscola."""
    parole = re.findall(r"[A-Za-zÀ-ÿ'’-]+", titolo)
    if not parole:
        return False
    if all(p.isupper() for p in parole if len(p) > 1):
        return True
    importanti = [p for p in parole if p.lower() not in _PAROLE_MINORI]
    return bool(importanti) and all(p[0].isupper() for p in importanti)


def trova_titoli(testo: str) -> list[Titolo]:
    """I titoli di clausola, numerati ("2. Fees.", "Art. 3 – Esclusiva di acquisto") o su una riga da soli.

    Gli indici, cioè un titolo seguito da un numero di pagina, non contano.
    """
    trovati: dict[int, Titolo] = {}
    for m in _NUMERATO.finditer(testo):
        titolo = m.group("titolo").strip()
        dopo = testo[m.end("titolo") :]
        # Voci d'indice: un numero di pagina dopo il titolo o dentro ("Interpretation 3 2").
        if len(titolo.split()) > 9 or re.match(r"[ \t]+\d{1,3}\b", dopo) or re.search(r"\s\d{1,3}(\s|$)", titolo):
            continue
        # Su una riga da sola e senza punto finale basta che sia corto ("Art. 3 – Esclusiva di acquisto");
        # in linea ("1. Fees. For its...") deve avere le iniziali maiuscole come i titoli inglesi.
        da_solo = re.match(r"[ \t]*(\n|$)", dopo) is not None
        if (da_solo and len(titolo.split()) <= 7) or _iniziali_maiuscole(titolo):
            trovati[m.start("testa")] = Titolo(m.start("testa"), titolo, True)
    for m in _MAIUSCOLO_IN_LINEA.finditer(testo):
        if m.start("testa") not in trovati and len(m.group("titolo").split()) <= 9:
            trovati[m.start("testa")] = Titolo(m.start("testa"), m.group("titolo").strip(), True)
    # Le righe che si ripetono sono intestazioni e piè di pagina ("Table of Contents", "Source: ...").
    ripetute = {r for r, n in Counter(r.strip() for r in testo.split("\n")).items() if n > 1}
    posizione = 0
    for riga in testo.split("\n"):
        pulita = riga.strip()
        inizio = posizione + (len(riga) - len(riga.lstrip()))
        posizione += len(riga) + 1
        if (
            pulita
            and inizio not in trovati
            and len(pulita) <= 80
            and len(pulita.split()) <= 8
            and pulita[0].isupper()
            and pulita[-1] not in ".:;,"
            and ":" not in pulita
            and pulita not in ripetute
            and "__" not in pulita
            and re.search(r"[A-Za-zÀ-ÿ]{3}", pulita)
            and not re.search(r"\s\d{1,3}$", pulita)
        ):
            trovati[inizio] = Titolo(inizio, pulita, False)
    return [trovati[p] for p in sorted(trovati)]


def ruolo_del_titolo(titolo: str, famiglia: str, lettori: tuple[str, ...]) -> str | None:
    minuscolo = titolo.lower()
    punteggi = {
        ruolo: sum(bool(re.search(r"\b" + chiave, minuscolo)) for chiave in PAROLE_CHIAVE[famiglia].get(ruolo, []))
        for ruolo in lettori
    }
    migliore = max(punteggi.values(), default=0)
    if migliore == 0:
        return None
    return next(r for r in PRIORITA if r in lettori and punteggi[r] == migliore)


def _confine(testo: str, obiettivo: int) -> int:
    """Il punto di taglio più vicino all'obiettivo: un a capo se è vicino, altrimenti una fine di frase o uno spazio."""
    tolleranza = max(200, len(testo) // 20)
    for separatore in ("\n", ". ", " "):
        prima = testo.rfind(separatore, 0, obiettivo)
        dopo = testo.find(separatore, obiettivo)
        candidati = [i + len(separatore) for i in (prima, dopo) if i != -1 and abs(i - obiettivo) <= tolleranza]
        if candidati:
            return min(candidati, key=lambda i: abs(i - obiettivo))
    return obiettivo


def _contiguo(testo: str, lettori: tuple[str, ...]) -> Taglio:
    """Parti contigue di lunghezza simile, una per lettore, nell'ordine della staffetta."""
    tagli = [0] + [_confine(testo, round(len(testo) * i / len(lettori))) for i in range(1, len(lettori))] + [len(testo)]
    tagli = [max(t, tagli[i - 1]) if i else t for i, t in enumerate(tagli)]
    sezioni = {ruolo: testo[tagli[i] : tagli[i + 1]].strip() for i, ruolo in enumerate(lettori)}
    return Taglio(sezioni, [], "contiguo")


def taglia(testo: str, lettori: tuple[str, ...], famiglia: str) -> Taglio:
    """Con almeno tre titoli numerati, oppure tre titoli su una riga da soli nel corpo del testo (come nei ToS),
    il taglio segue i titoli. Altrimenti le parti sono contigue: indirizzi e firme di una lettera non contano."""
    titoli = trova_titoli(testo)
    numerati = [t for t in titoli if t.numerato]
    nel_corpo = [t for t in titoli if not t.numerato and 0.15 * len(testo) < t.posizione < 0.85 * len(testo)]
    if len(numerati) < 3 and len(nel_corpo) < 3:
        return _contiguo(testo, lettori)
    riserva = LEGALE if LEGALE in lettori else lettori[0]
    clausole = [Clausola(0, "(preambolo)", riserva)] if titoli[0].posizione > 0 else []
    clausole += [
        Clausola(
            t.posizione,
            t.testo,
            ruolo_del_titolo(t.testo, famiglia, lettori) or riserva,
        )
        for t in titoli
    ]
    pezzi: dict[str, list[str]] = {ruolo: [] for ruolo in lettori}
    for clausola, successiva in zip(clausole, clausole[1:] + [None]):
        fine = successiva.inizio if successiva else len(testo)
        pezzo = testo[clausola.inizio : fine].strip()
        if pezzo:
            pezzi[clausola.ruolo].append(pezzo)
    return Taglio({ruolo: "\n\n[…]\n\n".join(p) for ruolo, p in pezzi.items()}, clausole, "titoli")
