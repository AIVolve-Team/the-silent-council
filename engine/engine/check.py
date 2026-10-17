"""The checks that run inside `deliver`: they answer "pass" or "stop, because…".

Each check is a function (message, chain already delivered) → Outcome. Seal and coherence are added to
the engine's list without changing the interface.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from .message import TELEPATHY, LatentMessage, session_start_hash, sha256


@dataclass(frozen=True)
class Outcome:
    passed: bool
    check: str
    reason: str = ""


Check = Callable[[LatentMessage, list[LatentMessage]], Outcome]


class FingerprintCheck:
    """Lossless: the bytes and the label are the ones from when the message was born."""

    name = "fingerprint"

    def __call__(self, message: LatentMessage, chain: list[LatentMessage]) -> Outcome:
        expected = message.label.get("block_hashes", {})
        for block, found in message.block_hashes().items():
            if expected.get(block) != found:
                return Outcome(False, self.name, f"block {block}: expected {expected.get(block)}, found {found}")
        found = sha256(message.manifest())
        if found != message.label.get("fingerprint"):
            return Outcome(
                False,
                self.name,
                f"label changed: expected fingerprint {message.label.get('fingerprint')}, found {found}",
            )
        return Outcome(True, self.name)


class ChainCheck:
    """The message is the right next one: same model and same session, sequence number,
    hash of the previous message and, in telepathy, start position right after the last piece."""

    name = "chain"

    def __init__(self, model: str, revision: str) -> None:
        self.model = model
        self.revision = revision

    def __call__(self, message: LatentMessage, chain: list[LatentMessage]) -> Outcome:
        e = message.label
        if (e["model"], e["revision"]) != (self.model, self.revision):
            return Outcome(False, self.name, f"different model: {e['model']}@{e['revision']}")
        # The institutional memory is a base: messages of its own session at the head of every chain, read once
        # and reused. Bases come first; the review's messages share one session among themselves.
        bases = [m for m in chain if m.label.get("base")]
        if e.get("base") and len(bases) != len(chain):
            return Outcome(False, self.name, "a base message after the review's messages")
        same = bases if e.get("base") else chain[len(bases) :]
        if same and e["session"] != same[0].label["session"]:
            return Outcome(False, self.name, f"different session: {e['session']}")
        if chain and e["mode"] != chain[0].label["mode"]:
            return Outcome(False, self.name, f"different mode: {e['mode']}")
        if e["number"] != len(chain) + 1:
            return Outcome(False, self.name, f"number {e['number']}, expected {len(chain) + 1}")
        previous = chain[-1].fingerprint if chain else session_start_hash(e["session"])
        if e["previous_hash"] != previous:
            return Outcome(False, self.name, "wrong hash of the previous message: message resent or out of order")
        if e["mode"] == TELEPATHY:
            start = sum(m.length for m in chain)
            if e["start"] != start:
                return Outcome(False, self.name, f"start {e['start']}, expected {start}: a piece does not move")
            if (message.n_read, message.n_thoughts) != (e["n_read"], e["latent_steps"]):
                return Outcome(False, self.name, "the positions do not match the label")
        return Outcome(True, self.name)
