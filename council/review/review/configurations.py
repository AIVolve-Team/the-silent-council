"""The eval's comparison configurations: the solo agent and the vote among 4 independent agents.

Whoever works alone reads the whole contract and writes a verdict with the council's schema, without objections because
it has no colleagues. The result has the shape of `Review.as_dict()`, so score, tokens and times are measured the same
way for all configurations.
"""

from __future__ import annotations

import time
from collections import Counter
from dataclasses import asdict

from engine import TEXT, Agent, Engine

from .categories import Benchmark
from .confidence import boolean_tokens
from .council import Review, Written, _written
from .prompts import INDEPENDENT, independent_instructions, solo_instructions, whole_contract
from .quotes import check
from .schemas import RECOMMENDATIONS, max_tokens, verdict_schema

SOLO, VOTE = "solo", "vote"


class _Alone:
    """An agent that reads the whole contract and writes the verdict without colleagues."""

    configuration = ""

    def __init__(self, engine: Engine, benchmark: Benchmark, *, translate: bool = False) -> None:
        self.engine = engine
        self.benchmark = benchmark
        self.translate = translate
        self.schema = verdict_schema(benchmark.categories, objections=False)
        self.trues, self.falses = boolean_tokens(engine.model.tokenizer)

    def _write(self, agent: Agent, text: str) -> Written:
        generation = self.engine.write(
            agent,
            whole_contract(text, translate=self.translate),
            [],
            mode=TEXT,
            schema=self.schema,
            field_order=True,
            max_spaces=1,
            observe=self.trues + self.falses,
            max_tokens=max_tokens(self.schema),
        )
        return _written(generation, self.trues, self.falses, text)

    def _review(self, contract: str, text: str) -> Review:
        return Review(
            self.benchmark.name,
            contract,
            self.configuration,
            0,
            self.engine.model.name,
            {"mode": "whole", "clauses": 0, "chars": {"all": len(text)}},
            realign=self.engine.model.realign,
        )


class SoloAgent(_Alone):
    """Configuration 1: a single agent reads the whole contract."""

    configuration = SOLO

    def review(self, contract: str, text: str) -> dict:
        start = time.perf_counter()
        review = self._review(contract, text)
        review.verdict = self._write(Agent(SOLO, solo_instructions(self.benchmark)), text)
        review.tokens_read = review.verdict.tokens_read
        review.tokens_generated = review.verdict.tokens_generated
        review.seconds = time.perf_counter() - start
        return review.as_dict()


def vote_among(written: dict[str, Written], categories: list[str]) -> tuple[dict[str, bool], dict[str, float]]:
    """For each category the majority of the valid verdicts wins.

    On a tie the group with the higher mean confidence wins, that is the mean probability of the chosen position;
    at equal confidence "yes" wins. Returns the positions and, for calibration, the mean p(yes) of the valid verdicts.
    """
    valid = [w for w in written.values() if w.valid]
    flag, probability = {}, {}
    for category in categories:
        votes = [(w.data["flag"][category], w.p_yes.get(category, 0.5)) for w in valid]
        yes = [p for position, p in votes if position]
        no = [1 - p for position, p in votes if not position]
        if len(yes) != len(no):
            flag[category] = len(yes) > len(no)
        else:
            flag[category] = sum(yes) / max(len(yes), 1) >= sum(no) / max(len(no), 1)
        if votes:
            probability[category] = sum(p for _, p in votes) / len(votes)
    return flag, probability


def common_recommendation(recommendations: list[str]) -> str | None:
    """The most frequent; on a tie the most cautious (do not sign, then negotiate, then sign)."""
    if not recommendations:
        return None
    count = Counter(recommendations)
    return max(count, key=lambda r: (count[r], RECOMMENDATIONS.index(r)))


class VoteAmongFour(_Alone):
    """Configuration 2: 4 independent agents, with the council's points of view, read the whole contract and vote
    category by category. Tokens and times are the sum of the 4."""

    configuration = VOTE

    def __init__(self, engine: Engine, benchmark: Benchmark, *, translate: bool = False) -> None:
        super().__init__(engine, benchmark, translate=translate)
        self.agents = [Agent(r, independent_instructions(r, benchmark)) for r in INDEPENDENT]

    def review(self, contract: str, text: str) -> dict:
        start = time.perf_counter()
        review = self._review(contract, text)
        written = {agent.name: self._write(agent, text) for agent in self.agents}
        valid = [w for w in written.values() if w.valid]
        read = sum(w.tokens_read for w in written.values())
        generated = sum(w.tokens_generated for w in written.values())
        data = None
        probability: dict[str, float] = {}
        if valid:
            flag, probability = vote_among(written, [c.key for c in self.benchmark.categories])
            # For each category set to yes, the first detail of an agent that voted yes: the strict version of the
            # score and the page need it.
            details, seen = [], set()
            for w in valid:
                for d in w.data["details"]:
                    category = d["category"]
                    if flag.get(category) and w.data["flag"].get(category) and category not in seen:
                        seen.add(category)
                        details.append(d)
            data = {
                "flag": flag,
                "details": details,
                "recommendation": common_recommendation([w.data["recommendation"] for w in valid]),
                "rationale": "",
            }
        review.verdict = Written(data, probability, check(data, text), read, generated, "")
        review.tokens_read, review.tokens_generated = read, generated
        review.seconds = time.perf_counter() - start
        row = review.as_dict()
        row["votes"] = {name: asdict(w) for name, w in written.items()}
        return row
