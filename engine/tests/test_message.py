"""Tests without the model: fingerprint, file, chain and signature."""

import torch

from engine import ChainCheck, FingerprintCheck, LatentMessage, SealCheck
from engine.seal import create_keys, load_private, load_public, sign

from .conftest import fake_message


def test_one_changed_byte_shows():
    message = fake_message()
    assert FingerprintCheck()(message, []).passed
    message.kv_read[1][0].view(-1)[5] += 1e-6
    outcome = FingerprintCheck()(message, [])
    assert not outcome.passed and "read" in outcome.reason


def test_changed_label_shows():
    message = fake_message()
    message.label["sender"] = "finance"
    assert not FingerprintCheck()(message, []).passed


def test_saved_and_reloaded_lossless(tmp_path):
    message = fake_message()
    message.save(tmp_path / "m.safetensors", full=True)
    reloaded = LatentMessage.load(tmp_path / "m.safetensors")
    assert reloaded.label == message.label
    for (k1, v1), (k2, v2) in zip(message.kv_read + message.kv_thoughts, reloaded.kv_read + reloaded.kv_thoughts):
        assert torch.equal(k1, k2) and torch.equal(v1, v2)
    assert FingerprintCheck()(reloaded, []).passed


def test_reduced_save_keeps_label_and_states(tmp_path):
    message = fake_message()
    message.save(tmp_path / "m.safetensors")
    reloaded = LatentMessage.load(tmp_path / "m.safetensors")
    assert reloaded.kv_read == [] and torch.equal(reloaded.states, message.states)
    assert reloaded.label["block_hashes"]["states"] == reloaded.block_hashes()["states"]


def test_the_copy_is_independent():
    message = fake_message()
    copy = message.copy()
    copy.kv_read[0][0].zero_()
    assert FingerprintCheck()(message, []).passed


def test_chain():
    check = ChainCheck("fake", "0")
    first = fake_message()
    assert check(first, []).passed
    second = fake_message(number=2, start=first.length, previous=first.fingerprint, seed=1)
    assert check(second, [first]).passed
    resent = fake_message(number=2, start=first.length, previous="other", seed=1)
    assert "previous" in check(resent, [first]).reason
    moved = fake_message(number=2, start=first.length + 1, previous=first.fingerprint, seed=1)
    assert "does not move" in check(moved, [first]).reason
    out_of_order = fake_message(number=3, start=first.length, previous=first.fingerprint, seed=1)
    assert "number" in check(out_of_order, [first]).reason
    other_session = fake_message(number=2, session="t", start=first.length, previous=first.fingerprint)
    assert "session" in check(other_session, [first]).reason
    assert "model" in ChainCheck("other", "0")(first, []).reason


def test_signature(tmp_path):
    create_keys(tmp_path / "private", tmp_path / "public", ["legal", "finance"])
    private = load_private(tmp_path / "private", ["legal", "finance"])
    check = SealCheck(load_public(tmp_path / "public"))
    assert (tmp_path / "private" / "legal.pem").stat().st_mode & 0o777 == 0o600

    message = fake_message()
    assert check(message, []).reason == "message not signed"
    sign(message, private["legal"])
    assert check(message, []).passed

    # Whoever tampers can recompute hashes and fingerprint, but not the signature.
    message.kv_read[0][0].view(-1)[0] += 1
    message.label["block_hashes"] = message.block_hashes()
    assert FingerprintCheck()(message.copy().close(), []).passed
    assert "invalid signature" in check(message, []).reason

    fake = fake_message()
    sign(fake, private["finance"])
    assert "invalid signature for legal" in check(fake, []).reason


def test_allowed_tokens_from_list_and_from_bitmask():
    from lmformatenforcer.tokenlist import TokenList

    from engine.engine import allowed_token_ids

    for bitmask in (False, True):
        allowed = TokenList(use_bitmask=bitmask, vocab_size=70)
        allowed.extend([0, 31, 32, 69])
        assert allowed_token_ids(allowed) == [0, 31, 32, 69]


def test_verify_archive_even_without_kv(tmp_path):
    from engine.verify import verify_archive

    create_keys(tmp_path / "private", tmp_path / "public", ["legal"])
    key = load_private(tmp_path / "private", ["legal"])["legal"]
    first = fake_message()
    sign(first, key)
    second = fake_message(number=2, start=first.length, previous=first.fingerprint, seed=1)
    sign(second, key)
    first.save(tmp_path / "1.safetensors")
    second.save(tmp_path / "2.safetensors", full=True)
    files = [tmp_path / "1.safetensors", tmp_path / "2.safetensors"]
    assert all(outcome.passed for _, outcome in verify_archive(files, tmp_path / "public"))

    # Without the first message the chain does not add up.
    assert not verify_archive(files[1:], tmp_path / "public")[0][1].passed

    # A message re-signed with another key does not pass.
    create_keys(tmp_path / "others", tmp_path / "others-public", ["legal"])
    sign(second, load_private(tmp_path / "others", ["legal"])["legal"])
    second.save(tmp_path / "2.safetensors", full=True)
    assert "invalid signature" in verify_archive(files, tmp_path / "public")[1][1].reason


def test_allowed_mask_from_list_and_from_bits():
    from lmformatenforcer.tokenlist import TokenList

    from engine.engine import allowed_mask

    for bits in (False, True):
        allowed = TokenList(use_bitmask=bits, vocab_size=70)
        allowed.extend([0, 31, 32, 69])
        assert allowed_mask(allowed).nonzero().flatten().tolist() == [0, 31, 32, 69]


def test_field_order_and_spaces_respected_by_the_constraint():
    """lm-format-enforcer 0.11.3 loses the parser's configuration: the engine puts it back."""
    from transformers import AutoTokenizer

    from engine.engine import Engine

    from .conftest import NAME, REVISION

    class FakeModel:
        tokenizer = AutoTokenizer.from_pretrained(NAME, revision=REVISION)

    engine = Engine.__new__(Engine)
    engine.model, engine._tokenizer_data = FakeModel(), None
    schema = {
        "type": "object",
        "properties": {"a": {"type": "boolean"}, "b": {"type": "boolean"}, "c": {"type": "string"}},
        "required": ["a", "b", "c"],
    }
    tok = FakeModel.tokenizer
    constraint = engine._constraint(schema, field_order=True, max_spaces=1)
    sequence = tok.encode("Answer:", add_special_tokens=False)
    constraint(sequence)
    # One token at a time, as in generation: the library keeps the state per prefix.
    for t in tok.encode('{"a": true,', add_special_tokens=False):
        assert constraint(sequence)[t], tok.decode([t])
        sequence.append(t)
    allowed = [tok.decode([i]) for i in constraint(sequence).nonzero().flatten().tolist()]
    keys = {a.strip() for a in allowed if a.strip().startswith('"')}
    assert '"c' not in keys and ('"b' in keys or keys == {'"'})
    assert not [a for a in allowed if a.strip() == "" and len(a) > 1]
