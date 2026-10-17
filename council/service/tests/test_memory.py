"""The memory of the last reviews for the questions, without the model."""

import pytest
import torch

from reviewer.manager import Rejected
from reviewer.memory import Memories, size_of


class Message:
    def __init__(self, positions: int) -> None:
        self.kv_read = [(torch.zeros(1, 2, positions, 4), torch.zeros(1, 2, positions, 4))]
        self.kv_thoughts = []
        self.states = None


class FakeCouncil:
    def __init__(self) -> None:
        self.asked: list[tuple[str, list]] = []

    def answer(self, text: str, memory: list) -> dict:
        self.asked.append((text, memory))
        return {"answer": {"answer": "yes", "quote": "", "known": True}, "stopped": None}


def test_the_answer_comes_from_the_memory_of_that_case():
    council, memories = FakeCouncil(), Memories(budget=10**9)
    first, second = [Message(3)], [Message(5)]
    memories.keep("council-aaaaaaaaaaaa", council, first)
    memories.keep("council-bbbbbbbbbbbb", council, second)
    r = memories.ask("council-aaaaaaaaaaaa", "Who signed?")
    assert r["answer"]["known"] and r["memory_bytes"] == size_of(first) == 2 * 2 * 3 * 4 * 4
    assert council.asked == [("Who signed?", first)]


def test_over_the_budget_the_oldest_case_goes_first():
    council = FakeCouncil()
    one = size_of([Message(10)])
    memories = Memories(budget=2 * one)
    for name in ("council-000000000001", "council-000000000002", "council-000000000003"):
        memories.keep(name, council, [Message(10)])
    assert list(memories.items) == ["council-000000000002", "council-000000000003"] and memories.used == 2 * one
    with pytest.raises(Rejected, match="review the contract again"):
        memories.ask("council-000000000001", "Who signed?")


def test_the_newest_case_stays_even_alone_over_the_budget():
    memories = Memories(budget=1)
    memories.keep("council-000000000001", FakeCouncil(), [Message(10)])
    assert list(memories.items) == ["council-000000000001"]


def test_text_messages_weigh_nothing():
    class Text:
        kv_read, kv_thoughts, states = [], [], None

    assert size_of([Text(), Text()]) == 0
