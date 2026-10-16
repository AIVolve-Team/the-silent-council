"""The blind manual check of the demo set.

The checker has neither written nor reviewed the expected answers, does not open their `.json` files and does
not know which verdict comes from text and which from telepathy. They receive the contracts and one sheet per verdict,
with neutral names and in shuffled order: recommendation, flagged clauses, objections and dissents. No mode, tokens,
times or thoughts.

    python -m review.blind prepare eval --output blind
        blind/for-the-checker/verdict-01.md …, sheet.csv     to give to the checker, with the contracts
        blind/key.json                                      stays with the organizer
    python -m review.blind count blind/for-the-checker/sheet.csv blind/key.json
"""

from __future__ import annotations

import argparse
import csv
import json
import random
from pathlib import Path

from .categories import BENCHMARK
from .metrics import NAMES

BLIND = ("text", "telepathy")
SEED = 31
COLUMNS = ("verdict", "contract", "right_recommendation", "expected_dissent_found", "right_amounts", "notes")
JUDGEMENTS = ("right_recommendation", "expected_dissent_found", "right_amounts")
ROLES = {"legal": "legal", "finance": "finance", "risk": "risk"}


def sheet(number: str, review: dict) -> str:
    """The sheet of a verdict, with nothing that tells how it was made."""
    benchmark = BENCHMARK[review["benchmark"]]
    roles = {c.key: c.role for c in benchmark.categories}
    data = (review.get("verdict") or {}).get("data")
    lines = [f"# Verdict {number}", "", f"Contract: `{review['contract']}`", ""]
    if data is None:
        return "\n".join([*lines, "The council did not give a valid verdict.", ""])
    lines += [f"## Recommendation: {data['recommendation']}", "", data.get("rationale") or "", ""]
    details = {d["category"]: d for d in data.get("details", [])}
    flagged = [k for k, yes in data["flag"].items() if yes]
    lines += ["## Flagged clauses", ""]
    for k in flagged:
        d = details.get(k, {})
        quote = f": «{d['quote']}»" if d.get("quote") else ""
        reason = f" ({d['rationale']})" if d.get("rationale") else ""
        lines.append(f"- **{k}**{quote}{reason}")
    lines += ["" if flagged else "None.", ""]
    if data.get("objections"):
        lines += ["## Objections", ""] + [f"- **{o['category']}**: {o['objection']}" for o in data["objections"]]
        lines.append("")
    lines += ["## Dissents between experts and verdict", ""]
    for d in review.get("dissents", []):
        expert = "it should be flagged" if d["type"] == "major" else "it should not be flagged"
        verdict = "no" if d["type"] == "major" else "yes"
        role = ROLES.get(d.get("role") or roles.get(d["category"]), d.get("role"))
        lines.append(f"- **{d['category']}**: for the {role} expert {expert}, the verdict says {verdict}.")
    lines += ["" if review.get("dissents") else "None.", ""]
    return "\n".join(lines)


def prepare(folder: Path, output: Path, *, seed: int = SEED) -> int:
    items = []
    for configuration in BLIND:
        f = folder / f"demo-dev-{configuration}.jsonl"
        if not f.exists():
            raise SystemExit(f"{f} is missing: the text and telepathy runs on the demo set are needed.")
        items += [(configuration, json.loads(r)) for r in f.read_text().splitlines() if r.strip()]
    random.Random(seed).shuffle(items)
    for_checker = output / "for-the-checker"
    for_checker.mkdir(parents=True, exist_ok=True)
    key, rows = {}, []
    for i, (configuration, review) in enumerate(items, 1):
        number = f"{i:02d}"
        (for_checker / f"verdict-{number}.md").write_text(sheet(number, review))
        key[f"verdict-{number}"] = {"contract": review["contract"], "configuration": configuration}
        rows.append({"verdict": f"verdict-{number}", "contract": review["contract"]})
    with (for_checker / "sheet.csv").open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=COLUMNS)
        writer.writeheader()
        writer.writerows(rows)
    (output / "key.json").write_text(json.dumps({"seed": seed, "verdicts": key}, indent=2, ensure_ascii=False))
    return len(items)


def count(sheet_file: Path, key: Path) -> str:
    """Per configuration, how many times the checker wrote "yes" on each judgement, among the filled-in rows."""
    verdicts = json.loads(key.read_text())["verdicts"]
    counts: dict[str, dict[str, list[int]]] = {c: {g: [0, 0] for g in JUDGEMENTS} for c in BLIND}
    with sheet_file.open() as f:
        for row in csv.DictReader(f):
            configuration = verdicts[row["verdict"]]["configuration"]
            for g in JUDGEMENTS:
                value = (row.get(g) or "").strip().lower()
                if value in ("yes", "y", "no", "n"):
                    counts[configuration][g][0] += value not in ("no", "n")
                    counts[configuration][g][1] += 1
    lines = [
        "| Configuration | Right recommendation | Expected dissent found | Right amounts |",
        "|---|---|---|---|",
    ]
    for c in BLIND:
        cells = [f"{a}/{n}" for a, n in (counts[c][g] for g in JUDGEMENTS)]
        lines.append(f"| {NAMES[c]} | " + " | ".join(cells) + " |")
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="The blind manual check.")
    commands = parser.add_subparsers(dest="command", required=True)
    p = commands.add_parser("prepare")
    p.add_argument("folder", type=Path, help="the eval folder with the runs on the demo set")
    p.add_argument("--output", type=Path, default=Path("blind"))
    p.add_argument("--seed", type=int, default=SEED)
    c = commands.add_parser("count")
    c.add_argument("sheet", type=Path)
    c.add_argument("key", type=Path)
    args = parser.parse_args()
    if args.command == "prepare":
        n = prepare(args.folder, args.output, seed=args.seed)
        print(f"{n} sheets in {args.output / 'for-the-checker'}; the key stays in {args.output / 'key.json'}")
    else:
        print(count(args.sheet, args.key))


if __name__ == "__main__":
    main()
