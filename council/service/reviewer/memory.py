"""The memory of the last reviews, for the questions on a case: `ask_council` answers from it.

The council keeps the chain of each review: in telepathy the memory of what the experts read, in text mode their
analyses. A question is answered from that chain by the same council that made it, without the contract, which the
server does not keep. The chain stays in memory only, never on disk: it is the contract in another form. When the
memory exceeds its budget the oldest cases go first, and a question on them asks to review the contract again.
"""

from __future__ import annotations

import threading
from collections import OrderedDict
from typing import Protocol

from .manager import Rejected


class Answers(Protocol):
    def answer(self, text: str, memory: list, *, visual: bool = False) -> dict: ...


def size_of(memory: list) -> int:
    """Bytes of a chain: the KV of each message, its latent steps and states. Text messages weigh nothing here."""
    total = 0
    for message in memory:
        for k, v in [*getattr(message, "kv_read", []), *getattr(message, "kv_thoughts", [])]:
            total += k.nelement() * k.element_size() + v.nelement() * v.element_size()
        states = getattr(message, "states", None)
        if states is not None:
            total += states.nelement() * states.element_size()
    return total


class Memories:
    def __init__(self, budget: int) -> None:
        """`budget`: bytes of chains kept at most. The newest case is always kept, even alone over the budget."""
        self.budget = budget
        self.items: OrderedDict[str, tuple[Answers, list, int]] = OrderedDict()
        self.lock = threading.Lock()

    def keep(self, case_id: str, council: Answers, memory: list) -> None:
        with self.lock:
            self.items.pop(case_id, None)
            self.items[case_id] = (council, memory, size_of(memory))
            while len(self.items) > 1 and self.used > self.budget:
                self.items.popitem(last=False)

    @property
    def used(self) -> int:
        return sum(size for _, _, size in self.items.values())

    def ask(self, case_id: str, question: str, *, visual: bool = False) -> dict:
        """`visual`: a question on what the pages look like, answered with the objects seen on them; the
        manager asks it after a review in the visual route."""
        with self.lock:
            item = self.items.get(case_id)
            if item is not None:
                self.items.move_to_end(case_id)
        if item is None:
            raise Rejected(
                f"the memory of case {case_id} is no longer on the server (it keeps only the last reviews, and never "
                "on disk): review the contract again to ask about it"
            )
        council, memory, size = item
        # Without `visual` the call is the one of before, so a council that predates it still answers.
        result = council.answer(question, memory, visual=True) if visual else council.answer(question, memory)
        return result | {"memory_bytes": size}
