"""The split of the contract into one section per reader, with a rule on the clause headings.

No LLM nor classifiers: recognizing the category is the council's job. Each clause is in a single section;
preamble, definitions and clauses without a role go to the legal expert; with fewer than three headings the contract
is split into contiguous parts, one per reader. A routing mistake is not fatal, because the rapporteur receives
everything.
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field

LEGAL, FINANCE, RISK = "legal", "finance", "risk"

# Heading keywords, per contract family and per role: regular expressions, searched from the start of a word. They
# come from the categories of each role, in English and in Italian.
KEYWORDS: dict[str, dict[str, list[str]]] = {
    # CUAD and the demo set.
    "commercial": {
        FINANCE: [
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
        RISK: [
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
        LEGAL: [
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
    # ContractNLI: finance is not convened.
    "nda": {
        RISK: [
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
        LEGAL: [
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
    # CLAUDETTE: ToS in Italian, finance is not convened.
    "tos": {
        RISK: [
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
        LEGAL: [
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

# The most specific roles first: the legal expert is the fallback.
PRIORITY = (FINANCE, RISK, LEGAL)

_MINOR_WORDS = {
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
_NUMBERED = re.compile(
    r"(?:^|(?<=\n)|(?<=\s\s))"
    r"(?P<head>(?:(?:ARTICLE|Article|SECTION|Section|ART\.|Art\.|ARTICOLO|Articolo|CLAUSE|Clause)\s+)?"
    r"(?:\d{1,2}(?:\.\d{1,2})?|[IVXL]{1,6}(?=[.\s]))\.?)"
    r"[ \t]*[–—-]?[ \t]*"
    r"(?P<title>[A-ZÀ-Ý][^\n.:;]{1,70}?)"
    r"(?=\.\s|\.$|\n|:\s|\s{2,}|$|[ \t]+\d{1,2}\.\d{1,2}\b)"
)
# All-caps headings even in the middle of a line: "...as follows: 1. INTERPRETATION 1.1 In this Agreement".
_UPPERCASE_INLINE = re.compile(
    r"(?<=\s)(?P<head>\d{1,2}\.)[ \t]+(?P<title>[A-Z][A-Z &,/'-]{2,60}[A-Z])(?=[ \t]+\d{1,2}\.\d{1,2}\b|\.\s|\s{2,}|\n|$)"
)


@dataclass
class Clause:
    start: int
    title: str
    role: str


@dataclass
class Split:
    sections: dict[str, str]
    clauses: list[Clause] = field(default_factory=list)
    mode: str = "headings"


@dataclass(frozen=True)
class Heading:
    position: int
    text: str
    numbered: bool


def _title_case(title: str) -> bool:
    """English-style heading: all caps, or every important word with a capital initial."""
    words = re.findall(r"[A-Za-zÀ-ÿ'’-]+", title)
    if not words:
        return False
    if all(w.isupper() for w in words if len(w) > 1):
        return True
    important = [w for w in words if w.lower() not in _MINOR_WORDS]
    return bool(important) and all(w[0].isupper() for w in important)


def find_headings(text: str) -> list[Heading]:
    """The clause headings, numbered ("2. Fees.", "Art. 3 – Esclusiva di acquisto") or alone on a line.

    Tables of contents, that is a heading followed by a page number, do not count.
    """
    found: dict[int, Heading] = {}
    for m in _NUMBERED.finditer(text):
        title = m.group("title").strip()
        after = text[m.end("title") :]
        # Table of contents entries: a page number after the heading or inside it ("Interpretation 3 2").
        if len(title.split()) > 9 or re.match(r"[ \t]+\d{1,3}\b", after) or re.search(r"\s\d{1,3}(\s|$)", title):
            continue
        # Alone on a line and without a final full stop it is enough to be short ("Art. 3 – Esclusiva di acquisto");
        # inline ("1. Fees. For its...") it must have capital initials like English headings.
        alone = re.match(r"[ \t]*(\n|$)", after) is not None
        if (alone and len(title.split()) <= 7) or _title_case(title):
            found[m.start("head")] = Heading(m.start("head"), title, True)
    for m in _UPPERCASE_INLINE.finditer(text):
        if m.start("head") not in found and len(m.group("title").split()) <= 9:
            found[m.start("head")] = Heading(m.start("head"), m.group("title").strip(), True)
    # Lines that repeat are headers and footers ("Table of Contents", "Source: ...").
    repeated = {r for r, n in Counter(r.strip() for r in text.split("\n")).items() if n > 1}
    position = 0
    for line in text.split("\n"):
        clean = line.strip()
        start = position + (len(line) - len(line.lstrip()))
        position += len(line) + 1
        if (
            clean
            and start not in found
            and len(clean) <= 80
            and len(clean.split()) <= 8
            and clean[0].isupper()
            and clean[-1] not in ".:;,"
            and ":" not in clean
            and clean not in repeated
            and "__" not in clean
            and re.search(r"[A-Za-zÀ-ÿ]{3}", clean)
            and not re.search(r"\s\d{1,3}$", clean)
        ):
            found[start] = Heading(start, clean, False)
    return [found[p] for p in sorted(found)]


def role_of_heading(title: str, family: str, readers: tuple[str, ...]) -> str | None:
    lower = title.lower()
    scores = {
        role: sum(bool(re.search(r"\b" + keyword, lower)) for keyword in KEYWORDS[family].get(role, []))
        for role in readers
    }
    best = max(scores.values(), default=0)
    if best == 0:
        return None
    return next(r for r in PRIORITY if r in readers and scores[r] == best)


def _boundary(text: str, target: int) -> int:
    """The cut point closest to the target: a newline if it is close, otherwise the end of a sentence or a space."""
    tolerance = max(200, len(text) // 20)
    for separator in ("\n", ". ", " "):
        before = text.rfind(separator, 0, target)
        after = text.find(separator, target)
        candidates = [i + len(separator) for i in (before, after) if i != -1 and abs(i - target) <= tolerance]
        if candidates:
            return min(candidates, key=lambda i: abs(i - target))
    return target


def _contiguous(text: str, readers: tuple[str, ...]) -> Split:
    """Contiguous parts of similar length, one per reader, in relay order."""
    cuts = [0] + [_boundary(text, round(len(text) * i / len(readers))) for i in range(1, len(readers))] + [len(text)]
    cuts = [max(c, cuts[i - 1]) if i else c for i, c in enumerate(cuts)]
    sections = {role: text[cuts[i] : cuts[i + 1]].strip() for i, role in enumerate(readers)}
    return Split(sections, [], "contiguous")


def split_contract(text: str, readers: tuple[str, ...], family: str) -> Split:
    """With at least three numbered headings, or three headings alone on a line in the body of the text (as in ToS),
    the split follows the headings. Otherwise the parts are contiguous: the addresses and signatures of a letter do not
    count."""
    headings = find_headings(text)
    numbered = [h for h in headings if h.numbered]
    in_body = [h for h in headings if not h.numbered and 0.15 * len(text) < h.position < 0.85 * len(text)]
    if len(numbered) < 3 and len(in_body) < 3:
        return _contiguous(text, readers)
    fallback = LEGAL if LEGAL in readers else readers[0]
    clauses = [Clause(0, "(preamble)", fallback)] if headings[0].position > 0 else []
    clauses += [
        Clause(
            h.position,
            h.text,
            role_of_heading(h.text, family, readers) or fallback,
        )
        for h in headings
    ]
    pieces: dict[str, list[str]] = {role: [] for role in readers}
    for clause, following in zip(clauses, clauses[1:] + [None]):
        end = following.start if following else len(text)
        piece = text[clause.start : end].strip()
        if piece:
            pieces[clause.role].append(piece)
    return Split({role: "\n\n[…]\n\n".join(p) for role, p in pieces.items()}, clauses, "headings")
