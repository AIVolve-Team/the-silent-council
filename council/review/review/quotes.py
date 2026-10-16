"""Every quote is looked up word for word in the contract.

A quote that is not there is made up: the person sees it flagged, and the strict version of the score does not count
it. The comparison ignores case, whitespace, typographic quotes and apostrophes, and the ellipsis of a cut.
"""

from __future__ import annotations

import re

_REPLACEMENTS = str.maketrans({"’": "'", "‘": "'", "“": '"', "”": '"', "«": '"', "»": '"', "–": "-", "—": "-"})


def normalize(text: str) -> str:
    text = text.translate(_REPLACEMENTS).lower()
    return re.sub(r"\s+", " ", text).strip()


def found(quote: str, contract: str) -> bool:
    """Every piece of the quote (separated by "..." or "…") appears in the contract. Quotes of fewer than three words
    do not count as evidence."""
    pieces = [p.strip(" \"'.,;:") for p in re.split(r"\.{3}|…", normalize(quote))]
    pieces = [p for p in pieces if p]
    if not pieces or sum(len(p.split()) for p in pieces) < 3:
        return False
    text = normalize(contract)
    return all(p in text for p in pieces)


def check(data: dict | None, contract: str) -> dict[str, bool]:
    """Category → the quote of the note or the verdict appears in the contract."""
    if not data:
        return {}
    items = data.get("quotes") or data.get("details") or []
    return {v["category"]: found(v.get("text") or v.get("quote") or "", contract) for v in items}
