"""The council's part of the judges' site: the index of the contracts and the verdict pages.

    python -m review.showcase --run <telepathy run>.jsonl --run <text run>.jsonl \\
        --recorded "15/10/2026 on the MI300X" --output council-showcase

The output folder is passed to `site/build.py --council <folder>`. The index has the style of the site's home page,
one row per contract with telepathy and text side by side. Index and verdict pages open in English, with the switch
to Italian; `numbers.json` gives the home page the averages for the demonstration.

The demo set stays private until delivery: without `--delivery` its reviews do not go out, because the site is
public.
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

from .categories import BENCHMARK
from .data import demo, expert_answers
from .view import PAGE, page, view

INDEX = Path(__file__).resolve().parents[1] / "page" / "showcase.html"
_PLACEHOLDER = '<script id="data" type="application/json">null</script>'

# Where the contracts and the correct answers come from (data/NOTICE.md): they are not ours, and the judge can check
# them. "who" and "explanation" in both languages of the verdict page.
SOURCES = {
    "cuad": {
        "name": "CUAD",
        "link": "https://github.com/TheAtticusProject/cuad",
        "who": {"it": "gli esperti di CUAD", "en": "the CUAD experts"},
        "explanation": {
            "it": (
                "Il contratto e le risposte giuste vengono da CUAD, un dataset pubblico di contratti veri annotati da "
                "studenti di legge controllati da avvocati (The Atticus Project, NeurIPS 2021). Non li abbiamo scritti noi."
            ),
            "en": (
                "The contract and its right answers come from CUAD, a public dataset of real contracts annotated by law "
                "students under lawyers' supervision (The Atticus Project, NeurIPS 2021). We did not write them."
            ),
        },
    },
    "contractnli": {
        "name": "ContractNLI",
        "link": "https://stanfordnlp.github.io/contract-nli/",
        "who": {"it": "gli esperti di ContractNLI", "en": "the ContractNLI annotators"},
        "explanation": {
            "it": (
                "L'accordo e le risposte giuste vengono da ContractNLI, un dataset pubblico di accordi di riservatezza "
                "veri annotati a mano (Koreeda e Manning, Stanford, EMNLP 2021). Non li abbiamo scritti noi."
            ),
            "en": (
                "The agreement and its right answers come from ContractNLI, a public dataset of real non-disclosure "
                "agreements annotated by hand (Koreeda and Manning, Stanford, EMNLP 2021). We did not write them."
            ),
        },
    },
    "claudette": {
        "name": "CLAUDETTE",
        "link": "https://github.com/lt-nlp-lab-unibo/Multilingual-Unfair-Clause-Detection",
        "who": {"it": "gli esperti di CLAUDETTE", "en": "the CLAUDETTE annotators"},
        "explanation": {
            "it": (
                "Le condizioni d'uso e le risposte giuste vengono da CLAUDETTE, un dataset pubblico di condizioni d'uso "
                "vere annotate a mano da giuristi (Galassi e altri, Artificial Intelligence and Law, 2024). Non le "
                "abbiamo scritte noi."
            ),
            "en": (
                "The terms of service and their right answers come from CLAUDETTE, a public dataset of real terms "
                "annotated by legal scholars (Galassi et al., Artificial Intelligence and Law, 2024). We did not write "
                "them."
            ),
        },
    },
    "demo": {
        "name": "expected answers",
        "link": None,
        "who": {"it": "le risposte attese", "en": "the expected answers"},
        "explanation": {
            "it": (
                "Le risposte attese le abbiamo scritte prima delle prove e bloccate con la loro impronta digitale nel "
                "repo: si può controllare che non siano cambiate dopo."
            ),
            "en": (
                "We wrote the expected answers before the runs and locked them with their fingerprint in the "
                "repository: anyone can check that they did not change afterwards."
            ),
        },
    },
}


class Private(SystemExit):
    """A review of the demo set without `--delivery`."""


def cuad_title(cid: str) -> str:
    """A readable name from the CUAD id, which is the name of the filed document: "PenntexMidstreamPartnersLp_20150416_
    S-1A_EX-10.4_9042833_EX-10.4_Transportation Agreement" becomes "Penntex Midstream Partners Lp: transportation
    agreement". The contract type is the last piece that talks about "agreement"; if there is none, "contract"."""
    date = re.match(r"^(.*?)_(?:\d{2}_\d{2}_\d{4}|\d{8})", cid)
    company = date.group(1) if date else re.split(r" - |_|-", cid, maxsplit=1)[0]
    company = company.replace("_", " ").replace(",", ", ").replace("  ", " ").strip()
    if " " not in company and re.search(r"[a-z]", company):
        company = re.sub(r"(?<=[a-z])(?=[A-Z])", " ", company)  # PenntexMidstreamPartnersLp
    pieces = re.findall(
        r"[A-Za-z][A-Za-z ,.&()_-]*?agreement(?: *\([^)]*\))?", cid.replace(" _ ", " & "), re.IGNORECASE
    )
    if not pieces:
        return f"{company}: contract"
    parts = [x.strip() for x in re.split(r"[-_]", pieces[-1]) if x.strip()]
    kind = parts[-1]
    if len(parts) > 1 and len(parts[-2]) <= 3:
        kind = f"{parts[-2]}-{kind}"  # Co-Branding
    # lower case outside the parentheses, where the proper names stay: "(Hyatt Ziva Cancun)"
    kind = re.sub(r"[^()]+(?=\(|$)", lambda m: m.group(0).lower(), kind, count=1)
    return f"{company}: {kind}"


def title_of(review: dict, texts: dict[str, str]) -> str:
    """For the demo set the subject of the contract (or the first line), as in `trial.sh`; for CUAD a readable name from
    the id; for the others the id."""
    text = texts.get(review["contract"])
    if not text:
        return cuad_title(review["contract"]) if review["benchmark"] == "cuad" else review["contract"]
    lines = [r.strip() for r in text.splitlines() if r.strip()]
    # The demo contracts are Italian: their subject line starts with "Oggetto:".
    subject = next((r.split(":", 1)[1].strip() for r in lines if r.lower().startswith("oggetto:")), None)
    title = subject or lines[0]
    return title[0].upper() + title[1:].lower()


def with_data(template: Path, data: dict) -> str:
    """A page with its data inside, in place of the placeholder: a single file, without requests to the server."""
    html = template.read_text()
    assert html.count(_PLACEHOLDER) == 1
    text = json.dumps(data, ensure_ascii=False).replace("</", "<\\/")
    return html.replace(_PLACEHOLDER, f'<script id="data" type="application/json">{text}</script>')


def file_name(prefix: str, review: dict, *pieces: str) -> str:
    file = "-".join([prefix, review["benchmark"], review["contract"][:50].rstrip("-_. "), *pieces]) + ".html"
    return file.replace("/", "_").replace(" ", "_")


def entry(review: dict, v: dict, file: str) -> dict:
    """What the index shows of a verdict: no sentences of the contract, only counts and recommendation."""
    rows = v["rows"]
    return {
        "title": v["title"],
        "contract": review["contract"],
        "benchmark": review["benchmark"],
        "mode": review["mode"],
        "recommendation": (v["recommendation"] or {}).get("value"),
        "flagged": sum(bool(r["flag"]) for r in rows),
        "categories": len(rows),
        "major_dissents": sum(bool(r["dissent"]) and r["dissent"]["type"] == "major" for r in rows),
        "minor_dissents": sum(bool(r["dissent"]) and r["dissent"]["type"] == "minor" for r in rows),
        "seal_intact": v["seal"]["intact"],
        "source": (v["comparison"] or {}).get("name"),
        "agreed": (v["comparison"] or {}).get("agreed"),
        "compared": (v["comparison"] or {}).get("compared"),
        "found": (v["comparison"] or {}).get("found"),
        "to_find": (v["comparison"] or {}).get("to_find"),
        "tokens_generated": review["tokens_generated"],
        "seconds": round(review["seconds"]),
        "model": review["model"],
        "page": file,
    }


def numbers(reviews: list[dict], views: list[dict], recorded: str | None) -> dict | None:
    """The per-contract averages of telepathy and text for the home page demonstration: tokens written and read,
    seconds and the strict count of the clauses found. Only on the contracts done in both modes, and on a benchmark
    with the answers of external experts (CUAD first of all): we wrote the demo set ourselves."""
    for benchmark in ("cuad", "contractnli", "claudette"):
        pairs = {(r["contract"], r["mode"]): (r, v) for r, v in zip(reviews, views) if r["benchmark"] == benchmark}
        contracts = sorted({c for c, m in pairs if m == "telepathy"} & {c for c, m in pairs if m == "text"})
        if not contracts:
            continue
        averages = {}
        for mode in ("telepathy", "text"):
            chosen = [pairs[(c, mode)] for c in contracts]
            comparisons = [v["comparison"] for _, v in chosen if v["comparison"]]
            averages[mode] = {
                "tokens_generated": round(sum(r["tokens_generated"] for r, _ in chosen) / len(chosen)),
                "tokens_read": round(sum(r["tokens_read"] for r, _ in chosen) / len(chosen)),
                "seconds": round(sum(r["seconds"] for r, _ in chosen) / len(chosen), 1),
                "found": sum(c["found"] for c in comparisons),
                "to_find": sum(c["to_find"] for c in comparisons),
            }
        models = sorted({pairs[(c, m)][0]["model"] for c in contracts for m in ("telepathy", "text")})
        return {
            "recorded": recorded,
            "benchmark": benchmark,
            "source": SOURCES[benchmark]["name"],
            "model": ", ".join(models),
            "contracts": len(contracts),
            **averages,
        }
    return None


def demo_expected() -> tuple[dict[str, str], dict[str, dict]]:
    """Texts and expected answers of the demo set: the answers in the format of `expert_answers`, with the expected
    quote as the marked span."""
    texts, expected = {}, {}
    for cid, text, answer in demo():
        texts[cid] = text
        expected[cid] = {
            row["category"]: {
                "should_flag": row["should_flag"],
                "evidence": [row["quote"]] if row.get("quote") else [],
            }
            for row in answer["rows"]
        }
    return texts, expected


def write_showcase(runs: list[Path], output: Path, *, recorded: str | None, delivery: bool = False) -> int:
    reviews = [json.loads(r) for run in runs for r in run.read_text().splitlines() if r.strip()]
    if not delivery and any(r["benchmark"] == "demo" for r in reviews):
        raise Private(
            "The demo set stays private until delivery and the site is public: "
            "remove those runs, or add --delivery at delivery time."
        )
    keys = [(r["benchmark"], r["contract"], r["mode"]) for r in reviews]
    if len(set(keys)) < len(keys):
        # For example two telepathy runs with different steps: the pages would overwrite each other and the averages
        # would mix.
        raise SystemExit("The same contract appears twice in the same mode: pass a single run per mode.")
    texts, expected = demo_expected() if any(r["benchmark"] == "demo" for r in reviews) else ({}, {})
    output.mkdir(parents=True, exist_ok=True)
    entries, views = [], []
    for r in reviews:
        experts = (expected if r["benchmark"] == "demo" else expert_answers(r["benchmark"])).get(r["contract"])
        source = SOURCES[r["benchmark"]] if experts else None
        v = view(r, BENCHMARK[r["benchmark"]], title_of(r, texts), experts=experts, source=source)
        # On the judges' site the page opens in English (the reader can switch to Italian) and goes back to the index.
        file = file_name("verdict", r, r["mode"])
        v |= {"language": "en", "index": "index.html"}
        (output / file).write_text(page(v))
        entries.append(entry(r, v, file))
        views.append(v)
    # The empty page, for the judge's live reviews: the site opens it with the view saved in its browser.
    (output / "verdict.html").write_text(PAGE.read_text())
    averages = numbers(reviews, views, recorded)
    if averages:
        (output / "numbers.json").write_text(json.dumps(averages, ensure_ascii=False, indent=1) + "\n")
    (output / "index.html").write_text(with_data(INDEX, {"recorded": recorded, "verdicts": entries}))
    return len(entries)


def main() -> None:
    parser = argparse.ArgumentParser(description="The council's part of the judges' site.")
    parser.add_argument("--run", type=Path, action="append", required=True, help="a .jsonl of recorded reviews")
    parser.add_argument("--recorded", default=None, help='for example "15/10/2026 on the MI300X"')
    parser.add_argument("--delivery", action="store_true", help="only at delivery: also publishes the demo set")
    parser.add_argument("--output", type=Path, default=Path("council-showcase"))
    args = parser.parse_args()
    n = write_showcase(args.run, args.output, recorded=args.recorded, delivery=args.delivery)
    print(f"{n} verdicts in {args.output}: pass it to site/build.py --council {args.output}")


if __name__ == "__main__":
    main()
