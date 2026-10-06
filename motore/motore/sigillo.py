"""Il sigillo: firma digitale Ed25519 di ogni ruolo sul manifesto del suo messaggio latente.

L'impronta da sola non basta: chi manomette un messaggio può ricalcolare hash e impronta. La firma no, perché
serve la chiave privata del ruolo. Chiunque abbia le chiavi pubbliche può verificare.
"""

from __future__ import annotations

import base64
import os
from pathlib import Path

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey

from .controllo import Esito
from .messaggio import MessaggioLatente


def crea_chiavi(private: Path, pubbliche: Path, ruoli: list[str]) -> None:
    """Una coppia per ruolo, se non c'è già. Le private vanno fuori dal repo (permessi 600), le pubbliche nel repo."""
    private.mkdir(parents=True, exist_ok=True)
    pubbliche.mkdir(parents=True, exist_ok=True)
    for ruolo in ruoli:
        file_privato = private / f"{ruolo}.pem"
        if file_privato.exists():
            continue
        chiave = Ed25519PrivateKey.generate()
        pem = chiave.private_bytes(
            serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()
        )
        descrittore = os.open(file_privato, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descrittore, "wb") as f:
            f.write(pem)
        (pubbliche / f"{ruolo}.pem").write_bytes(
            chiave.public_key().public_bytes(
                serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo
            )
        )


def carica_private(cartella: Path, ruoli: list[str]) -> dict[str, Ed25519PrivateKey]:
    return {r: serialization.load_pem_private_key((cartella / f"{r}.pem").read_bytes(), password=None) for r in ruoli}


def carica_pubbliche(cartella: Path) -> dict[str, Ed25519PublicKey]:
    return {f.stem: serialization.load_pem_public_key(f.read_bytes()) for f in sorted(cartella.glob("*.pem"))}


def firma(messaggio: MessaggioLatente, chiave: Ed25519PrivateKey) -> None:
    messaggio.etichetta["firma"] = base64.b64encode(chiave.sign(messaggio.manifesto())).decode("ascii")


class ControlloSigillo:
    """Il manifesto è firmato dal mittente dichiarato. Si mette dopo il controllo dell'impronta, che lega i byte
    al manifesto."""

    nome = "sigillo"

    def __init__(self, pubbliche: dict[str, Ed25519PublicKey]) -> None:
        self.pubbliche = pubbliche

    def __call__(self, messaggio: MessaggioLatente, catena: list[MessaggioLatente]) -> Esito:
        chiave = self.pubbliche.get(messaggio.mittente)
        if chiave is None:
            return Esito(False, self.nome, f"nessuna chiave pubblica per {messaggio.mittente}")
        valore = messaggio.etichetta.get("firma")
        if not valore:
            return Esito(False, self.nome, "messaggio non firmato")
        try:
            chiave.verify(base64.b64decode(valore), messaggio.manifesto())
        except InvalidSignature:
            return Esito(False, self.nome, f"firma non valida per {messaggio.mittente}")
        return Esito(True, self.nome)
