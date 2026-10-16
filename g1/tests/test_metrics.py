import os

import pytest
from engine import Engine, Model

from g1 import metrics

NAME = os.environ.get("G1_MODEL", "Qwen/Qwen3-0.6B")
REVISION = os.environ.get("G1_REVISION", "c1899de289a04d12100db370d81485cdf75e47ca")

pytestmark = pytest.mark.model


@pytest.fixture(scope="module")
def engine():
    return Engine(Model(NAME, REVISION), max_text_tokens=16)


def test_the_long_text_has_at_least_the_requested_tokens(engine):
    text = metrics.long_text(engine.model.tokenizer, 4000)
    n = len(engine.model.tokenizer(text).input_ids)
    assert 4000 <= n < 4400


def test_the_metrics_on_the_long_text(engine):
    result = metrics.measure_engine(engine, tokens=600)
    assert result["tokens_read_first_agent"] >= 600
    assert result["message_kv_gb"] > 0
    assert result["fingerprint_seconds"] > 0
    assert result["recompute_identical"] is True  # in fp32 on the Mac the difference is 0 (engine README)
    assert result["stopped"] is None
