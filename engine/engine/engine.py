"""The engine's commands: `think`, `write` and `deliver`, plus recomputing thoughts for the “Pre-registered eval” tests."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import torch
from transformers import DynamicCache

from .check import ChainCheck, Check, FingerprintCheck, Outcome
from .message import (
    TELEPATHY,
    TEXT,
    VERSION,
    LatentMessage,
    cache_from,
    cache_from_pieces,
    session_start_hash,
    sha256,
    slice_kv,
)
from .model import Generation, Model
from .seal import sign

# With these names LatentMAS's templates override the prompt: they are not used here.
FORBIDDEN_NAMES = {"planner", "critic", "refiner", "judger"}


@dataclass(frozen=True)
class Agent:
    name: str
    instructions: str

    def __post_init__(self) -> None:
        if self.name.lower() in FORBIDDEN_NAMES:
            raise ValueError(f"Forbidden role name: {self.name}")


@dataclass
class Handoff:
    outcome: Outcome
    copy: LatentMessage | None


def allowed_token_ids(allowed) -> list[int]:
    """lm-format-enforcer 0.11 returns a `TokenList`: a list of ids, or an int32 bitmask."""
    if not getattr(allowed, "use_bitmask", False):
        return list(getattr(allowed, "allowed_tokens", allowed))
    return allowed_mask(allowed).nonzero().flatten().tolist()


def allowed_mask(allowed) -> torch.Tensor:
    """The same `TokenList` as a boolean mask, without going through a Python list: inside a JSON string almost
    every token is allowed, and a 150,000-id list at every step slows generation down."""
    if not getattr(allowed, "use_bitmask", False):
        mask = torch.zeros(max(allowed.allowed_tokens, default=-1) + 1, dtype=torch.bool)
        mask[list(allowed.allowed_tokens)] = True
        return mask
    bits = (allowed.allowed_tokens.unsqueeze(1) >> torch.arange(32, dtype=torch.int32)) & 1
    return bits.flatten().bool()


def with_colleagues(text: str, received: list[LatentMessage]) -> str:
    """In text mode the receiver reads what the previous agents wrote, never what they read."""
    written = [m for m in received if m.text]
    if not written:
        return text
    lines = "\n\n".join(f"[{m.sender}]\n{m.text}" for m in written)
    return f"Messages from colleagues:\n\n{lines}\n\n---\n\n{text}"


class Engine:
    def __init__(
        self,
        model: Model,
        *,
        checks: list[Check] | None = None,
        signing_keys: dict | None = None,
        log_dir: Path | None = None,
        max_text_tokens: int = 512,
    ) -> None:
        self.model = model
        self.checks: list[Check] = [
            FingerprintCheck(),
            ChainCheck(model.name, model.revision),
            *(checks or []),
        ]
        self.signing_keys = signing_keys or {}
        self.log_dir = log_dir
        self.max_text_tokens = max_text_tokens
        self._tokenizer_data = None

    # --- think ----------------------------------------------------------------------------------------

    def think(
        self,
        agent: Agent,
        text: str,
        received: list[LatentMessage],
        *,
        session: str,
        latent_steps: int = 10,
        mode: str = TELEPATHY,
        recipient: str | None = None,
    ) -> LatentMessage:
        """The agent reads its text on top of the received messages and returns its latent message.

        In text mode it writes its analysis instead, at most `max_text_tokens` tokens.
        """
        if mode == TEXT:
            prompt = self.model.prompt(agent.instructions, with_colleagues(text, received), thinking=False)
            written = self.model.generate(DynamicCache(), self.model.encode(prompt), self.max_text_tokens)
            label = self._label(agent, session, received, recipient, mode, prompt)
            label |= {"start": None, "n_read": 0, "latent_steps": 0}
            label |= {"tokens_read": written.tokens_read, "tokens_generated": written.tokens_generated}
            return self._close(LatentMessage(label, text=written.text))

        cache = cache_from(received)
        start = cache.get_seq_length()
        prompt = self.model.prompt(agent.instructions, text, thinking=True)
        ids = self.model.encode(prompt)
        states = self.model.latent_steps(cache, self.model.read(ids, cache), latent_steps)
        n = ids.shape[1]
        label = self._label(agent, session, received, recipient, mode, prompt)
        label |= {"start": start, "n_read": n, "latent_steps": latent_steps}
        label |= {"tokens_read": n, "tokens_generated": 0}
        message = LatentMessage(
            label,
            slice_kv(cache, start, start + n),
            slice_kv(cache, start + n, start + n + latent_steps),
            states,
        )
        return self._close(message)

    def _label(self, agent, session, received, recipient, mode, prompt) -> dict:
        return {
            "sender": agent.name,
            "recipient": recipient,
            "session": session,
            "number": len(received) + 1,
            "previous_hash": received[-1].fingerprint if received else session_start_hash(session),
            "model": self.model.name,
            "revision": self.model.revision,
            "engine_version": VERSION,
            "dtype": str(self.model.dtype).removeprefix("torch."),
            "n_layer": self.model.n_layer,
            "mode": mode,
            "read_text_hash": sha256(prompt.encode("utf-8")),
            "commitment": None,
        }

    def _close(self, message: LatentMessage) -> LatentMessage:
        message.close()
        if message.sender in self.signing_keys:
            sign(message, self.signing_keys[message.sender])
        return message

    def with_commitment(self, message: LatentMessage, commitment: dict) -> LatentMessage:
        """Puts the commitment in the label, then closes and signs again: so the commitment is sealed."""
        new = message.copy()
        new.label["commitment"] = commitment
        return self._close(new)

    # --- write ----------------------------------------------------------------------------------------

    def write(
        self,
        agent: Agent,
        text: str,
        received: list[LatentMessage],
        *,
        mode: str = TELEPATHY,
        schema: dict | None = None,
        field_order: bool = False,
        max_spaces: int | None = None,
        max_tokens: int | None = None,
        observe: list[int] | None = None,
    ) -> Generation:
        """The agent writes starting from the received messages: note, verdict or decision. It works on a copy of
        the memory.

        With a JSON schema the decoding is constrained. `field_order` enforces the order of `required` (e.g.
        objections first, then the verdict); `max_spaces` caps consecutive whitespace: with 1 the spaces between
        words stay and indentation, which costs tokens, goes away.
        `observe` records at every step the logprobs of those tokens, for confidence.
        """
        if mode == TEXT:
            cache, text = DynamicCache(), with_colleagues(text, received)
        else:
            cache = cache_from(received)
        ids = self.model.encode(self.model.prompt(agent.instructions, text, thinking=False))
        allowed = None if schema is None else self._constraint(schema, field_order, max_spaces)
        return self.model.generate(cache, ids, max_tokens or self.max_text_tokens, allowed=allowed, observe=observe)

    def _constraint(self, schema: dict, field_order: bool, max_spaces: int | None):
        import sys

        try:
            from transformers.tokenization_utils import PreTrainedTokenizerBase  # noqa: F401
        except ImportError:
            # lm-format-enforcer 0.11.3 imports PreTrainedTokenizerBase from a module that transformers 5 removed
            import transformers.tokenization_utils_base as base

            sys.modules["transformers.tokenization_utils"] = base
        from lmformatenforcer import CharacterLevelParserConfig, JsonSchemaParser, TokenEnforcer
        from lmformatenforcer.integrations.transformers import build_token_enforcer_tokenizer_data

        if self._tokenizer_data is None:
            self._tokenizer_data = build_token_enforcer_tokenizer_data(self.model.tokenizer)
        parser = JsonSchemaParser(schema)
        enforcer = TokenEnforcer(self._tokenizer_data, parser)
        # lm-format-enforcer 0.11.3: TokenEnforcer replaces the parser's configuration with one that has only the
        # tokenizer's alphabet, so field order and the whitespace cap go back to their defaults.
        # The right configuration is put back afterwards, with the same alphabet.
        config = CharacterLevelParserConfig(
            alphabet=self._tokenizer_data.tokenizer_alphabet, force_json_field_order=field_order
        )
        if max_spaces is not None:
            config.max_consecutive_whitespaces = max_spaces
        parser.config = config
        return lambda sequence: allowed_mask(enforcer.get_allowed_tokens(sequence))

    # --- deliver --------------------------------------------------------------------------------------

    def deliver(self, message: LatentMessage, chain: list[LatentMessage]) -> Handoff:
        """Takes the message to the recipient, always through the checks. The recipient gets a copy, and only if
        they all say "pass"."""
        for check in self.checks:
            outcome = check(message, chain)
            if not outcome.passed:
                self._log_incident(message, outcome)
                return Handoff(outcome, None)
        return Handoff(Outcome(True, "handoff"), message.copy())

    def verify_chain(self, chain: list[LatentMessage]) -> Outcome:
        """All the checks on the whole chain, before the final result goes out."""
        for i, message in enumerate(chain):
            for check in self.checks:
                outcome = check(message, chain[:i])
                if not outcome.passed:
                    self._log_incident(message, outcome)
                    return outcome
        return Outcome(True, "whole chain")

    def _log_incident(self, message: LatentMessage, outcome: Outcome) -> None:
        """Incident log entry and the whole message saved as evidence."""
        if self.log_dir is None:
            return
        self.log_dir.mkdir(parents=True, exist_ok=True)
        now = datetime.now(UTC)
        session = re.sub(r"[^\w.-]", "_", str(message.label.get("session")))
        name = f"incident-{session}-{message.label.get('number')}-{now:%Y%m%dT%H%M%S%f}"
        entry = {"time": now.isoformat(), "check": outcome.check, "reason": outcome.reason}
        entry["label"] = message.label
        (self.log_dir / f"{name}.json").write_text(json.dumps(entry, indent=2, ensure_ascii=False))
        message.save(self.log_dir / f"{name}.safetensors", full=True)

    # --- “Pre-registered eval” tests ------------------------------------------------------------------------------------

    @torch.no_grad()
    def recompute_thoughts(
        self,
        message: LatentMessage,
        chain: list[LatentMessage],
        *,
        states_from: torch.Tensor | None = None,
        origin: str | None = None,
    ) -> LatentMessage:
        """Redoes the KV of the latent steps from the hidden states, in the message's position.

        With the message's own states it must give back its KV. With another message's it is the
        "thoughts of another contract" test: the reading stays, the thoughts change.
        """
        states = message.states if states_from is None else states_from
        steps = message.n_thoughts
        if states.shape[0] != steps + 1:
            raise ValueError(f"{steps + 1} states needed, there are {states.shape[0]}")
        cache = cache_from_pieces([p for m in chain for p in (m.kv_read, m.kv_thoughts)] + [message.kv_read])
        start = cache.get_seq_length()
        for t in range(steps):
            self.model.latent_step(states[t : t + 1].to(self.model.device), cache)
        new = message.copy()
        new.kv_thoughts = slice_kv(cache, start, start + steps)
        new.states = states.clone()
        if states_from is not None:
            new.label["thoughts_from"] = origin or "another message"
        return self._close(new)
