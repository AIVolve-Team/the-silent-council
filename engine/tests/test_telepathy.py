"""Tests with the real model (small Qwen3): the "Done when" list of “Telepathic engine”."""

import json
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest
import torch

from engine import TEXT, Engine, FingerprintCheck, LatentMessage, Outcome, Relay
from engine.seal import SealCheck, create_keys, load_private, load_public

from .conftest import FINANCE, LEGAL, NAME, RAPPORTEUR, REVISION, RISK

pytestmark = pytest.mark.model

QUESTION = "What is the warehouse unlock code? Answer with the number only."


def code(number: str) -> str:
    return f"Internal note. The warehouse unlock code is {number}. Do not share it with anyone outside the team."


def test_the_channel_carries_content(engine):
    real = engine.think(LEGAL, code("4721"), [], session="real", latent_steps=4)
    other = engine.think(LEGAL, code("9386"), [], session="other", latent_steps=4)
    with_real = engine.write(RAPPORTEUR, QUESTION, [real], max_tokens=24).text
    with_other = engine.write(RAPPORTEUR, QUESTION, [other], max_tokens=24).text
    without = engine.write(RAPPORTEUR, QUESTION, [], max_tokens=24).text
    assert "4721" in with_real
    assert "9386" in with_other and "4721" not in with_other
    assert "4721" not in without


def test_relay_in_telepathy_and_in_text(engine):
    texts = {
        "legal": "The supplier is Alfa Componenti.",
        "finance": code("4721"),
        "risk": "Delivery is scheduled for 30 April.",
        "rapporteur": QUESTION,
    }
    for mode in ("telepathy", TEXT):
        outcome = Relay(engine, [LEGAL, FINANCE, RISK], RAPPORTEUR, mode=mode, latent_steps=3).run(
            f"relay-{mode}", texts, max_tokens=24
        )
        assert outcome.stopped is None and outcome.final is not None and len(outcome.messages) == 3
        assert [m.label["number"] for m in outcome.messages] == [1, 2, 3]
        if mode == TEXT:
            assert all(m.text and m.kv_read == [] for m in outcome.messages)
            assert outcome.latent_positions == 0
        else:
            assert all(m.text is None and m.n_thoughts == 3 for m in outcome.messages)
            assert outcome.latent_positions == 9
            assert sum(m.label["tokens_generated"] for m in outcome.messages) == 0
            assert "4721" in outcome.final.text


def test_lossless_from_file_in_another_process(engine, tmp_path):
    message = engine.think(LEGAL, code("4721"), [], session="file", latent_steps=4)
    message.save(tmp_path / "m.safetensors", full=True)
    here = engine.write(RAPPORTEUR, QUESTION, [message], max_tokens=8)
    script = f"""
import json, sys
sys.path.insert(0, {str(Path(__file__).parents[1])!r})
from engine import Model, Engine, LatentMessage, FingerprintCheck
from tests.conftest import RAPPORTEUR
model = Model({NAME!r}, {REVISION!r})
m = LatentMessage.load({str(tmp_path / "m.safetensors")!r}, model.device)
assert FingerprintCheck()(m, []).passed
g = Engine(model).write(RAPPORTEUR, {QUESTION!r}, [m], max_tokens=8)
print(json.dumps({{"text": g.text, "logprob": [p.logprob for p in g.steps]}}))
"""
    output = subprocess.run([sys.executable, "-c", script], capture_output=True, text=True, check=True, env=os.environ)
    there = json.loads(output.stdout.strip().splitlines()[-1])
    assert there["text"] == here.text
    assert there["logprob"] == [p.logprob for p in here.steps]


def test_changed_byte_stops_delivery_and_evidence_remains(engine):
    message = engine.think(LEGAL, code("4721"), [], session="tampered", latent_steps=2)
    message.kv_thoughts[0][1].view(-1)[0] += 1
    handoff = engine.deliver(message, [])
    assert not handoff.outcome.passed and handoff.copy is None and handoff.outcome.check == "fingerprint"
    evidence = sorted(engine.log_dir.iterdir())
    assert [p.suffix for p in evidence] == [".json", ".safetensors"]
    assert json.loads(evidence[0].read_text())["check"] == "fingerprint"


def test_writing_does_not_change_the_delivered_message(engine):
    message = engine.think(LEGAL, code("4721"), [], session="copy", latent_steps=2)
    delivered = engine.deliver(message, []).copy
    engine.write(RAPPORTEUR, QUESTION, [delivered], max_tokens=8)
    assert FingerprintCheck()(delivered, []).passed


def test_with_zero_steps_the_reading_remains(engine):
    message = engine.think(LEGAL, code("4721"), [], session="m0", latent_steps=0)
    assert message.n_read > 0 and message.n_thoughts == 0 and message.states.shape[0] == 1
    assert "4721" in engine.write(RAPPORTEUR, QUESTION, [message], max_tokens=24).text


def test_recomputing_thoughts(engine):
    first = engine.think(LEGAL, code("4721"), [], session="recompute", latent_steps=4)
    second = engine.think(FINANCE, "The supplier is Alfa Componenti.", [first], session="recompute", latent_steps=4)
    redone = engine.recompute_thoughts(second, [first])
    difference = max(
        (a - b).abs().max().item() for x, y in zip(second.kv_thoughts, redone.kv_thoughts) for a, b in zip(x, y)
    )
    print(f"recompute with its own states: max difference {difference}")
    assert difference == 0.0
    assert redone.fingerprint == second.fingerprint

    donor = engine.think(FINANCE, "The supplier is Beta Servizi.", [], session="donor", latent_steps=4)
    swapped = engine.recompute_thoughts(second, [first], states_from=donor.states, origin="donor#1")
    assert swapped.label["thoughts_from"] == "donor#1"
    assert not torch.equal(swapped.kv_thoughts[0][0], second.kv_thoughts[0][0])
    assert torch.equal(swapped.kv_read[0][0], second.kv_read[0][0])
    assert engine.deliver(swapped, [first]).outcome.passed


def test_writing_with_a_json_schema(engine):
    message = engine.think(LEGAL, code("4721"), [], session="schema", latent_steps=2)
    schema = {
        "type": "object",
        "properties": {"code": {"type": "string"}, "should_flag": {"type": "boolean"}},
        "required": ["code", "should_flag"],
    }
    written = engine.write(
        RAPPORTEUR,
        "Report the code and tell me whether it should be flagged. Answer in JSON.",
        [message],
        schema=schema,
        max_tokens=40,
    )
    data = json.loads(written.text)
    assert set(data) == {"code", "should_flag"} and isinstance(data["should_flag"], bool)
    assert all(p.logprob <= 0 and len(p.alternatives) == 5 for p in written.steps)


def test_a_check_that_stops_blocks_the_relay(model, tmp_path):
    def stop_finance(message, chain):
        if message.sender == "finance":
            return Outcome(False, "test", "test check")
        return Outcome(True, "test")

    engine = Engine(model, checks=[stop_finance], log_dir=tmp_path / "log", max_text_tokens=16)
    texts = {"legal": "A", "finance": "B", "risk": "C", "rapporteur": QUESTION}
    outcome = Relay(engine, [LEGAL, FINANCE, RISK], RAPPORTEUR, latent_steps=1).run("stop", texts)
    assert outcome.final is None and outcome.stopped.check == "test"
    assert [m.sender for m in outcome.messages] == ["legal"]
    assert any(p.suffix == ".json" for p in (tmp_path / "log").iterdir())


def test_the_seal_stops_whoever_tampers_and_recomputes_the_fingerprints(model, tmp_path):
    roles = ["legal", "finance", "risk"]
    create_keys(tmp_path / "private", tmp_path / "public", roles)
    engine = Engine(
        model,
        signing_keys=load_private(tmp_path / "private", roles),
        checks=[SealCheck(load_public(tmp_path / "public"))],
        log_dir=tmp_path / "log",
    )
    texts = {
        "legal": "The supplier is Alfa Componenti.",
        "finance": code("4721"),
        "risk": "C",
        "rapporteur": QUESTION,
    }
    relay = Relay(engine, [LEGAL, FINANCE, RISK], RAPPORTEUR, latent_steps=2)
    assert relay.run("seal", texts, max_tokens=24).stopped is None

    def tamper(message: LatentMessage) -> None:
        message.kv_read[3][0].view(-1)[0] += 1
        message.label["block_hashes"] = message.block_hashes()
        message.label["fingerprint"] = message.copy().close().fingerprint

    outcome = relay.run("seal-attack", texts, max_tokens=24, attacks={"finance": tamper})
    assert outcome.stopped.check == "seal" and "invalid signature for finance" in outcome.stopped.reason
    assert [m.sender for m in outcome.messages] == ["legal"]


def test_schema_with_field_order_and_observed_tokens(engine):
    true = engine.model.tokenizer.encode(" true", add_special_tokens=False)
    false = engine.model.tokenizer.encode(" false", add_special_tokens=False)
    schema = {
        "type": "object",
        "properties": {"objections": {"type": "string", "maxLength": 60}, "code_present": {"type": "boolean"}},
        "required": ["objections", "code_present"],
    }
    message = engine.think(LEGAL, code("4721"), [], session="order", latent_steps=2)
    written = engine.write(
        RAPPORTEUR,
        "Fill in the JSON: first the objections, then whether the code is present.",
        [message],
        schema=schema,
        field_order=True,
        max_spaces=1,
        max_tokens=60,
        observe=true + false,
    )
    assert written.text.index('"objections"') < written.text.index('"code_present"')
    assert not re.search(r"\s\s", written.text), written.text
    assert all(set(p.observed) == set(true + false) for p in written.steps)
