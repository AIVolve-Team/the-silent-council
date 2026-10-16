"""The confidence of note and verdict, from the logprobs of the true and false tokens.

For each category we look at the step where the model writes the boolean inside `flag`: the probability of "yes" is
p(true) / (p(true) + p(false)), with the model's distribution before the schema constraint.
"""

from __future__ import annotations

import math
import re

from engine import Generation

# Provisional thresholds: they are set on the dev set with Qwen3-14B.
THRESHOLDS = (0.9, 0.7)

_KEY = re.compile(r'"([^"]+)"\s*:\s*$')


def boolean_tokens(tokenizer) -> tuple[list[int], list[int]]:
    """The ids of the tokens that write true and false, with and without a leading space."""

    def ids(words: list[str]) -> list[int]:
        found = []
        for word in words:
            encoding = tokenizer.encode(word, add_special_tokens=False)
            if len(encoding) == 1:
                found.append(encoding[0])
        return sorted(set(found))

    return ids(["true", " true"]), ids(["false", " false"])


def p_yes(generation: Generation, trues: list[int], falses: list[int]) -> dict[str, float]:
    """Category → probability that it should be flagged, for the booleans written inside `flag`."""
    result: dict[str, float] = {}
    text = ""
    for step in generation.steps:
        # After `flag` come `quotes` (note) or `details` (verdict): there are no more booleans there.
        inside = '"flag"' in text and '"quotes"' not in text and '"details"' not in text
        key = _KEY.search(text) if inside else None
        # The boolean's step: right after `"key": `, and the written token starts with t or f.
        if key and step.observed and step.text.strip()[:1] in ("t", "f"):
            p_true = sum(math.exp(step.observed[t]) for t in trues if t in step.observed)
            p_false = sum(math.exp(step.observed[t]) for t in falses if t in step.observed)
            if p_true + p_false > 0:
                result[key.group(1)] = p_true / (p_true + p_false)
        text += step.text
    return result


def level(p_yes: float, flag: bool, thresholds: tuple[float, float] = THRESHOLDS) -> str:
    """High, medium or low, for the chosen position."""
    p = p_yes if flag else 1 - p_yes
    if p >= thresholds[0]:
        return "high"
    return "medium" if p >= thresholds[1] else "low"
