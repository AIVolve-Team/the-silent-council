"""From the council's review to the view for the verdict page, with the rules of “Verdict and dissent”.

- At the top the recommendation; then the rows of all the categories, with quote, rationale and confidence.
- The major dissent with a confident expert (high confidence) is always highlighted; the others open with a click.
- The seal is intact if the chain was delivered and verified; otherwise the page shows the red notice.

Usage: python -m review.view results/<run>.jsonl --contract <id> --title "..." --output view.json
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from .categories import BENCHMARK, Benchmark
from .confidence import level

NAMES = {"legal": "Legal", "finance": "Finance", "risk": "Risk", "rapporteur": "Rapporteur"}
PAGE = Path(__file__).resolve().parents[1] / "page" / "verdict.html"
# The visual checks: their style and script enter the page only when the view has them, so every other
# page stays byte for byte what it was.
VISUAL_CSS = PAGE.with_name("visual.css")
VISUAL_JS = PAGE.with_name("visual.js")
_PLACEHOLDER = '<script id="data" type="application/json">null</script>'
_STYLE_END = "</style>"
_BODY_END = "</script>\n</body>"
EVIDENCE_CUT = 400


def page(view_: dict) -> str:
    """The verdict page with the view inside: a single file, to open or attach."""
    html = PAGE.read_text()
    assert html.count(_PLACEHOLDER) == 1
    data = json.dumps(view_, ensure_ascii=False).replace("</", "<\\/")
    # Neither close the script nor open a comment in it: after "<!--" a "<script" would swallow the rest of the page.
    data = data.replace("<!--", "<\\u0021--")
    html = html.replace(_PLACEHOLDER, f'<script id="data" type="application/json">{data}</script>')
    section = visual_section(view_.get("visual"))
    if section is None:
        return html
    assert html.count(_STYLE_END) == 1 and html.count(_BODY_END) == 1
    code = VISUAL_JS.read_text()
    assert "</" not in code
    # Every "<" escaped: the model's texts cannot close the script or open a comment inside it.
    texts = json.dumps(section, ensure_ascii=False).replace("<", "\\u003c")
    html = html.replace(_STYLE_END, VISUAL_CSS.read_text() + _STYLE_END)
    return html.replace(
        _BODY_END,
        f'</script>\n<script id="visual" type="application/json">{texts}</script>\n<script>\n{code}</script>\n</body>',
    )


# --- The visual checks: the inspector's signals and the answers on the pages, in plain words ---

_WORDS = {
    "it": {
        "title": "Controlli visivi",
        "why": "Perché il PDF è complesso",
        "page": "pagina",
        "pages": lambda ns: ("pagina " if len(ns) == 1 else "pagine ") + _join(ns, "e"),
        "kind": {
            "scanned": "pagina scansionata",
            "image": "immagine",
            "signature_field": "campo firma",
            "annotation": "annotazione",
            "drawing": "disegno o tratto a mano",
            "hidden_text": "testo nascosto",
        },
        "route_visual": lambda ns: (
            f"Il Consiglio ha guardato come immagine la pagina {ns[0]}."
            if len(ns) == 1
            else f"Il Consiglio ha guardato come immagini le pagine {_join(ns, 'e')}."
        ),
        "route_off": "Il Consiglio ha letto solo il testo visibile: la modalità visiva era spenta.",
        "route_text": "Il Consiglio ha letto solo il testo visibile: nessuna pagina andava guardata come immagine.",
        "hidden_removed": lambda ps: f"Il testo nascosto{f' ({ps})' if ps else ''} è stato tolto prima della lettura.",
        "hidden_none": "Nel PDF non c'era testo nascosto.",
        "checks": "Le domande sulle pagine",
        "no_answer": "Nessuna risposta.",
        "unknown": "Dalle pagine non si può dire con certezza.",
        "no_objects": "Nessun oggetto indicato.",
        "type": {
            "signature": "firma",
            "unsigned_signature_block": "spazio per la firma non firmato",
            "initials": "sigla",
            "missing_initials": "sigla mancante",
            "stamp": "timbro",
            "handwritten_correction": "correzione a mano",
            "handwritten_note": "nota a mano",
            "checkbox": "casella",
            "table": "tabella",
            "logo": "logo",
        },
        "rows": ("in alto", "a metà pagina", "in basso"),
        "columns": ("a sinistra", "al centro", "a destra"),
        "centre": "al centro",
    },
    "en": {
        "title": "Visual checks",
        "why": "Why the PDF is complex",
        "page": "page",
        "pages": lambda ns: ("page " if len(ns) == 1 else "pages ") + _join(ns, "and"),
        "kind": {
            "scanned": "scanned page",
            "image": "image",
            "signature_field": "signature field",
            "annotation": "annotation",
            "drawing": "drawing or hand stroke",
            "hidden_text": "hidden text",
        },
        "route_visual": lambda ns: (
            f"The council looked at page {ns[0]} as an image."
            if len(ns) == 1
            else f"The council looked at pages {_join(ns, 'and')} as images."
        ),
        "route_off": "The council read only the visible text: the visual mode was off.",
        "route_text": "The council read only the visible text: no page needed to be seen as an image.",
        "hidden_removed": lambda ps: f"The hidden text{f' ({ps})' if ps else ''} was removed before reading.",
        "hidden_none": "The PDF had no hidden text.",
        "checks": "The questions on the pages",
        "no_answer": "No answer.",
        "unknown": "The pages do not say for sure.",
        "no_objects": "No object pointed out.",
        "type": {
            "signature": "signature",
            "unsigned_signature_block": "unsigned signature block",
            "initials": "initials",
            "missing_initials": "missing initials",
            "stamp": "stamp",
            "handwritten_correction": "handwritten correction",
            "handwritten_note": "handwritten note",
            "checkbox": "checkbox",
            "table": "table",
            "logo": "logo",
        },
        "rows": ("top", "middle", "bottom"),
        "columns": ("left", "centre", "right"),
        "centre": "centre",
    },
}
# The kinds whose detail is a label read in the PDF (the name of a field, the text of a note): worth showing.
_LABELLED = ("signature_field", "annotation")


def _join(items: list, word: str) -> str:
    items = [str(i) for i in items]
    return items[0] if len(items) == 1 else f"{', '.join(items[:-1])} {word} {items[-1]}"


def _third(a: float, b: float) -> int:
    """0, 1 or 2: the third of the page (0-1000) where the centre of the span falls."""
    centre = min(max((a + b) / 2, 0), 1000)
    return 0 if centre < 1000 / 3 else 1 if centre < 2000 / 3 else 2


def position(page_: object, box: object, language: str = "it") -> str:
    """Where an object is, in words: 'page 6, bottom left' from box_2d [ymin, xmin, ymax, xmax] on 0-1000."""
    w = _WORDS[language]
    where = f"{w['page']} {page_}" if isinstance(page_, int) and not isinstance(page_, bool) else ""
    numbers = isinstance(box, list | tuple) and len(box) == 4
    numbers = numbers and all(isinstance(x, int | float) and not isinstance(x, bool) for x in box)
    if not numbers:
        return where
    row, column = _third(box[0], box[2]), _third(box[1], box[3])
    # The middle of the page is just "centre", not "middle centre".
    words = w["centre"] if (row, column) == (1, 1) else f"{w['rows'][row]} {w['columns'][column]}"
    return f"{where}, {words}" if where else words


def _text(x: object) -> str:
    return x.strip() if isinstance(x, str) else ""


def _object_line(o: dict, language: str) -> str:
    w = _WORDS[language]
    kind = _text(o.get("type"))
    name = w["type"].get(kind, kind.replace("_", " ")) or "?"
    where = position(o.get("page"), o.get("box_2d"), language)
    line = f"{name[:1].upper()}{name[1:]}" + (f", {where}" if where else "")
    text = _text(o.get("text"))
    return f"{line}: “{text}”" if text else line


def _section(visual: dict, language: str) -> dict:
    w = _WORDS[language]
    signals = [s for s in visual.get("signals") or [] if isinstance(s, dict)]
    by_page: dict[object, list[str]] = {}
    for s in signals:
        kind = _text(s.get("kind"))
        words = w["kind"].get(kind, kind.replace("_", " "))
        detail = _text(s.get("detail"))
        if kind in _LABELLED and detail:
            words = f"{words} “{detail}”"
        if words not in by_page.setdefault(s.get("page"), []):
            by_page[s.get("page")].append(words)
    numbers = sorted(p for p in by_page if isinstance(p, int))
    why = [f"{w['page']} {p}: {', '.join(by_page[p])}" for p in numbers]
    why += [", ".join(ws) for p, ws in by_page.items() if not isinstance(p, int)]

    pages = [p for p in visual.get("visual_pages") or [] if isinstance(p, int)]
    if visual.get("route") == "visual" and pages:
        route = w["route_visual"](pages)
    elif visual.get("visual_mode") == "off":
        route = w["route_off"]
    else:
        route = w["route_text"]
    hidden = sorted(
        {s.get("page") for s in signals if s.get("kind") == "hidden_text" and isinstance(s.get("page"), int)}
    )
    if visual.get("hidden_text_removed"):
        hidden_line = w["hidden_removed"](hidden and w["pages"](hidden))
    else:
        hidden_line = w["hidden_none"]

    checks = []
    for c in visual.get("checks") or []:
        if not isinstance(c, dict) or not _text(c.get("question")):
            continue
        # The service writes the answer's fields on the check itself ({section, question, answer, objects, known});
        # a check that carries the council's answer whole ({answer, objects, known}) reads the same.
        answer = c["answer"] if isinstance(c.get("answer"), dict) else c
        objects = [o for o in answer.get("objects") or [] if isinstance(o, dict)]
        text = _text(answer.get("answer"))
        known = c.get("known") is True and answer.get("known") is not False
        checks.append(
            {
                "question": _text(c["question"]),
                "answer": text or w["no_answer"],
                "unknown": None if known or not text else w["unknown"],
                "objects": [_object_line(o, language) for o in objects],
            }
        )
    return {
        "title": w["title"],
        "why_title": w["why"],
        "why": why,
        "route": route,
        "hidden": hidden_line,
        "checks_title": w["checks"],
        "checks": checks,
    }


def visual_section(visual: object) -> dict | None:
    """The texts of the 'Visual checks' section in both languages (the reader switches language on the page), or None
    when the view has no complex PDF behind it: text contracts and simple PDFs keep their page as it was."""
    if not isinstance(visual, dict) or not visual.get("complex"):
        return None
    return {language: _section(visual, language) for language in _WORDS}


def _level(written: dict | None, key: str) -> str | None:
    if not written or not written.get("data"):
        return None
    p = written["p_yes"].get(key)
    position = written["data"]["flag"].get(key)
    return None if p is None or position is None else level(p, position)


def _note_quotes(note: dict) -> dict[str, tuple[str, bool]]:
    if not note.get("data"):
        return {}
    found = note.get("quotes_found", {})
    return {q["category"]: (q["text"], found.get(q["category"], False)) for q in note["data"]["quotes"]}


def _experts(answer: dict | None, flag: bool | None) -> dict | None:
    if answer is None:
        return None
    return {
        "should_flag": answer["should_flag"],
        "agrees": None if flag is None else flag == answer["should_flag"],
        # At most two annotated spans, cut: they are enough to show where to look.
        "evidence": [e if len(e) <= EVIDENCE_CUT else e[:EVIDENCE_CUT].rstrip() + "…" for e in answer["evidence"][:2]],
    }


def view(
    review: dict,
    benchmark: Benchmark,
    title: str,
    *,
    experts: dict[str, dict] | None = None,
    source: dict | None = None,
) -> dict:
    """`experts` (category → {"should_flag", "evidence"}) and `source` ({"name", "link"}) only for the judges' site
: each row also says what the dataset's experts answered. The client business does not have them."""
    names = {c.key: c.name_it for c in benchmark.categories}
    verdict = review.get("verdict")
    data = verdict["data"] if verdict else None
    details = {d["category"]: d for d in (data or {}).get("details", [])}
    found = (verdict or {}).get("quotes_found", {})
    dissents = {d["category"]: d for d in review["dissents"]}
    notes = review["notes"]

    rows = []
    for category in benchmark.categories:
        detail = details.get(category.key, {})
        dissent = dissents.get(category.key)
        flag = None if data is None else data["flag"].get(category.key)
        row = {
            "key": category.key,
            "name_it": category.name_it,
            "role": category.role,
            "flag": flag,
            "confidence": _level(verdict, category.key),
            "quote": detail.get("quote"),
            "quote_found": found.get(category.key) if detail else None,
            "rationale": detail.get("rationale"),
            "dissent": None,
            "experts": _experts((experts or {}).get(category.key), flag),
        }
        if dissent:
            quote, quote_found = _note_quotes(notes.get(dissent["role"], {})).get(category.key, (None, None))
            row["dissent"] = {
                "type": dissent["type"],
                "role": dissent["role"],
                "role_name": NAMES[dissent["role"]],
                "expert_says": dissent["type"] == "major",
                "expert_confidence": dissent["expert_confidence"],
                "verdict_confidence": dissent["verdict_confidence"],
                "expert_quote": quote,
                "expert_quote_found": quote_found,
                # the major dissent with a confident expert is always visible.
                "highlighted": dissent["type"] == "major" and dissent["expert_confidence"] == "high",
            }
        rows.append(row)

    notes_view = []
    for role in benchmark.readers:
        note = notes.get(role)
        if note is None:
            continue
        quotes = _note_quotes(note)
        notes_view.append(
            {
                "role": role,
                "name": NAMES[role],
                "valid": note.get("data") is not None,
                "rows": [
                    {
                        "key": c.key,
                        "name_it": c.name_it,
                        "flag": (note.get("data") or {}).get("flag", {}).get(c.key),
                        "confidence": _level(note, c.key),
                    }
                    for c in benchmark.of_role(role)
                ],
                "quotes": [
                    {"key": k, "name_it": names.get(k, k), "text": t, "found": f} for k, (t, f) in quotes.items()
                ],
                "amounts_dates_parties": (note.get("data") or {}).get("amounts_dates_parties", []),
            }
        )

    compared = [r for r in rows if r["experts"] and r["experts"]["agrees"] is not None]
    # The strict count: agreement alone is high even for whoever always answers "nothing", because the clauses that are
    # present are few. A clause without an answer from the council (missing verdict) counts as not found.
    to_find = [r for r in rows if r["experts"] and r["experts"]["should_flag"]]
    stopped = review.get("stopped")
    return {
        "title": title,
        "contract": review["contract"],
        "benchmark": review["benchmark"],
        "mode": review["mode"],
        "model": review["model"],
        "latent_steps": review.get("latent_steps"),
        "recommendation": None if data is None else {"value": data["recommendation"], "rationale": data["rationale"]},
        "objections": [
            {"key": o["category"], "name_it": names.get(o["category"], o["category"]), "objection": o["objection"]}
            for o in (data or {}).get("objections", [])
        ],
        "seal": {
            "intact": stopped is None and bool(review["fingerprints"]),
            "messages": len(review["fingerprints"]),
            "fingerprints": review["fingerprints"],
            "check": None if stopped is None else stopped["check"],
            "reason": None if stopped is None else stopped["reason"],
        },
        "rows": rows,
        "comparison": None
        if experts is None
        else {
            **(source or {}),
            "agreed": sum(r["experts"]["agrees"] for r in compared),
            "compared": len(compared),
            "found": sum(r["flag"] is True for r in to_find),
            "to_find": len(to_find),
        },
        "notes": notes_view,
        "cost": {
            "tokens_generated": review["tokens_generated"],
            "tokens_read": review["tokens_read"],
            "latent_positions": review["latent_positions"],
            "seconds": round(review["seconds"], 1),
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Exports the view of a review for the verdict page.")
    parser.add_argument("run", type=Path, help=".jsonl file written by review.run")
    parser.add_argument("--contract", required=True)
    parser.add_argument("--title")
    parser.add_argument("--output", type=Path, default=Path("view.json"))
    parser.add_argument("--html", type=Path, help="also writes the verdict page with the data inside, in a single file")
    args = parser.parse_args()
    reviews = [json.loads(r) for r in args.run.open()]
    review = next(r for r in reviews if r["contract"] == args.contract)
    result = view(review, BENCHMARK[review["benchmark"]], args.title or args.contract)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    print(f"Written {args.output}")
    if args.html:
        args.html.write_text(page(result))
        print(f"Written {args.html}")


if __name__ == "__main__":
    main()
