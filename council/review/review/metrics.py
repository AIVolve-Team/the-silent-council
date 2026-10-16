"""The metrics of the council's eval, from the reviews written by `review.eval`.

Everything starts from the `.jsonl` rows (one review per contract, in the shape of `Review.as_dict()`) and from the
correct answers: no model runs here. The rules, operational definitions included, are in the pre-registration
(`council/PREREGISTRAZIONE.md`).
"""

from __future__ import annotations

import random
import re
from collections import Counter
from dataclasses import dataclass

from .confidence import level
from .council import MAX_ANALYSIS_TOKENS
from .quotes import normalize
from .scoring import Score, agreement, score

# The configurations, in report order: the four compared ones and the three sabotage tests.
CONFIGURATIONS = ("solo", "vote", "text", "telepathy", "m0", "swapped-thoughts", "swapped-contract")
SABOTAGES = ("m0", "swapped-thoughts", "swapped-contract")
NAMES = {
    "solo": "Solo agent",
    "vote": "4 independent agents and vote",
    "text": "Council in text",
    "telepathy": "Council in telepathy",
    "m0": "Zeroed thoughts (m=0)",
    "swapped-thoughts": "Thoughts from another contract",
    "swapped-contract": "Swapped contract",
}
# Thresholds of “Pre-registered eval”.
F1_MARGIN = 3.0
THOUGHTS_DROP = 2.0
TOKEN_REDUCTION = 0.5
BOOTSTRAP_REPETITIONS = 10_000
BOOTSTRAP_SEED = 62
OVERLAP_WORDS = 5


# --- strict version ------------------------------------------------------------------------------------------------


def _words(text: str) -> list[str]:
    return re.findall(r"\w+", normalize(text))


def overlaps(quote: str, evidence: list[str]) -> bool:
    """The quote overlaps an annotated span: they share at least 5 consecutive words, or the whole quote if it is
    shorter. Quotes of fewer than 3 words do not count, as in `quotes.found`. Words and punctuation are compared after
    the same normalization as the quotes."""
    words = _words(quote)
    if len(words) < 3:
        return False
    n = min(OVERLAP_WORDS, len(words))
    wanted = {tuple(words[i : i + n]) for i in range(len(words) - n + 1)}
    for span in evidence:
        annotated = _words(span)
        if any(tuple(annotated[i : i + n]) in wanted for i in range(len(annotated) - n + 1)):
            return True
    return False


def _quotes(review: dict) -> dict[str, list[str]]:
    data = (review.get("verdict") or {}).get("data") or {}
    quotes: dict[str, list[str]] = {}
    for d in data.get("details", []):
        quotes.setdefault(d["category"], []).append(d.get("quote") or "")
    return quotes


def strict_score(reviews: list[dict], correct: dict, evidence: dict) -> Score:
    """Like `score`, but a correct "yes" counts only if one of its quotes overlaps an annotated span: otherwise it
    counts as a missed clause."""
    strict = []
    for r in reviews:
        data = (r.get("verdict") or {}).get("data")
        if data is None:
            strict.append(r)
            continue
        quotes = _quotes(r)
        flag = {}
        for category, yes in data["flag"].items():
            key = (r["contract"], category)
            # The "no"s and the false alarms stay as they are; a correct "yes" stays only with the right quote.
            right = yes and correct.get(key)
            flag[category] = any(overlaps(q, evidence.get(key, [])) for q in quotes.get(category, [])) if right else yes
        strict.append({**r, "verdict": {**r["verdict"], "data": {**data, "flag": flag}}})
    return score(strict, correct)


# --- paired bootstrap ----------------------------------------------------------------------------------------------


def _counts(reviews: list[dict], correct: dict) -> dict[str, tuple[int, int, int]]:
    """Contract → (tp, fp, fn) of the main score."""
    out = {}
    for r in reviews:
        s = score([r], {k: g for k, g in correct.items() if k[0] == r["contract"]})
        out[r["contract"]] = (s.tp, s.fp, s.fn)
    return out


def _f1(tp: int, fp: int, fn: int) -> float:
    return 100 * 2 * tp / (2 * tp + fp + fn) if tp else 0.0


@dataclass
class Difference:
    difference: float
    low: float
    high: float
    contracts: int

    @property
    def shown(self) -> bool:
        """We say "does not lose, shown" if even the lower bound is within −3 points."""
        return self.low >= -F1_MARGIN


def paired_bootstrap(
    a: list[dict], b: list[dict], correct: dict, *, repetitions: int = BOOTSTRAP_REPETITIONS, seed: int = BOOTSTRAP_SEED
) -> Difference:
    """F1(a) − F1(b) with the 95% interval: the contracts are resampled with replacement, the same for a and b.
    Percentiles 2.5 and 97.5, fixed seed."""
    ca, cb = _counts(a, correct), _counts(b, correct)
    contracts = sorted(set(ca) & set(cb))
    if not contracts:
        raise ValueError("no contract in common between the two configurations")

    def difference(chosen: list[str]) -> float:
        sa = [sum(ca[c][i] for c in chosen) for i in range(3)]
        sb = [sum(cb[c][i] for c in chosen) for i in range(3)]
        return _f1(*sa) - _f1(*sb)

    rng = random.Random(seed)
    samples = sorted(difference(rng.choices(contracts, k=len(contracts))) for _ in range(repetitions))
    return Difference(
        difference(contracts),
        samples[int(0.025 * (repetitions - 1))],
        samples[int(0.975 * (repetitions - 1))],
        len(contracts),
    )


# --- costs ---------------------------------------------------------------------------------------------------------


def costs(reviews: list[dict]) -> dict[str, float]:
    """Averages per contract: tokens read, generated (notes included) and total, and seconds."""
    n = len(reviews) or 1
    read = sum(r["tokens_read"] for r in reviews) / n
    generated = sum(r["tokens_generated"] for r in reviews) / n
    return {
        "tokens_read": read,
        "tokens_generated": generated,
        "tokens_total": read + generated,
        "seconds": sum(r["seconds"] for r in reviews) / n,
    }


# --- metrics without a threshold -----------------------------------------------------------------------------------


def who_is_right(reviews: list[dict], correct: dict) -> dict[str, tuple[int, int]]:
    """In the major dissents (expert yes, verdict no) how many times the expert was right; in the minor ones (expert
    no, verdict yes) how many times the rapporteur was right. (right, dissents with a known correct answer)."""
    count = {"major": [0, 0], "minor": [0, 0]}
    for r in reviews:
        for d in r.get("dissents", []):
            right = correct.get((r["contract"], d["category"]))
            if right is None:
                continue
            count[d["type"]][1] += 1
            # Major: the expert is right if the clause should be flagged. Minor: the rapporteur is right if it should.
            count[d["type"]][0] += right
    return {kind: (a, n) for kind, (a, n) in count.items()}


def calibration(reviews: list[dict], correct: dict) -> dict[str, tuple[int, int]]:
    """Per confidence level of the verdict (high, medium, low), (correct, decisions)."""
    count = {"high": [0, 0], "medium": [0, 0], "low": [0, 0]}
    for r in reviews:
        verdict = r.get("verdict") or {}
        data = verdict.get("data")
        if not data:
            continue
        for category, yes in data["flag"].items():
            p = verdict.get("p_yes", {}).get(category)
            right = correct.get((r["contract"], category))
            if p is None or right is None:
                continue
            item = count[level(p, yes)]
            item[0] += yes == right
            item[1] += 1
    return {k: (g, n) for k, (g, n) in count.items()}


# Amounts and dates in the Italian format of the demo contracts.
_AMOUNT = re.compile(r"(?:€\s?\d[\d.]*(?:,\d+)?|\d[\d.]*(?:,\d+)?\s?(?:€|euro\b))", re.IGNORECASE)
_MONTHS = "gennaio|febbraio|marzo|aprile|maggio|giugno|luglio|agosto|settembre|ottobre|novembre|dicembre"
_DATE = re.compile(rf"\b\d{{1,2}}[/.-]\d{{1,2}}[/.-]\d{{2,4}}\b|\b\d{{1,2}}°? (?:{_MONTHS}) \d{{4}}\b", re.IGNORECASE)


def _digits(amount: str) -> str:
    return re.sub(r"[^\d,]", "", amount).rstrip(",")


def amounts_and_dates(review: dict, contract: str) -> tuple[int, int]:
    """Amounts and dates written in the verdict (quotes, rationales) and how many do not appear in the contract: a
    wrong amount is always flagged. Counts only: the values stay in the `.jsonl` files."""
    data = (review.get("verdict") or {}).get("data") or {}
    pieces = [data.get("rationale") or ""]
    pieces += [f"{d.get('quote', '')} {d.get('rationale', '')}" for d in data.get("details", [])]
    text = " ".join(pieces)
    in_contract = {_digits(i) for i in _AMOUNT.findall(contract)}
    normal_contract = normalize(contract)
    found = [("amount", _digits(i)) for i in _AMOUNT.findall(text)]
    found += [("date", normalize(d)) for d in _DATE.findall(text)]
    outside = sum(
        (value not in in_contract) if kind == "amount" else (value not in normal_contract) for kind, value in found
    )
    return len(found), outside


# --- decisions -----------------------------------------------------------------------------------------------------


def g4(telepathy: list[dict], text: list[dict], correct: dict) -> dict[str, bool]:
    """The three conditions of G4 on CUAD."""
    f1_tele, f1_text = score(telepathy, correct).f1, score(text, correct).f1
    ct, cx = costs(telepathy), costs(text)
    return {
        "f1": f1_tele >= f1_text - F1_MARGIN,
        "tokens": ct["tokens_generated"] <= (1 - TOKEN_REDUCTION) * cx["tokens_generated"],
        "time": ct["seconds"] <= cx["seconds"],
    }


def thoughts_help(f1_telepathy: float, f1_m0: float | None, f1_swapped: float | None) -> bool | None:
    """We say "the thoughts improve the result" only if the zeroed thoughts drop the F1 by at least 2 points and those
    of another contract drop it. None if one of the two tests is missing."""
    if f1_m0 is None or f1_swapped is None:
        return None
    return f1_telepathy - f1_m0 >= THOUGHTS_DROP and f1_swapped < f1_telepathy


SENTENCE_ALWAYS = "The agents hand each other their thoughts."
# With 0 latent steps there are no thoughts: the mechanism is described for what it is (PREREGISTRAZIONE.md).
SENTENCE_MEMORY = "The agents hand each other the memory of what they read."
SENTENCE_THOUGHTS = "The thoughts improve the result."
SENTENCE_FALLBACK = (
    "The agents hand each other the memory of what they read instead of rewriting it: same quality, fewer tokens."
)


# --- chart ---------------------------------------------------------------------------------------------------------


def svg_chart(points: list[tuple[str, float, float]], title: str) -> str:
    """F1 against tokens generated per contract, one point per configuration: (name, tokens, F1)."""
    width, height, margin = 640, 400, 60
    max_x = max((x for _, x, _ in points), default=1) * 1.1 or 1

    def px(x: float) -> float:
        return margin + x / max_x * (width - 2 * margin)

    def py(y: float) -> float:
        return height - margin - y / 100 * (height - 2 * margin)

    lines = [
        (
            f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" '
            'font-family="sans-serif" font-size="12">'
        ),
        f'<rect width="{width}" height="{height}" fill="white"/>',
        f'<text x="{width / 2}" y="24" text-anchor="middle" font-size="15">{title}</text>',
        f'<line x1="{margin}" y1="{py(0)}" x2="{width - margin}" y2="{py(0)}" stroke="black"/>',
        f'<line x1="{margin}" y1="{py(0)}" x2="{margin}" y2="{py(100)}" stroke="black"/>',
        f'<text x="{width / 2}" y="{height - 18}" text-anchor="middle">tokens generated per contract</text>',
        f'<text x="18" y="{height / 2}" text-anchor="middle" transform="rotate(-90 18 {height / 2})">F1</text>',
    ]
    for y in range(0, 101, 20):
        lines.append(f'<text x="{margin - 8}" y="{py(y) + 4}" text-anchor="end">{y}</text>')
        lines.append(f'<line x1="{margin}" y1="{py(y)}" x2="{width - margin}" y2="{py(y)}" stroke="#ddd"/>')
    for i in range(5):
        x = max_x * i / 4
        lines.append(f'<text x="{px(x)}" y="{py(0) + 18}" text-anchor="middle">{x:,.0f}</text>')
    for name, x, y in points:
        lines.append(f'<circle cx="{px(x):.1f}" cy="{py(y):.1f}" r="5" fill="#1f5fae"/>')
        lines.append(f'<text x="{px(x) + 8:.1f}" y="{py(y) - 8:.1f}">{name} ({y:.1f})</text>')
    lines.append("</svg>")
    return "\n".join(lines)


# --- summary per benchmark -----------------------------------------------------------------------------------------


def score_row(reviews: list[dict], correct: dict, evidence: dict) -> dict:
    main = score(reviews, correct)
    strict = strict_score(reviews, correct, evidence)
    valid = sum(bool((r.get("verdict") or {}).get("data")) for r in reviews)
    return {
        "contracts": len(reviews),
        "valid_verdicts": valid,
        "f1": main.f1,
        "precision": main.precision,
        "recall": main.recall,
        "mcc": main.mcc,
        "always_yes": main.f1_always_yes,
        "missed": main.fn,
        "false_alarms": main.fp,
        "strict_f1": strict.f1,
        **truncated_analyses(reviews),
        **costs(reviews),
    }


def truncated_analyses(reviews: list[dict]) -> dict[str, int]:
    """In text mode: how many of the experts' analyses hit the token cap, and how many there are in all."""
    tokens = [t for r in reviews for t in (r.get("analyses") or {}).values()]
    return {"analyses": len(tokens), "truncated_analyses": sum(t >= MAX_ANALYSIS_TOKENS for t in tokens)}


def summary(
    runs: dict[str, list[dict]],
    correct: dict,
    evidence: dict,
    *,
    texts: dict[str, str] | None = None,
    grade_3: dict | None = None,
) -> dict:
    """All the numbers of a benchmark: `runs` is configuration → reviews."""
    numbers: dict = {"configurations": {c: score_row(r, correct, evidence) for c, r in runs.items()}}
    if "telepathy" in runs and "text" in runs:
        d = paired_bootstrap(runs["telepathy"], runs["text"], correct)
        numbers["telepathy_vs_text"] = {
            "difference": d.difference,
            "low": d.low,
            "high": d.high,
            "contracts": d.contracts,
            "shown": d.shown,
            "g4": g4(runs["telepathy"], runs["text"], correct),
        }
    if "telepathy" in runs and "solo" in runs:
        # The comparison that isolates the channel: in telepathy the rapporteur works on the memory of the reading of
        # the whole contract, the solo agent reads the whole contract.
        d = paired_bootstrap(runs["telepathy"], runs["solo"], correct)
        numbers["telepathy_vs_solo"] = {
            "difference": d.difference,
            "low": d.low,
            "high": d.high,
            "contracts": d.contracts,
        }
    if "telepathy" in runs:
        f1 = {c: numbers["configurations"][c]["f1"] for c in runs}
        numbers["sabotages"] = {c: f1[c] - f1["telepathy"] for c in SABOTAGES if c in f1}
        numbers["thoughts_help"] = thoughts_help(f1["telepathy"], f1.get("m0"), f1.get("swapped-thoughts"))
    numbers["without_threshold"] = {}
    for c in ("text", "telepathy"):
        if c in runs:
            same, compared = agreement(runs[c])
            numbers["without_threshold"][c] = {
                "dissents": who_is_right(runs[c], correct),
                "calibration": calibration(runs[c], correct),
                "notes_verdict_agreement": (same, compared),
                "notes_as_verdict_f1": score(runs[c], correct, from_notes=True).f1,
            }
    if texts:
        numbers["amounts_and_dates"] = {
            c: tuple(map(sum, zip(*(amounts_and_dates(r, texts[r["contract"]]) for r in rev), strict=True)))
            for c, rev in runs.items()
            if rev and c != "swapped-contract"
        }
    if grade_3:
        numbers["grade_3"] = {c: score(r, grade_3).f1 for c, r in runs.items()}
    numbers["recommendations"] = {
        c: dict(Counter(((r.get("verdict") or {}).get("data") or {}).get("recommendation") for r in rev))
        for c, rev in runs.items()
    }
    return numbers
