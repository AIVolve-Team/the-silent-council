"""The council's calibration on the dev set: how many latent steps and which confidence thresholds.

Reads the runs of `review.run` with several step values (for example `--steps 0 10 20 40`) and writes the tables to
paste into the ticket, with aggregate numbers only.

Usage:
    python -m review.calibration results --benchmark cuad
"""

from __future__ import annotations

import argparse
import json
import re
from itertools import pairwise
from pathlib import Path

from .run import _contracts_and_answers
from .scoring import agreement, score

# The steps to choose from: 10, 20 and 40 of “Pre-registered eval”, and 0, which is its early check of the thoughts. With the same tie
# rule, 0 wins only if no value with thoughts beats it by at least 1 point: then the thoughts do not help and the
# system is corrected before the freeze, as “Pre-registered eval” allows (PREREGISTRAZIONE.md).
CANDIDATES = (0, 10, 20, 40)
TIE = 1.0
# The thresholds are proposed on a grid: the confidence is the probability of the chosen position, between 0.5 and 1.
GRID = (0.6, 0.7, 0.8, 0.85, 0.9, 0.95, 0.99)
CORRECT_HIGH, CORRECT_MEDIUM = 0.9, 0.7

_NAME = re.compile(
    r"^(?P<benchmark>[a-z]+)-dev-(?P<mode>telepathy|text)-m(?P<steps>\d+)-(?P<model>.+?)(?P<no_realign>-no-realign)?$"
)


def choose_steps(f1: dict[int, float]) -> int:
    """The highest F1 among 0, 10, 20 and 40 wins; under 1 point of difference the value with fewer steps wins."""
    candidates = [m for m in CANDIDATES if m in f1]
    if not candidates:
        raise ValueError("the runs with 0, 10, 20 or 40 steps are needed")
    best = max(f1[m] for m in candidates)
    return min(m for m in candidates if best - f1[m] < TIE)


def decisions(reviews: list[dict], correct: dict) -> list[tuple[float, bool]]:
    """(confidence of the chosen position, correct) for every yes/no of the verdict and of the notes."""
    out = []
    for r in reviews:
        written = [r.get("verdict")] + list((r.get("notes") or {}).values())
        for w in written:
            if not w or not w.get("data"):
                continue
            for category, yes in w["data"]["flag"].items():
                p = w.get("p_yes", {}).get(category)
                right = correct.get((r["contract"], category))
                if p is not None and right is not None:
                    out.append((p if yes else 1 - p, yes == right))
    return out


def propose_thresholds(items: list[tuple[float, bool]]) -> tuple[float, float] | None:
    """A proposal, to be reviewed: "high" is the lowest threshold of the grid above which the model is right at least
    9 times out of 10; "medium" the lowest under "high" between which and "high" it is right at least 7 times out of
    10."""

    def share(inside: list[bool]) -> float:
        return sum(inside) / len(inside) if inside else 0.0

    highs = [
        t for t in GRID if share([g for c, g in items if c >= t]) >= CORRECT_HIGH and any(c >= t for c, _ in items)
    ]
    if not highs:
        return None
    high = min(highs)
    mediums = [
        t
        for t in GRID
        if t < high
        and share([g for c, g in items if t <= c < high]) >= CORRECT_MEDIUM
        and any(t <= c < high for c, _ in items)
    ]
    return high, min(mediums) if mediums else high


def _n(x: float, digits: int = 1) -> str:
    return f"{x:.{digits}f}"


def report(folder: Path, benchmark: str) -> str:
    groups: dict[tuple[str, bool], dict[str, dict[int, list[dict]]]] = {}
    for f in sorted(folder.glob(f"{benchmark}-dev-*.jsonl")):
        name = _NAME.match(f.stem)
        if not name:
            continue
        rows = [json.loads(r) for r in f.read_text().splitlines() if r.strip()]
        key = (name["model"], not name["no_realign"])
        groups.setdefault(key, {}).setdefault(name["mode"], {})[int(name["steps"])] = rows
    if not groups:
        return f"No dev runs of {benchmark} in {folder}."
    _, correct = _contracts_and_answers(benchmark, "dev")
    if not correct:
        raise SystemExit(f"The correct answers of {benchmark} are missing: for the demo set see COUNCIL_DEMO_SET.")
    parts = [f"# Calibration on {benchmark}, dev set", ""]
    for (model, realign), modes in groups.items():
        parts += [f"## {model}, realignment {'on' if realign else 'off'}", ""]
        parts += [
            "| Mode | Steps | Contracts | F1 | MCC | Notes as verdict | Notes-verdict agreement |",
            "|---|---|---|---|---|---|---|",
        ]
        for mode_name, runs in sorted(modes.items()):
            for steps, rows in sorted(runs.items()):
                s = score(rows, correct)
                same, compared = agreement(rows)
                parts.append(
                    f"| {mode_name} | {steps} | {len(rows)} | {_n(s.f1)} | {_n(s.mcc, 2)} | "
                    f"{_n(score(rows, correct, from_notes=True).f1)} | {same}/{compared} |"
                )
        parts.append("")
        telepathy = modes.get("telepathy", {})
        f1 = {m: score(r, correct).f1 for m, r in telepathy.items()}
        if any(m in f1 for m in CANDIDATES):
            chosen = choose_steps(f1)
            parts.append(f"**Chosen steps:** {chosen} (F1 {_n(f1[chosen])}), with the rule of “Pre-registered eval”.")
            if chosen == 0:
                parts.append(
                    "With the thoughts the F1 does not rise by at least 1 point: on the dev set the thoughts do not "
                    "help. Per “Pre-registered eval” the system is corrected before the freeze: 0 steps, no tests on the thoughts, "
                    "fallback sentence."
                )
            items = decisions(telepathy[chosen], correct) + decisions(modes.get("text", {}).get(chosen, []), correct)
            parts += ["", "**Confidence** (verdicts and notes, telepathy and text with the chosen steps):", ""]
            parts += ["| Confidence of the position | Decisions | Correct |", "|---|---|---|"]
            edges = (0.5, *GRID, 1.01)
            for low, high in pairwise(edges):
                inside = [g for c, g in items if low <= c < high]
                if inside:
                    correct_share = 100 * sum(inside) / len(inside)
                    parts.append(
                        f"| from {_n(low, 2)} to {_n(min(high, 1), 2)} | {len(inside)} | {_n(correct_share, 0)}% |"
                    )
            proposal = propose_thresholds(items)
            parts.append("")
            parts.append(
                f"**Proposed thresholds** (to be reviewed): high from {_n(proposal[0], 2)}, medium from "
                f"{_n(proposal[1], 2)}."
                if proposal
                else "**Thresholds:** with these data no threshold reaches 9 correct decisions out of 10."
            )
        parts.append("")
    return "\n".join(parts)


def main() -> None:
    parser = argparse.ArgumentParser(description="Calibration of latent steps and confidence thresholds.")
    parser.add_argument("folder", type=Path)
    parser.add_argument("--benchmark", default="cuad")
    args = parser.parse_args()
    print(report(args.folder, args.benchmark))


if __name__ == "__main__":
    main()
