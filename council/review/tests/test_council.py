"""The council on a contract of a few lines, with Qwen3-0.6B: in telepathy and in text."""

import pytest
from engine import TELEPATHY, TEXT, Engine, Model

from review import BENCHMARK, Council
from review.run import MODELS

pytestmark = pytest.mark.model

# An Italian contract, like the demo set's.
CONTRACT = """CONTRATTO DI FORNITURA

Art. 1 – Oggetto
Il Fornitore fornisce al Cliente componenti meccanici.

Art. 2 – Prezzi e pagamenti
Il Cliente acquista ogni anno componenti per almeno € 50.000,00. Se non li raggiunge, paga la differenza.

Art. 3 – Esclusiva di acquisto
Il Cliente compra i componenti solo dal Fornitore, per tutta la durata del contratto.

Art. 4 – Durata e recesso
Il contratto dura due anni. Il Fornitore può recedere in qualsiasi momento con 30 giorni di preavviso.
"""


@pytest.fixture(scope="module")
def engine():
    return Engine(Model("Qwen/Qwen3-0.6B", MODELS["Qwen/Qwen3-0.6B"]))


@pytest.mark.parametrize("mode", [TELEPATHY, TEXT])
def test_valid_notes_and_verdict(engine, mode):
    council = Council(engine, BENCHMARK["demo"], mode=mode, latent_steps=2)
    review = council.review("trial", CONTRACT)
    assert review.stopped is None and review.split["mode"] == "headings"
    assert set(review.notes) == {"legal", "finance", "risk"}
    assert all(n.valid and len(n.data["flag"]) == len(BENCHMARK["cuad"].of_role(r)) for r, n in review.notes.items())
    verdict = review.verdict
    assert verdict.valid and len(verdict.data["flag"]) == 19
    assert verdict.data["recommendation"] in ("sign", "negotiate", "do not sign")
    assert set(verdict.p_yes) == set(verdict.data["flag"])
    assert review.tokens_generated > verdict.tokens_generated
    assert (review.latent_positions == 6) == (mode == TELEPATHY) and review.realign


def test_a_question_is_answered_from_the_memory_of_the_review(engine):
    """after the review the rapporteur answers from the experts' memory, reading only the question; a changed
    byte in the memory and there is no answer."""
    council = Council(engine, BENCHMARK["demo"], mode=TELEPATHY, latent_steps=0)
    review = council.review("trial", CONTRACT)
    assert review.stopped is None and len(council.memory) == 3
    r = council.answer("Per quanti anni dura il contratto?", council.memory)
    assert r["stopped"] is None and r["answer"] is not None and set(r["answer"]) == {"answer", "quote", "known"}
    contract_tokens = len(engine.model.tokenizer.encode(CONTRACT, add_special_tokens=False))
    assert r["tokens_read"] < 300 and r["fingerprints"] == review.fingerprints, (r["tokens_read"], contract_tokens)
    council.memory[1].kv_read[0][0].view(-1)[0] += 1.0
    stopped = council.answer("Per quanti anni dura il contratto?", council.memory)
    assert stopped["answer"] is None and stopped["stopped"]["check"] == "fingerprint"


def test_a_visual_question_is_answered_with_the_objects_from_the_memory(engine):
    """with `visual` the answer has the objects with page and box, within the schema's bounds; without it the
    answer is the one of before."""
    council = Council(engine, BENCHMARK["demo"], mode=TELEPATHY, latent_steps=0)
    review = council.review("trial", CONTRACT)
    assert review.stopped is None
    r = council.answer("Who signed? Which signature blocks are empty?", council.memory, visual=True)
    assert r["stopped"] is None and r["answer"] is not None and set(r["answer"]) == {"answer", "objects", "known"}
    assert len(r["answer"]["objects"]) <= 8 and r["fingerprints"] == review.fingerprints
    for o in r["answer"]["objects"]:
        assert set(o) == {"page", "type", "box_2d", "text"} and len(o["box_2d"]) == 4
        assert 1 <= o["page"] and all(0 <= v <= 1000 for v in o["box_2d"])
    plain = council.answer("Per quanti anni dura il contratto?", council.memory)
    assert set(plain["answer"]) == {"answer", "quote", "known"}


@pytest.fixture
def pages(engine, monkeypatch):
    """Two page images and a model that takes them: Qwen3-0.6B does not see images, so here a page is its placeholder
    only. What is checked is the chain the visual expert heads, not what it sees (the probe, on Gemma 4)."""
    from PIL import Image

    model = type(engine.model)
    monkeypatch.setattr(model, "image_token", property(lambda self: "<page>"))
    monkeypatch.setattr(model, "encode_with_pages", lambda self, text, pages: (self.encode(text), None))
    return [Image.new("RGB", (8, 8), "white"), Image.new("RGB", (8, 8), "black")]


@pytest.mark.parametrize("mode", [TELEPATHY, TEXT])
def test_the_visual_expert_heads_the_chain_and_the_experts_follow(engine, pages, mode):
    """in the visual route the visual expert is the first message of the review; the experts' notes come
    from their own messages after it, and the questions are answered from the whole chain."""
    council = Council(engine, BENCHMARK["demo"], mode=mode, latent_steps=0)
    review = council.review("trial", CONTRACT, visual=("Look at the pages.", [2, 5], pages))
    assert review.stopped is None and review.verdict.valid
    assert [m.sender for m in council.memory] == ["visual", "legal", "finance", "risk"]
    first = council.memory[0].label
    assert first["pages"] == 2 and len(first["pages_hash"]) == 64
    assert set(review.notes) == {"legal", "finance", "risk"} and all(n.valid for n in review.notes.values())
    assert review.visual["pages"] == [2, 5] and review.visual["delivered"]
    assert (review.visual["report"] is not None) == (mode == TEXT)
    r = council.answer("Who signed?", council.memory, visual=True)
    assert r["stopped"] is None and r["fingerprints"] == review.fingerprints


def test_a_question_passes_the_checks_with_the_institutional_memory(engine):
    """the experts' messages follow the institutional memory, so the memory of the review starts with
    it, or the first message would point at nothing and every question would be stopped."""
    from engine import Agent

    base = [
        engine.think(
            Agent("playbook", "Keep the playbook."),
            "Playbook: never accept a unilateral withdrawal.",
            [],
            session="institution/v1",
            latent_steps=0,
            base=True,
        )
    ]
    council = Council(engine, BENCHMARK["demo"], mode=TELEPATHY, latent_steps=0)
    review = council.review("trial", CONTRACT, base=base)
    assert review.stopped is None and council.memory[0] is not None and council.memory[0].label.get("base")
    r = council.answer("Per quanti anni dura il contratto?", council.memory)
    assert r["stopped"] is None and r["answer"] is not None
