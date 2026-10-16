import json
import os

import pytest
from engine import Engine, Model

from g1.gsm8k import load_problems
from g1.run import run_mode

NAME = os.environ.get("G1_MODEL", "Qwen/Qwen3-0.6B")
REVISION = os.environ.get("G1_REVISION", "c1899de289a04d12100db370d81485cdf75e47ca")

pytestmark = pytest.mark.model


@pytest.fixture(scope="module")
def engine():
    return Engine(Model(NAME, REVISION), max_text_tokens=24)


def test_the_three_modes_on_one_problem_and_the_resume(engine, tmp_path):
    problems = load_problems(1)
    rows = {
        mode: run_mode(engine, mode, problems, tmp_path / f"{mode}.jsonl", max_answer_tokens=48)
        for mode in ("text", "telepathy", "no_thoughts")
    }

    for mode, (row,) in rows.items():
        assert row["id"] == "gsm8k-test-0000"
        assert row["mode"] == mode
        assert row["correct_answer"] == "18"
        assert row["correct"] in (True, False)
        assert row["stopped"] is None
    assert rows["text"][0]["tokens_generated"] > rows["telepathy"][0]["tokens_generated"]
    assert rows["telepathy"][0]["latent_positions"] == 30
    assert rows["no_thoughts"][0]["latent_positions"] == 0
    assert rows["text"][0]["truncated"] >= 1  # with 24 tokens per agent at least one message is truncated

    file = tmp_path / "telepathy.jsonl"
    again = run_mode(engine, "telepathy", problems, file, max_answer_tokens=48)
    assert again == rows["telepathy"]
    assert len(file.read_text().splitlines()) == 1
    assert json.loads(file.read_text())["id"] == "gsm8k-test-0000"
