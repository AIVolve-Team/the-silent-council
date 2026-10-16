"""Check the council's demo set and compute its hash.

Each contract is a `<name>.txt` file in `demo-set/`, next to its expected answer `<name>.json` in the format of
"Verdict and dissent": the recommendation, the 19 CUAD rows, the expected dissent and the amounts and dates the
verdict must report correctly. The set stays out of the repo until delivery; only `demo-set.sha256` goes in the
repo, written with --hash after a team member has reviewed the set.
"""

import argparse
import hashlib
import json
from pathlib import Path

from categories import CUAD_CATEGORIES

HERE = Path(__file__).resolve().parent
FOLDER = HERE / "demo-set"
MANIFEST = HERE / "demo-set.sha256"
RECOMMENDATIONS = {"sign", "negotiate", "do not sign"}
POSITIONS = {"yes", "no"}


def errors(answer: dict, text: str) -> list[str]:
    """The errors of an expected answer against its contract; an empty list if it is valid."""
    found = []
    if answer.get("recommendation") not in RECOMMENDATIONS:
        found.append(f"invalid recommendation: {answer.get('recommendation')!r}")
    if not answer.get("rationale"):
        found.append("the recommendation has no rationale")
    rows = answer.get("rows", [])
    if [r.get("category") for r in rows] != list(CUAD_CATEGORIES):
        found.append("the rows must be the 19 CUAD categories, in the order of categories.py")
    for row in rows:
        category = row.get("category")
        if CUAD_CATEGORIES.get(category) != row.get("role"):
            found.append(f"{category}: role {row.get('role')!r} differs from categories.py")
        if row.get("should_flag") is True:
            if not row.get("quote") or row["quote"] not in text:
                found.append(f"{category}: the quote does not appear in the contract")
            if not row.get("rationale"):
                found.append(f"{category}: the rationale is missing")
        elif row.get("should_flag") is False:
            if row.get("quote") is not None:
                found.append(f"{category}: a 'no' row must not have a quote")
        else:
            found.append(f"{category}: should_flag must be true or false")
    for dissent in answer.get("expected_dissent", []):
        category = dissent.get("category")
        if category not in CUAD_CATEGORIES or CUAD_CATEGORIES[category] != dissent.get("role"):
            found.append(f"expected dissent: invalid category or role ({category})")
            continue
        note, verdict = dissent.get("expected_note"), dissent.get("expected_verdict")
        if {note, verdict} != POSITIONS:
            found.append(f"expected dissent on {category}: note and verdict must be one 'yes' and one 'no'")
            continue
        if dissent.get("type") != ("major" if note == "yes" else "minor"):
            found.append(
                f"expected dissent on {category}: 'major' if the note says yes and the verdict no, else 'minor'"
            )
        # The dissent is plausible even when it gets the verdict wrong: the row says who is right.
        correct = {r["category"]: r["should_flag"] for r in rows}.get(category)
        if dissent.get("who_is_right") != ("expert" if (note == "yes") == correct else "verdict"):
            found.append(f"expected dissent on {category}: 'who_is_right' does not match the correct answer")
        if not dissent.get("why"):
            found.append(f"expected dissent on {category}: the why is missing")
    for value in answer.get("amounts_and_dates", []):
        if value not in text:
            found.append(f"amount or date that does not appear in the contract: {value!r}")
    return found


def contracts() -> list[Path]:
    return sorted(FOLDER.glob("*.txt"))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--hash", action="store_true", help="write demo-set.sha256 (after the review)")
    args = parser.parse_args()

    if not contracts():
        raise SystemExit(f"No contracts in {FOLDER}.")
    total = 0
    for contract in contracts():
        answer = json.loads(contract.with_suffix(".json").read_text())
        problems = errors(answer, contract.read_text())
        total += len(problems)
        flagged = sum(r["should_flag"] for r in answer["rows"])
        print(f"{contract.stem}: {answer['recommendation']}, {flagged}/19 to flag, status: {answer['status']}")
        for problem in problems:
            print(f"  - {problem}")
    if total:
        raise SystemExit(f"{total} problems to fix.")
    if args.hash:
        lines = [
            f"{hashlib.sha256(f.read_bytes()).hexdigest()}  {FOLDER.name}/{f.name}"
            for f in sorted(FOLDER.iterdir())
            if f.suffix in {".txt", ".json"}
        ]
        MANIFEST.write_text("\n".join(lines) + "\n")
        print(f"Wrote {MANIFEST.name}: check it with `shasum -a 256 -c {MANIFEST.name}`.")


if __name__ == "__main__":
    main()
