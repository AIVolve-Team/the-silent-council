"""The relay: the agents in a row, in telepathy or in text, with the same prompts."""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass

from .check import Outcome
from .engine import Agent, Engine
from .message import TELEPATHY, LatentMessage
from .model import Generation


@dataclass
class RelayOutcome:
    messages: list[LatentMessage]
    final: Generation | None
    stopped: Outcome | None
    seconds: float

    @property
    def tokens_read(self) -> int:
        return sum(m.label["tokens_read"] for m in self.messages) + (self.final.tokens_read if self.final else 0)

    @property
    def tokens_generated(self) -> int:
        """Everything the model writes, notes and verdict included."""
        generated = sum(m.label["tokens_generated"] for m in self.messages)
        return generated + (self.final.tokens_generated if self.final else 0)

    @property
    def latent_positions(self) -> int:
        return sum(m.label["latent_steps"] for m in self.messages)


class Relay:
    def __init__(
        self,
        engine: Engine,
        agents: list[Agent],
        last: Agent,
        *,
        mode: str = TELEPATHY,
        latent_steps: int = 10,
    ) -> None:
        self.engine = engine
        self.agents = agents
        self.last = last
        self.mode = mode
        self.latent_steps = latent_steps

    def run(
        self,
        session: str,
        texts: dict[str, str],
        *,
        schema: dict | None = None,
        field_order: bool = False,
        max_spaces: int | None = None,
        observe: list[int] | None = None,
        max_tokens: int | None = None,
        thoughts_from: dict[str, LatentMessage] | None = None,
        attacks: dict[str, Callable[[LatentMessage], None]] | None = None,
    ) -> RelayOutcome:
        """Makes the agents think in order, delivers each message and then makes the last one write.

        `thoughts_from` replaces an agent's thoughts with those of another message (“Pre-registered eval” test).
        `attacks` tampers with a message after it is born and before delivery (lie-detector demo).
        If a check stops a message, the relay stops there.
        """
        start = time.perf_counter()
        chain: list[LatentMessage] = []
        names = [a.name for a in self.agents] + [self.last.name]
        for i, agent in enumerate(self.agents):
            message = self.engine.think(
                agent,
                texts[agent.name],
                chain,
                session=session,
                latent_steps=self.latent_steps,
                mode=self.mode,
                recipient=names[i + 1],
            )
            if thoughts_from and agent.name in thoughts_from:
                donor = thoughts_from[agent.name]
                origin = f"{donor.label['session']}#{donor.label['number']}"
                message = self.engine.recompute_thoughts(message, chain, states_from=donor.states, origin=origin)
            if attacks and agent.name in attacks:
                attacks[agent.name](message)
            handoff = self.engine.deliver(message, chain)
            if not handoff.outcome.passed:
                return RelayOutcome(chain, None, handoff.outcome, time.perf_counter() - start)
            chain.append(handoff.copy)
            del message  # the delivered copy remains: on a Mac the messages' memory counts
        outcome = self.engine.verify_chain(chain)
        if not outcome.passed:
            return RelayOutcome(chain, None, outcome, time.perf_counter() - start)
        final = self.engine.write(
            self.last,
            texts[self.last.name],
            chain,
            mode=self.mode,
            schema=schema,
            field_order=field_order,
            max_spaces=max_spaces,
            observe=observe,
            max_tokens=max_tokens,
        )
        return RelayOutcome(chain, final, None, time.perf_counter() - start)
