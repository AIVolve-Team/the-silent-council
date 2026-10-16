"""The judges' live reviews: the judge picks a contract from a list, never an arbitrary text.

This way the GPU does not examine anybody's texts and every verdict has the comparison with the experts. The catalog
has the CUAD contracts of the sample (they need the files of `data/cache`, which `prepare.py` downloads) and, only at
delivery, the demo set. The key of a contract is "<benchmark>:<id>".

The test contracts are added only after the pre-registered eval: before that, running them live would mean
looking at the test.
"""

from __future__ import annotations

from collections.abc import Callable

from .data import contracts, expert_answers
from .showcase import SOURCES, cuad_title, demo_expected, title_of

SUBSETS = ("dev", "test")


def catalog(
    subsets: tuple[str, ...] = ("dev",),
    *,
    with_demo: bool = False,
    length: Callable[[str], int] | None = None,
    max_tokens: int | None = None,
) -> dict[str, dict]:
    """key → benchmark, contract, subset, text, title, experts' answers and source. With `max_tokens` (and the
    `length` in tokens of a text) the contracts that are too long stay out, as in `review.run`."""
    if unknown := sorted(set(subsets) - set(SUBSETS)):
        raise ValueError(f"unknown subsets: {', '.join(unknown)}")
    within = (lambda text: True) if not max_tokens or length is None else (lambda text: length(text) <= max_tokens)
    items = {}
    experts = expert_answers("cuad")
    for subset in subsets:
        for cid, text in contracts("cuad", subset):
            if within(text):
                items[f"cuad:{cid}"] = {
                    "benchmark": "cuad",
                    "contract": cid,
                    "subset": subset,
                    "text": text,
                    "title": cuad_title(cid),
                    "experts": experts.get(cid),
                    "source": SOURCES["cuad"],
                }
    if with_demo:
        texts, expected = demo_expected()
        for cid, text in texts.items():
            if within(text):
                items[f"demo:{cid}"] = {
                    "benchmark": "demo",
                    "contract": cid,
                    "subset": "demo",
                    "text": text,
                    "title": title_of({"contract": cid, "benchmark": "demo"}, texts),
                    "experts": expected.get(cid),
                    "source": SOURCES["demo"],
                }
    return items


def listing(items: dict[str, dict]) -> list[dict]:
    """What the judge sees to choose: key, title and where it comes from. The text stays on the server."""
    return [
        {"key": k, "title": v["title"], "benchmark": v["benchmark"], "subset": v["subset"]} for k, v in items.items()
    ]
