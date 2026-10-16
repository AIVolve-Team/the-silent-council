import pytest

from g1.gsm8k import PROBLEMS_FILE, load_problems


def test_they_are_the_first_100_problems_of_the_official_test():
    problems = load_problems()
    assert len(problems) == 100
    first = problems[0]
    assert first.id == "gsm8k-test-0000"
    assert first.question.startswith("Janet’s ducks lay 16 eggs per day.")
    assert first.answer == "18"
    assert problems[-1].id == "gsm8k-test-0099"


def test_fewer_can_be_taken():
    assert [p.id for p in load_problems(2)] == ["gsm8k-test-0000", "gsm8k-test-0001"]


def test_a_touched_file_is_not_used(tmp_path):
    touched = tmp_path / "gsm8k.jsonl"
    touched.write_text(PROBLEMS_FILE.read_text().replace("16 eggs", "17 eggs", 1))
    with pytest.raises(ValueError, match="fingerprint"):
        load_problems(file=touched)
