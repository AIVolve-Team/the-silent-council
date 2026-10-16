"""The GSM8K answers: the correct one, written after `####`, and the model's, in the last `\\boxed{}`."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path

NUMBER = re.compile(r"-?\d[\d,]*(?:\.\d+)?|-?\.\d+")
BOX = re.compile(r"\\boxed\{((?:[^{}]|\{[^{}]*\})*)\}")

# The first 100 lines of grade_school_math/data/test.jsonl of openai/grade-school-math at commit 3101c7d (MIT).
# The whole file (1,319 lines) has fingerprint 3730d312…9d14; these 100 lines have the one below.
PROBLEMS_FILE = Path(__file__).resolve().parent.parent / "data" / "gsm8k-test-100.jsonl"
PROBLEMS_FINGERPRINT = "1d266ea030421507ae8e9434bd76a7830553081c0f3d002250c429357b21ff90"


@dataclass(frozen=True)
class Problem:
    id: str
    question: str
    answer: str


def load_problems(n: int = 100, *, file: Path = PROBLEMS_FILE) -> list[Problem]:
    """The first `n` problems of the GSM8K test, only if the file is the pre-registered one."""
    data = file.read_bytes()
    if hashlib.sha256(data).hexdigest() != PROBLEMS_FINGERPRINT:
        raise ValueError(f"the fingerprint of {file} is not the pre-registered one: the file has been touched")
    rows = [json.loads(row) for row in data.decode("utf-8").splitlines()]
    return [
        Problem(f"gsm8k-test-{i:04d}", row["question"], correct_answer(row["answer"])) for i, row in enumerate(rows[:n])
    ]


def normalize(number: str) -> str | None:
    """`1,250.00` → `1250`, `.5` → `0.5`: the same number is always written the same way."""
    try:
        value = Decimal(number.replace(",", ""))
    except InvalidOperation:
        return None
    if value == value.to_integral_value():
        return str(int(value))
    return format(value.normalize(), "f")


def last_number(text: str) -> str | None:
    numbers = NUMBER.findall(text)
    return normalize(numbers[-1]) if numbers else None


def correct_answer(solution: str) -> str:
    answer = last_number(solution.split("####")[-1])
    if answer is None:
        raise ValueError(f"solution without an answer after ####: {solution[-80:]!r}")
    return answer


def extract_answer(text: str) -> str | None:
    """The last number of the last box; with no box, or if the box has no numbers, the last one in the text."""
    boxes = BOX.findall(text)
    if boxes and (inside := last_number(boxes[-1])) is not None:
        return inside
    return last_number(text)


def is_correct(predicted: str | None, correct: str) -> bool:
    if predicted is None:
        return False
    return Decimal(predicted) == Decimal(normalize(correct) or "NaN")
