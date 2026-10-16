"""The score on the (contract, category) pairs: F1, precision, recall, MCC and the "always yes" baseline,
for the verdict and for the experts' notes, and how much notes and verdict agree.

A minimal version, for calibrating the latent steps on the dev set. The full eval belongs to “Council eval”.
"""

from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass
class Score:
    tp: int
    fp: int
    fn: int
    tn: int
    invalid: int

    @property
    def f1(self) -> float:
        return 100 * 2 * self.tp / (2 * self.tp + self.fp + self.fn) if self.tp else 0.0

    @property
    def precision(self) -> float:
        return 100 * self.tp / (self.tp + self.fp) if self.tp + self.fp else 0.0

    @property
    def recall(self) -> float:
        return 100 * self.tp / (self.tp + self.fn) if self.tp + self.fn else 0.0

    @property
    def mcc(self) -> float:
        numerator = self.tp * self.tn - self.fp * self.fn
        denominator = math.sqrt((self.tp + self.fp) * (self.tp + self.fn) * (self.tn + self.fp) * (self.tn + self.fn))
        return numerator / denominator if denominator else 0.0

    @property
    def f1_always_yes(self) -> float:
        positives, total = self.tp + self.fn, self.tp + self.fp + self.fn + self.tn
        return 100 * 2 * positives / (positives + total) if positives else 0.0


def _flag(review: dict, from_notes: bool) -> dict[str, bool] | None:
    """The answers on a contract: those of the verdict, or those of the valid notes put together (each category is
    looked at by a single expert, so they do not overlap). None if there is no valid one."""
    if from_notes:
        notes = [n["data"]["flag"] for n in review["notes"].values() if n["data"] is not None]
        return {key: yes for flag in notes for key, yes in flag.items()} if notes else None
    verdict = review["verdict"]
    return verdict["data"]["flag"] if verdict and verdict["data"] is not None else None


def score(reviews: list[dict], correct: dict[tuple[str, str], bool], *, from_notes: bool = False) -> Score:
    """Compares the verdicts with the correct answers. An invalid or missing answer counts as "no", and is counted
    separately.

    With `from_notes` the experts' notes put together take the place of the verdict: if the notes are right and the
    verdict is not, the flags get lost in the rapporteur.
    """
    answers = {r["contract"]: _flag(r, from_notes) for r in reviews}
    tp = fp = fn = tn = invalid = 0
    for (contract, category), right in correct.items():
        if contract not in answers:
            continue
        flag = answers[contract]
        if flag is None or category not in flag:
            invalid += 1
        said = bool(flag and flag.get(category))
        tp += said and right
        fp += said and not right
        fn += right and not said
        tn += not right and not said
    return Score(tp, fp, fn, tn, invalid)


def agreement(reviews: list[dict]) -> tuple[int, int]:
    """On how many categories the verdict says the same as the note of the expert who looks at them, among those
    where there are both the note and the verdict: (agreeing, compared)."""
    same = compared = 0
    for review in reviews:
        verdict, notes = _flag(review, False), _flag(review, True)
        if verdict is None or notes is None:
            continue
        for key, yes in notes.items():
            if key in verdict:
                compared += 1
                same += yes == verdict[key]
    return same, compared
