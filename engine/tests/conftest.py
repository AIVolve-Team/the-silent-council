import os

import pytest
import torch

from engine import Agent, Engine, Model
from engine.message import TELEPATHY, LatentMessage, session_start_hash

NAME = os.environ.get("ENGINE_MODEL", "Qwen/Qwen3-0.6B")
REVISION = os.environ.get("ENGINE_REVISION", "c1899de289a04d12100db370d81485cdf75e47ca")

LEGAL = Agent("legal", "You are the legal expert. Read carefully the text you are given.")
FINANCE = Agent("finance", "You are the finance expert. Read carefully the text you are given.")
RISK = Agent("risk", "You are the risk expert. Read carefully the text you are given.")
RAPPORTEUR = Agent(
    "rapporteur", "You are the rapporteur. Answer briefly and precisely, using what you know from your colleagues."
)


@pytest.fixture(scope="session")
def model() -> Model:
    return Model(NAME, REVISION)


@pytest.fixture
def engine(model, tmp_path) -> Engine:
    return Engine(model, log_dir=tmp_path / "log", max_text_tokens=48)


def fake_message(number: int = 1, session: str = "s", start: int = 0, previous: str | None = None, seed: int = 0):
    """A latent message with random tensors, for the tests that do not load the model."""
    generator = torch.Generator().manual_seed(seed)
    kv = [
        (torch.randn(1, 2, 3, 4, generator=generator), torch.randn(1, 2, 3, 4, generator=generator)) for _ in range(2)
    ]
    thoughts = [
        (torch.randn(1, 2, 1, 4, generator=generator), torch.randn(1, 2, 1, 4, generator=generator)) for _ in range(2)
    ]
    label = {
        "sender": "legal",
        "recipient": "rapporteur",
        "session": session,
        "number": number,
        "previous_hash": previous or session_start_hash(session),
        "model": "fake",
        "revision": "0",
        "engine_version": "0.1.0",
        "dtype": "float32",
        "n_layer": 2,
        "mode": TELEPATHY,
        "read_text_hash": "x",
        "commitment": None,
        "start": start,
        "n_read": 3,
        "latent_steps": 1,
        "tokens_read": 3,
        "tokens_generated": 0,
    }
    return LatentMessage(label, kv, thoughts, torch.randn(2, 8, generator=generator)).close()
