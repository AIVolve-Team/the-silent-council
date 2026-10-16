"""The model by contract length: short contracts to one model, long ones to another.

A single rule, no LLM: the contract's tokens are counted with the tokenizer of the short-contract model and compared
with the threshold. On 80 CUAD train contracts, in telepathy, below 6,000 tokens Qwen3-14B and Gemma 4 31B are on par
and Qwen is twice as fast; above it, Gemma finds more clauses (+12.5 F1 points). The router scores 77.4 F1 against 68.6
for Qwen alone and 75.6 for Gemma alone (branch `spike/gemma4`).
"""

from __future__ import annotations

from collections.abc import Callable

# The median length of the 80 contracts of the trial, in Qwen3-14B tokens: about 9 pages.
THRESHOLD = 6_000

Review = Callable[..., dict]


class Router:
    """Stands in for the council for the `Reviewer`: picks the model and passes the call on to it.

    `short` reviews contracts up to `threshold` tokens included, `long` the longer ones. The review already carries
    the model's name (`model`); here the counted tokens and the threshold are added, so the case says why it went there.
    """

    def __init__(self, short: Review, long: Review, count: Callable[[str], int], threshold: int = THRESHOLD) -> None:
        self.short = short
        self.long = long
        self.count = count
        self.threshold = threshold

    def __call__(self, case_id: str, text: str, mode: str, benchmark: str = "demo") -> dict:
        tokens = self.count(text)
        review = self.long if tokens > self.threshold else self.short
        result = review(case_id, text, mode, benchmark)
        return result | {"routing": {"contract_tokens": tokens, "threshold": self.threshold}}
