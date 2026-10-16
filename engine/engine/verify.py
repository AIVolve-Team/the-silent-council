"""Verification of saved latent messages: fingerprint, signature and chain, even without the engine.

Usage: python -m engine.verify <folder with the .safetensors> [--public <folder of the public keys>]

It also works on files saved without KV: then it checks the states, the text and the label, and the chain is
verified all the same, because every message carries the hash of the previous one.
"""

from __future__ import annotations

import argparse
import sys
from collections import defaultdict
from pathlib import Path

from .check import Outcome
from .message import LatentMessage, session_start_hash, sha256
from .seal import SealCheck, load_public


def verify_message(message: LatentMessage, seal: SealCheck | None) -> Outcome:
    if sha256(message.manifest()) != message.label.get("fingerprint"):
        return Outcome(False, "fingerprint", "label changed")
    expected = message.label.get("block_hashes", {})
    found = message.block_hashes()
    present = ["states", "text"] + (["read", "thoughts"] if message.kv_read else [])
    for block in present:
        if expected.get(block) != found[block]:
            return Outcome(False, "fingerprint", f"block {block} changed")
    if seal is not None:
        return seal(message, [])
    return Outcome(True, "fingerprint")


def verify_archive(files: list[Path], public: Path | None = None) -> list[tuple[str, Outcome]]:
    seal = SealCheck(load_public(public)) if public else None
    sessions: dict[str, list[tuple[Path, LatentMessage]]] = defaultdict(list)
    for path in files:
        message = LatentMessage.load(path)
        sessions[message.label["session"]].append((path, message))
    results = []
    for session, entries in sorted(sessions.items()):
        entries.sort(key=lambda entry: entry[1].label["number"])
        previous = session_start_hash(session)
        for expected, (path, message) in enumerate(entries, start=1):
            outcome = verify_message(message, seal)
            if outcome.passed and message.label["number"] != expected:
                outcome = Outcome(False, "chain", f"message {expected} is missing")
            elif outcome.passed and message.label["previous_hash"] != previous:
                outcome = Outcome(False, "chain", "does not follow the previous message")
            results.append((f"{session} #{message.label['number']} ({path.name})", outcome))
            previous = message.fingerprint
    return results


def main() -> None:
    parser = argparse.ArgumentParser(description="Verifies the saved latent messages.")
    parser.add_argument("folder", type=Path)
    parser.add_argument("--public", type=Path, help="folder of the public keys, to check the signatures")
    args = parser.parse_args()
    results = verify_archive(sorted(args.folder.glob("*.safetensors")), args.public)
    for name, outcome in results:
        print(f"{'ok   ' if outcome.passed else 'STOP '} {name}" + ("" if outcome.passed else f": {outcome.reason}"))
    if not results:
        print("No messages found.")
    sys.exit(0 if results and all(outcome.passed for _, outcome in results) else 1)


if __name__ == "__main__":
    main()
