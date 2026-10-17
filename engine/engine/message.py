"""The latent message: an agent's piece of cache, its hidden states and a label.

The fingerprint covers everything: the hashes of the block bytes are in the label, and the fingerprint is the
SHA-256 of the manifest, i.e. of the label in canonical JSON without fingerprint and signature. The signature, if
any, is on the same manifest.
"""

from __future__ import annotations

import copy
import hashlib
import json
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path

import torch
from safetensors import safe_open
from safetensors.torch import save_file
from transformers import DynamicCache

VERSION = "0.1.0"
TELEPATHY = "telepathy"
TEXT = "text"

# For each layer, K and V of shape [1, kv_heads, positions, head_dim].
KV = list[tuple[torch.Tensor, torch.Tensor]]


def canonical_json(data: object) -> bytes:
    return json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def session_start_hash(session: str) -> str:
    """The "previous message" of the first message of a session."""
    return sha256(canonical_json({"session_start": session}))


def hash_tensors(tensors: Iterable[torch.Tensor]) -> str:
    """SHA-256 of the canonical bytes: contiguous tensors, in their native dtype, in the given order."""
    h = hashlib.sha256()
    for tensor in tensors:
        h.update(tensor.detach().contiguous().to("cpu").view(torch.uint8).numpy().tobytes())
    return h.hexdigest()


@dataclass
class LatentMessage:
    label: dict
    kv_read: KV = field(default_factory=list)
    kv_thoughts: KV = field(default_factory=list)
    states: torch.Tensor | None = None
    text: str | None = None

    @property
    def sender(self) -> str:
        return self.label["sender"]

    @property
    def fingerprint(self) -> str:
        return self.label["fingerprint"]

    @property
    def n_read(self) -> int:
        return self.kv_read[0][0].shape[-2] if self.kv_read else 0

    @property
    def n_thoughts(self) -> int:
        return self.kv_thoughts[0][0].shape[-2] if self.kv_thoughts else 0

    @property
    def length(self) -> int:
        """How many positions it takes in the cache of the whole relay."""
        return self.n_read + self.n_thoughts

    def block_hashes(self) -> dict[str, str]:
        return {
            "read": hash_tensors(t for k, v in self.kv_read for t in (k, v)),
            "thoughts": hash_tensors(t for k, v in self.kv_thoughts for t in (k, v)),
            "states": hash_tensors([] if self.states is None else [self.states]),
            "text": sha256((self.text or "").encode("utf-8")),
        }

    def manifest(self) -> bytes:
        return canonical_json({k: v for k, v in self.label.items() if k not in ("fingerprint", "signature")})

    def close(self) -> LatentMessage:
        """Computes block hashes and fingerprint. Done when the message is born, before the signature."""
        self.label.pop("signature", None)
        self.label["block_hashes"] = self.block_hashes()
        self.label["fingerprint"] = sha256(self.manifest())
        return self

    def copy(self) -> LatentMessage:
        """The receiver works on a copy: generation writes into the cache it receives."""
        return LatentMessage(
            copy.deepcopy(self.label),
            [(k.clone(), v.clone()) for k, v in self.kv_read],
            [(k.clone(), v.clone()) for k, v in self.kv_thoughts],
            None if self.states is None else self.states.clone(),
            self.text,
        )

    def save(self, path: Path, *, full: bool = False) -> None:
        """Safetensors with the label in the header. Always the states, the KV only with `full`."""
        tensors = {} if self.states is None else {"states": self.states.to("cpu").contiguous()}
        if full:
            for name, kv in (("read", self.kv_read), ("thoughts", self.kv_thoughts)):
                for i, (k, v) in enumerate(kv):
                    tensors[f"{name}.{i}.k"] = k.to("cpu").contiguous()
                    tensors[f"{name}.{i}.v"] = v.to("cpu").contiguous()
        metadata = {
            "label": json.dumps(self.label, ensure_ascii=False),
            "text": self.text or "",
            "full": "yes" if full else "no",
        }
        save_file(tensors, str(path), metadata=metadata)

    @classmethod
    def load(cls, path: Path, device: str = "cpu") -> LatentMessage:
        with safe_open(str(path), framework="pt", device="cpu") as f:
            metadata = f.metadata()
            keys = f.keys()  # safe_open does not iterate like a dict
            tensors = {key: f.get_tensor(key).to(device) for key in keys}
        label = json.loads(metadata["label"])

        def kv(name: str) -> KV:
            if f"{name}.0.k" not in tensors:
                return []
            return [(tensors[f"{name}.{i}.k"], tensors[f"{name}.{i}.v"]) for i in range(label["n_layer"])]

        return cls(label, kv("read"), kv("thoughts"), tensors.get("states"), metadata["text"] or None)


def cache_for_writing(config=None) -> DynamicCache:
    """The empty cache an agent writes with. With transformers 5 and the model's config it is born the way the model
    wants it: Gemma 4's sliding layers keep only the last window instead of every position."""
    if config is None or hasattr(DynamicCache, "from_legacy_cache"):
        return DynamicCache()
    return DynamicCache(config=config)


def cache_from_pieces(pieces: list[KV], config=None) -> DynamicCache:
    """The cache made of the pieces in a row. `torch.cat` creates new tensors: the pieces are not touched.

    Without `config` every layer keeps every position: that is what reading and then slicing the messages needs. With
    the config (transformers 5) the cache is the model's own, and the sliding layers keep only the last window: that
    is what writing needs, since the older positions would be thrown away by the mask anyway."""
    pieces = [p for p in pieces if p and p[0][0].shape[-2] > 0]
    if not pieces:
        return cache_for_writing(config)
    layers = tuple(
        (torch.cat([p[i][0] for p in pieces], dim=-2), torch.cat([p[i][1] for p in pieces], dim=-2))
        for i in range(len(pieces[0]))
    )
    if hasattr(DynamicCache, "from_legacy_cache"):
        return DynamicCache.from_legacy_cache(layers)
    if config is None:
        # transformers 5: without a config every layer is full, even Gemma 4's sliding ones; the mask does the window
        return DynamicCache(ddp_cache_data=layers)
    cache = DynamicCache(config=config)
    for i, (keys, values) in enumerate(layers):
        cache.update(keys, values, i)
    return cache


def kv_layers(cache: DynamicCache) -> KV:
    """Keys and values of each layer, with transformers 4 and 5."""
    if hasattr(cache, "to_legacy_cache"):
        return list(cache.to_legacy_cache())
    return [(layer.keys, layer.values) for layer in cache.layers]


def cache_from(messages: list[LatentMessage], config=None) -> DynamicCache:
    """The relay's memory so far: the messages in a row, in the order they were born."""
    return cache_from_pieces([piece for m in messages for piece in (m.kv_read, m.kv_thoughts)], config)


def slice_kv(cache: DynamicCache, start: int, end: int) -> KV:
    """Positions [start, end) of the cache, copied."""
    return [(k[..., start:end, :].clone(), v[..., start:end, :].clone()) for k, v in kv_layers(cache)]
