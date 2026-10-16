"""The eval's comparison configurations and the swapped thoughts, with Qwen3-0.6B on a short contract."""

import pytest
from engine import Engine, Model

from review import BENCHMARK, Council
from review.configurations import SoloAgent, VoteAmongFour
from review.run import MODELS

from .test_council import CONTRACT

pytestmark = pytest.mark.model

OTHER = CONTRACT.replace("componenti meccanici", "imballaggi").replace("€ 50.000,00", "€ 20.000,00")


@pytest.fixture(scope="module")
def engine():
    return Engine(Model("Qwen/Qwen3-0.6B", MODELS["Qwen/Qwen3-0.6B"]))


def test_solo_agent_and_vote_among_four(engine):
    for cls in (SoloAgent, VoteAmongFour):
        row = cls(engine, BENCHMARK["demo"]).review("trial", CONTRACT)
        data = row["verdict"]["data"]
        assert data is not None and len(data["flag"]) == 19 and "objections" not in data
        assert row["mode"] == cls.configuration and row["tokens_generated"] > 0
    assert len(row["votes"]) == 4
    assert row["tokens_generated"] == sum(v["tokens_generated"] for v in row["votes"].values())


def test_thoughts_from_another_contract(engine):
    council = Council(engine, BENCHMARK["demo"], latent_steps=2)
    council.review("other", OTHER)
    donors = council.thoughts
    assert set(donors) == {"legal", "finance", "risk"}
    assert all(p.states.shape[0] == 3 and p.states.device.type == "cpu" for p in donors.values())
    review = council.review("trial", CONTRACT, thoughts_from=donors)
    assert review.stopped is None and review.verdict.valid
