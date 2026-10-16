"""The G1 verdict, as pre-registered in memory, tokens and three zones for accuracy.

python -m g1.summary results/      # prints the report to publish
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path

TOKEN_THRESHOLD = 0.5  # tokens generated in telepathy at least 50% fewer than in text
DEMONSTRATED = -3.0  # within 3 points of text
STOP = -10.0  # more than 10 points below: something in the engine is broken
H100_GB = 80  # above this, the script's line "it wouldn't fit on an H100" can be said
RUNS = {"text": "text", "telepathy": "telepathy (10 steps)", "no_thoughts": "no thoughts (m=0)"}


def zone(difference: float) -> str:
    """`difference` = accuracy of telepathy minus that of text, in percentage points."""
    if difference >= DEMONSTRATED:
        return "demonstrated"
    if difference >= STOP:
        return "go on"
    return "stop"


@dataclass(frozen=True)
class G1Outcome:
    accuracy: dict[str, float]
    tokens_generated: dict[str, int]
    token_reduction: float
    difference: float
    zone: str
    memory_ok: bool | None
    passed: bool | None


def accuracy(rows: list[dict]) -> float:
    return 100 * sum(r["correct"] for r in rows) / len(rows)


def g1_outcome(
    *, text: list[dict], telepathy: list[dict], no_thoughts: list[dict], memory_ok: bool | None = None
) -> G1Outcome:
    runs = {"text": text, "telepathy": telepathy, "no_thoughts": no_thoughts}
    sets = {name: {r["id"] for r in rows} for name, rows in runs.items()}
    if len({frozenset(s) for s in sets.values()}) != 1:
        raise ValueError(f"the three runs must have the same problems: { ({k: len(v) for k, v in sets.items()}) }")
    acc = {name: accuracy(rows) for name, rows in runs.items()}
    tokens = {name: sum(r["tokens_generated"] for r in rows) for name, rows in runs.items()}
    reduction = 1 - tokens["telepathy"] / tokens["text"]
    difference = acc["telepathy"] - acc["text"]
    accuracy_zone = zone(difference)
    passed = None if memory_ok is None else memory_ok and reduction >= TOKEN_THRESHOLD and accuracy_zone != "stop"
    return G1Outcome(acc, tokens, reduction, difference, accuracy_zone, memory_ok, passed)


def decimal(x: float, digits: int = 1) -> str:
    return f"{x:.{digits}f}"


def integer(n: int) -> str:
    return f"{n:,}"


def read(file: Path) -> list[dict]:
    return [json.loads(row) for row in file.read_text().splitlines()]


def report(folder: Path) -> str:
    """The G1 report, from the three runs and, if present, from `memory.json`."""
    all_rows = {name: read(folder / f"{name}.jsonl") for name in RUNS}
    # If the run was interrupted, only the problems finished in all three modes count.
    finished = set.intersection(*({r["id"] for r in rows} for rows in all_rows.values()))
    rows = {name: [r for r in run_rows if r["id"] in finished] for name, run_rows in all_rows.items()}
    environment_file = folder / "environment.json"
    expected = json.loads(environment_file.read_text())["problems"] if environment_file.exists() else len(finished)
    memory_file = folder / "memory.json"
    memory = json.loads(memory_file.read_text()) if memory_file.exists() else None
    outcome = g1_outcome(**rows, memory_ok=None if memory is None else bool(memory.get("ok")))

    table = [
        "| Run | Accuracy | Tokens generated | Tokens read | Seconds per problem | Truncated messages |",
        "|---|---|---|---|---|---|",
    ]
    for name, title in RUNS.items():
        r = rows[name]
        seconds = sum(x["seconds"] for x in r) / len(r)
        table.append(
            f"| {title} | {decimal(outcome.accuracy[name])}% | {integer(outcome.tokens_generated[name])} "
            f"| {integer(sum(x['tokens_read'] for x in r))} | {decimal(seconds)} | {sum(x['truncated'] for x in r)} |"
        )

    reduction = outcome.token_reduction * 100
    sign = "−" if reduction >= 0 else "+"
    tokens_ok = "✓" if outcome.token_reduction >= TOKEN_THRESHOLD else "✗"
    points = ("+" if outcome.difference >= 0 else "−") + decimal(abs(outcome.difference))
    items = [
        (
            f"- **Tokens generated in telepathy:** {sign}{decimal(abs(reduction), 0)}% compared with text "
            f"(threshold: at least −50%) {tokens_ok}"
        ),
        f"- **Accuracy:** telepathy minus text = {points} points → zone **{outcome.zone}**",
    ]
    if memory is None:
        items.append("- **Memory:** the memory measurement is missing (`python -m g1.metrics memory`)")
    else:
        status = "✓" if memory.get("ok") else f"✗ {memory.get('error', '')}".rstrip()
        items.append(f"- **Memory:** engine and Qwen3.6 on the same MI300X without errors {status}")
        weights = memory.get("two_models_weights_gb")
        if weights is not None:
            line = "can be said" if weights > H100_GB else "cannot be said"
            items.append(
                f'- **Weights of the two models:** {decimal(weights)} GB: the line *"it wouldn\'t fit on an H100"* '
                f"{line} (it takes more than {H100_GB} GB)"
            )
    verdict = {True: "**G1 passes**", False: "**G1 does not pass**", None: "**G1 still open**"}[outcome.passed]
    header = ["## G1: the engine on the MI300X", ""]
    if len(finished) < expected:
        word = "problem" if len(finished) == 1 else "problems"
        header += [f"> **Partial: {len(finished)} {word} out of {expected}** finished in the three modes.", ""]
    return "\n".join([*header, *table, "", *items, "", verdict, ""])


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("folder", type=Path)
    print(report(parser.parse_args().folder))


if __name__ == "__main__":
    main()
