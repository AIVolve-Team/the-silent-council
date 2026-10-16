import pytest

from g1.summary import g1_outcome, zone


def rows(correct: list[bool], tokens: int) -> list[dict]:
    """One row per problem, with the generated tokens split in equal parts."""
    return [
        {"id": f"p{i}", "correct": c, "tokens_generated": tokens // len(correct), "tokens_read": 10, "seconds": 1.0}
        for i, c in enumerate(correct)
    ]


@pytest.mark.parametrize(
    ("difference", "expected"),
    [(1.4, "demonstrated"), (-3.0, "demonstrated"), (-3.5, "go on"), (-10.0, "go on"), (-10.5, "stop")],
)
def test_the_three_accuracy_zones(difference, expected):
    assert zone(difference) == expected


def test_fails_when_accuracy_drops_too_much_even_with_memory_and_tokens_fine():
    outcome = g1_outcome(
        text=rows([True, True, True, False], tokens=1000),
        telepathy=rows([True, True, False, False], tokens=300),
        no_thoughts=rows([True, False, False, False], tokens=280),
        memory_ok=True,
    )
    assert outcome.accuracy == {"text": 75.0, "telepathy": 50.0, "no_thoughts": 25.0}
    assert outcome.difference == -25.0
    assert outcome.zone == "stop"
    assert outcome.token_reduction == pytest.approx(0.7)
    assert outcome.passed is False


def test_fails_if_the_tokens_drop_by_less_than_half():
    outcome = g1_outcome(
        text=rows([True, True], tokens=100),
        telepathy=rows([True, True], tokens=60),
        no_thoughts=rows([True, True], tokens=60),
        memory_ok=True,
    )
    assert outcome.zone == "demonstrated"
    assert outcome.token_reduction == pytest.approx(0.4)
    assert outcome.passed is False


def test_passes_when_everything_adds_up():
    outcome = g1_outcome(
        text=rows([True] * 10, tokens=2000),
        telepathy=rows([True] * 9 + [False], tokens=500),
        no_thoughts=rows([True] * 8 + [False] * 2, tokens=480),
        memory_ok=True,
    )
    assert outcome.difference == -10.0
    assert outcome.zone == "go on"
    assert outcome.passed is True


def test_without_the_memory_measurement_the_verdict_stays_open():
    outcome = g1_outcome(
        text=rows([True], tokens=100), telepathy=rows([True], tokens=10), no_thoughts=rows([True], tokens=10)
    )
    assert outcome.passed is None


def test_the_three_runs_must_have_the_same_problems():
    with pytest.raises(ValueError, match="same problems"):
        g1_outcome(text=rows([True, True], 10), telepathy=rows([True], 10), no_thoughts=rows([True], 10))
