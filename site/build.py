"""Builds the judges' site in `public/`: the home page and the council's pages. Python 3 is enough, without
dependencies: the verdict pages are prepared by `council/review` (view and showcase).

    python3 site/build.py --council <verdict pages> [--repo https://github.com/…]
    cd site && vercel deploy      # with the CLI: the free plan does not link an organization's repos by itself
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
from pathlib import Path

HERE = Path(__file__).resolve().parent
COUNCIL = {
    "id": "council",
    "name": "Silent Council",
    "en": "A council of agents reviews contracts in silence, passing each other their memory, and writes a verdict with "
    "its dissent.",
    "it": "Un consiglio di agenti rivede i contratti in silenzio, passandosi la memoria, e scrive un verdetto con il suo "
    "dissenso.",
    "cases": "council/index.html",
    "live": "council/live.html",
}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--council", type=Path, default=None, help="the council's pages")
    parser.add_argument("--repo", default=None, help="the public repo, when it is public")
    parser.add_argument("--output", type=Path, default=HERE / "public")
    a = parser.parse_args()

    if a.output.exists():
        shutil.rmtree(a.output)
    shutil.copytree(HERE / "src", a.output)
    shutil.copy(HERE / "windows.json", a.output / "windows.json")
    projects = []
    if a.council:
        # next to the live review of src/council: index, verdict pages and the showcase's numbers
        shutil.copytree(a.council, a.output / "council", dirs_exist_ok=True)
        # numbers.json (written by review.showcase): the telepathy and text averages for the home page demonstration
        numbers = "council/numbers.json" if (a.output / "council" / "numbers.json").exists() else None
        projects.append(COUNCIL | {"numbers": numbers})
        print(f"Council: pages from {a.council}" + (", with the numbers for the home page" if numbers else ""))
    else:
        shutil.rmtree(a.output / "council")
    (a.output / "projects.json").write_text(
        json.dumps({"projects": projects, "repo": a.repo}, ensure_ascii=False, indent=1)
    )

    # No whole IBAN outside the PDFs: it is the rule of “Case for a person”, and here it is checked on everything that goes online.
    iban = re.compile(r"\b[A-Z]{2}\d{2}(?:\s?[A-Z0-9]){12,30}\b")
    for f in a.output.rglob("*"):
        if f.suffix in (".html", ".json") and iban.search(f.read_text(encoding="utf-8")):
            raise SystemExit(f"whole IBAN in {f.relative_to(a.output)}: not publishing")
    print(f"site in {a.output}")


if __name__ == "__main__":
    main()
