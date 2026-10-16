"""The seal: an Ed25519 digital signature by each role on the manifest of its latent message.

The fingerprint alone is not enough: whoever tampers with a message can recompute hashes and fingerprint. Not the
signature, because it needs the role's private key. Anyone with the public keys can verify.
"""

from __future__ import annotations

import base64
import os
from pathlib import Path

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey

from .check import Outcome
from .message import LatentMessage


def create_keys(private: Path, public: Path, roles: list[str]) -> None:
    """One pair per role, if not there already. Private keys go outside the repo (mode 600), public ones in it."""
    private.mkdir(parents=True, exist_ok=True)
    public.mkdir(parents=True, exist_ok=True)
    for role in roles:
        private_file = private / f"{role}.pem"
        if private_file.exists():
            continue
        key = Ed25519PrivateKey.generate()
        pem = key.private_bytes(
            serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()
        )
        descriptor = os.open(private_file, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "wb") as f:
            f.write(pem)
        (public / f"{role}.pem").write_bytes(
            key.public_key().public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo)
        )


def load_private(folder: Path, roles: list[str]) -> dict[str, Ed25519PrivateKey]:
    return {r: serialization.load_pem_private_key((folder / f"{r}.pem").read_bytes(), password=None) for r in roles}


def load_public(folder: Path) -> dict[str, Ed25519PublicKey]:
    return {f.stem: serialization.load_pem_public_key(f.read_bytes()) for f in sorted(folder.glob("*.pem"))}


def sign(message: LatentMessage, key: Ed25519PrivateKey) -> None:
    message.label["signature"] = base64.b64encode(key.sign(message.manifest())).decode("ascii")


class SealCheck:
    """The manifest is signed by the declared sender. It goes after the fingerprint check, which binds the bytes
    to the manifest."""

    name = "seal"

    def __init__(self, public_keys: dict[str, Ed25519PublicKey]) -> None:
        self.public_keys = public_keys

    def __call__(self, message: LatentMessage, chain: list[LatentMessage]) -> Outcome:
        key = self.public_keys.get(message.sender)
        if key is None:
            return Outcome(False, self.name, f"no public key for {message.sender}")
        value = message.label.get("signature")
        if not value:
            return Outcome(False, self.name, "message not signed")
        try:
            key.verify(base64.b64decode(value), message.manifest())
        except InvalidSignature:
            return Outcome(False, self.name, f"invalid signature for {message.sender}")
        return Outcome(True, self.name)
