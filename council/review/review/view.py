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
_PLACEHOLDER = '<script id="data" type="application/json">null</script>'
EVIDENCE_CUT = 400


def page(view_: dict) -> str:
    """The verdict page with the view inside: a single file, to open or attach."""
    html = PAGE.read_text()
    assert html.count(_PLACEHOLDER) == 1
    data = json.dumps(view_, ensure_ascii=False).replace("</", "<\\/")
    return html.replace(_PLACEHOLDER, f'<script id="data" type="application/json">{data}</script>')


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
