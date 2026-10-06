"""Il messaggio latente: il pezzo di cache di un agente, i suoi stati nascosti e un'etichetta.

L'impronta copre tutto: gli hash dei byte dei blocchi stanno nell'etichetta, e l'impronta è lo SHA-256 del
manifesto, cioè dell'etichetta in JSON canonico senza impronta e firma. La firma, se c'è, è sullo stesso manifesto.
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

VERSIONE = "0.1.0"
TELEPATIA = "telepatia"
TESTO = "testo"

# Per ogni layer, K e V di forma [1, teste_kv, posizioni, dim_testa].
KV = list[tuple[torch.Tensor, torch.Tensor]]


def json_canonico(dati: object) -> bytes:
    return json.dumps(dati, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def sha256(dati: bytes) -> str:
    return hashlib.sha256(dati).hexdigest()


def hash_inizio(sessione: str) -> str:
    """Il "messaggio precedente" del primo messaggio di una sessione."""
    return sha256(json_canonico({"inizio_sessione": sessione}))


def hash_tensori(tensori: Iterable[torch.Tensor]) -> str:
    """SHA-256 dei byte canonici: tensori contigui, nel dtype nativo, nell'ordine dato."""
    h = hashlib.sha256()
    for tensore in tensori:
        h.update(tensore.detach().contiguous().to("cpu").view(torch.uint8).numpy().tobytes())
    return h.hexdigest()


@dataclass
class MessaggioLatente:
    etichetta: dict
    kv_lettura: KV = field(default_factory=list)
    kv_pensieri: KV = field(default_factory=list)
    stati: torch.Tensor | None = None
    testo: str | None = None

    @property
    def mittente(self) -> str:
        return self.etichetta["mittente"]

    @property
    def impronta(self) -> str:
        return self.etichetta["impronta"]

    @property
    def n_lettura(self) -> int:
        return self.kv_lettura[0][0].shape[-2] if self.kv_lettura else 0

    @property
    def n_pensieri(self) -> int:
        return self.kv_pensieri[0][0].shape[-2] if self.kv_pensieri else 0

    @property
    def lunghezza(self) -> int:
        """Quante posizioni occupa nella cache dell'intera staffetta."""
        return self.n_lettura + self.n_pensieri

    def hash_blocchi(self) -> dict[str, str]:
        return {
            "lettura": hash_tensori(t for k, v in self.kv_lettura for t in (k, v)),
            "pensieri": hash_tensori(t for k, v in self.kv_pensieri for t in (k, v)),
            "stati": hash_tensori([] if self.stati is None else [self.stati]),
            "testo": sha256((self.testo or "").encode("utf-8")),
        }

    def manifesto(self) -> bytes:
        return json_canonico({k: v for k, v in self.etichetta.items() if k not in ("impronta", "firma")})

    def chiudi(self) -> MessaggioLatente:
        """Calcola hash dei blocchi e impronta. Si fa quando il messaggio nasce, prima della firma."""
        self.etichetta.pop("firma", None)
        self.etichetta["hash_blocchi"] = self.hash_blocchi()
        self.etichetta["impronta"] = sha256(self.manifesto())
        return self

    def copia(self) -> MessaggioLatente:
        """Chi riceve lavora su una copia: la generazione scrive nella cache che riceve."""
        return MessaggioLatente(
            copy.deepcopy(self.etichetta),
            [(k.clone(), v.clone()) for k, v in self.kv_lettura],
            [(k.clone(), v.clone()) for k, v in self.kv_pensieri],
            None if self.stati is None else self.stati.clone(),
            self.testo,
        )

    def salva(self, percorso: Path, *, completo: bool = False) -> None:
        """Safetensors con l'etichetta nell'header. Sempre gli stati, la KV solo con `completo`."""
        tensori = {} if self.stati is None else {"stati": self.stati.to("cpu").contiguous()}
        if completo:
            for nome, kv in (("lettura", self.kv_lettura), ("pensieri", self.kv_pensieri)):
                for i, (k, v) in enumerate(kv):
                    tensori[f"{nome}.{i}.k"] = k.to("cpu").contiguous()
                    tensori[f"{nome}.{i}.v"] = v.to("cpu").contiguous()
        metadati = {
            "etichetta": json.dumps(self.etichetta, ensure_ascii=False),
            "testo": self.testo or "",
            "completo": "sì" if completo else "no",
        }
        save_file(tensori, str(percorso), metadata=metadati)

    @classmethod
    def carica(cls, percorso: Path, dispositivo: str = "cpu") -> MessaggioLatente:
        with safe_open(str(percorso), framework="pt", device="cpu") as f:
            metadati = f.metadata()
            chiavi = f.keys()  # safe_open non si itera come un dizionario
            tensori = {chiave: f.get_tensor(chiave).to(dispositivo) for chiave in chiavi}
        etichetta = json.loads(metadati["etichetta"])

        def kv(nome: str) -> KV:
            if f"{nome}.0.k" not in tensori:
                return []
            return [(tensori[f"{nome}.{i}.k"], tensori[f"{nome}.{i}.v"]) for i in range(etichetta["n_layer"])]

        return cls(etichetta, kv("lettura"), kv("pensieri"), tensori.get("stati"), metadati["testo"] or None)


def cache_da_pezzi(pezzi: list[KV]) -> DynamicCache:
    """La cache fatta dai pezzi in fila. `torch.cat` crea tensori nuovi: i pezzi non vengono toccati."""
    pezzi = [p for p in pezzi if p and p[0][0].shape[-2] > 0]
    if not pezzi:
        return DynamicCache()
    strati = tuple(
        (torch.cat([p[i][0] for p in pezzi], dim=-2), torch.cat([p[i][1] for p in pezzi], dim=-2))
        for i in range(len(pezzi[0]))
    )
    return DynamicCache.from_legacy_cache(strati)


def cache_da(messaggi: list[MessaggioLatente]) -> DynamicCache:
    """La memoria della staffetta fino a qui: i messaggi in fila, nell'ordine in cui sono nati."""
    return cache_da_pezzi([pezzo for m in messaggi for pezzo in (m.kv_lettura, m.kv_pensieri)])


def taglia(cache: DynamicCache, da: int, a: int) -> KV:
    """Le posizioni [da, a) della cache, copiate."""
    return [(k[..., da:a, :].clone(), v[..., da:a, :].clone()) for k, v in cache.to_legacy_cache()]
