from reviewer.manager import Reviewer
from reviewer.routing import THRESHOLD, Router

from .conftest import CONTRACT, LINK, SECRET, FakeCouncil, email


class CouncilOf(FakeCouncil):
    """The fake council with its model's name in the review, like the real one."""

    def __init__(self, model: str) -> None:
        super().__init__()
        self.model = model

    def __call__(self, *args, **options) -> dict:
        return super().__call__(*args, **options) | {"model": self.model}


def words(text: str) -> int:
    return len(text.split())


def test_up_to_the_threshold_the_short_model_beyond_it_the_long_one():
    short, long = CouncilOf("Qwen/Qwen3-14B"), CouncilOf("google/gemma-4-31B-it")
    router = Router(short, long, words, threshold=3)
    assert router("a", "one two three", "telepathy")["model"] == "Qwen/Qwen3-14B"
    longer = router("b", "one two three four", "telepathy", "cuad")
    assert longer["model"] == "google/gemma-4-31B-it"
    assert longer["routing"] == {"contract_tokens": 4, "threshold": 3}
    assert short.calls == [("a", "one two three", "telepathy", "demo")]
    assert long.calls == [("b", "one two three four", "telepathy", "cuad")]


def test_the_default_threshold_is_the_trial_one():
    assert Router(FakeCouncil(), FakeCouncil(), words).threshold == THRESHOLD == 6_000


def test_the_response_for_evolus_says_which_model_reviewed(tmp_path):
    router = Router(CouncilOf("Qwen/Qwen3-14B"), CouncilOf("google/gemma-4-31B-it"), words, threshold=1)
    reviewer = Reviewer(router, tmp_path / "cases", secret=SECRET, link=LINK)
    response = reviewer.review_contract(None, CONTRACT, **email())
    assert response["model"] == "google/gemma-4-31B-it" and response["verdict"]
