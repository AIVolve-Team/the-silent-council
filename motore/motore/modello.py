"""Il modello condiviso: Qwen3 su Transformers, con il riallineamento e i passi latenti di LatentMAS.

Riallineamento e passi latenti riprendono `ModelWrapper` di LatentMAS al commit 9a9e4d3 (`models.py:158-213` e
`models.py:277-350`, Apache-2.0, vedi NOTICE.md). Qui girano un agente alla volta (batch 1) e restituiscono anche
gli stati nascosti dei passi latenti, che LatentMAS scarta.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

import torch
from transformers import AutoModelForCausalLM, AutoTokenizer, DynamicCache


def dispositivo_predefinito() -> str:
    """`cuda` copre anche ROCm, quindi la MI300X."""
    if torch.cuda.is_available():
        return "cuda"
    if torch.backends.mps.is_available():
        return "mps"
    return "cpu"


@dataclass
class Passo:
    """Un token generato, con il suo logprob e le alternative più probabili (prima del vincolo dello schema)."""

    token: int
    testo: str
    logprob: float
    alternative: list[tuple[str, float]]
    # logprob dei token chiesti con `osserva`, a ogni passo: per esempio true e false, per la confidenza.
    osservati: dict[int, float] = field(default_factory=dict)


@dataclass
class Generazione:
    testo: str
    passi: list[Passo]
    token_letti: int

    @property
    def token_generati(self) -> int:
        return len(self.passi)


class Modello:
    def __init__(
        self,
        nome: str,
        revisione: str,
        *,
        dispositivo: str | None = None,
        dtype: torch.dtype | None = None,
        riallinea: bool = True,
    ) -> None:
        self.nome = nome
        self.revisione = revisione
        self.dispositivo = dispositivo or dispositivo_predefinito()
        # Su GPU il modello nasce in bf16 e la cache resta così: nessuna conversione in transito.
        self.dtype = dtype or (torch.bfloat16 if self.dispositivo == "cuda" else torch.float32)
        self.tokenizer = AutoTokenizer.from_pretrained(nome, revision=revisione)
        self.rete = AutoModelForCausalLM.from_pretrained(nome, revision=revisione, dtype=self.dtype)
        self.rete.to(self.dispositivo).eval()
        self.riallinea = riallinea
        self.matrice, self.norma = self._riallineamento()
        self.fine = self._token_di_fine()

    @property
    def n_layer(self) -> int:
        return self.rete.config.num_hidden_layers

    def _riallineamento(self) -> tuple[torch.Tensor, torch.Tensor]:
        """W_a = (W_outᵀ W_out + 1e-5·I)⁻¹ W_outᵀ W_in in fp32, e la norma media degli embedding d'ingresso.

        Senza riallineamento la matrice è l'identità, ma la normalizzazione della norma resta, come in LatentMAS.
        """
        # torch.linalg.solve non è garantito su MPS: fuori dalla GPU si calcola sulla CPU, una volta sola.
        dove = self.dispositivo if self.dispositivo == "cuda" else "cpu"
        w_in = self.rete.get_input_embeddings().weight.detach().to(dove, torch.float32)
        w_out = self.rete.get_output_embeddings().weight.detach().to(dove, torch.float32)
        norma = w_in.norm(dim=1).mean()
        if self.riallinea:
            gram = w_out.T @ w_out + 1e-5 * torch.eye(w_out.shape[1], device=dove)
            matrice = torch.linalg.solve(gram, w_out.T @ w_in)
        else:
            matrice = torch.eye(w_in.shape[1], device=dove)
        return matrice.to(self.dispositivo), norma.to(self.dispositivo)

    def _token_di_fine(self) -> set[int]:
        fine = {self.tokenizer.eos_token_id, self.tokenizer.convert_tokens_to_ids("<|im_end|>")}
        eos = self.rete.generation_config.eos_token_id
        fine.update(eos if isinstance(eos, list) else [eos])
        return {t for t in fine if t is not None}

    def prompt(self, istruzioni: str, testo: str, *, pensiero: bool) -> str:
        """Il turno di un agente nel formato chat di Qwen3.

        Con `pensiero` il prompt finisce come in LatentMAS (`<|im_start|>assistant\\n`) e seguono i passi latenti.
        Senza, il modello risponde subito, senza blocco `<think>`.
        """
        messaggi = [{"role": "system", "content": istruzioni}, {"role": "user", "content": testo}]
        opzioni = {} if pensiero else {"enable_thinking": False}
        return self.tokenizer.apply_chat_template(messaggi, tokenize=False, add_generation_prompt=True, **opzioni)

    def codifica(self, testo: str) -> torch.Tensor:
        return self.tokenizer(testo, return_tensors="pt", add_special_tokens=False).input_ids.to(self.dispositivo)

    @torch.no_grad()
    def leggi(self, ids: torch.Tensor, cache: DynamicCache) -> torch.Tensor:
        """Legge `ids` sopra la cache, che si allunga, e restituisce l'ultimo stato nascosto, [1, D].

        È lo stato dopo la normalizzazione finale, cioè `hidden_states[-1]` di LatentMAS.
        """
        uscita = self.rete.model(input_ids=ids, past_key_values=cache, use_cache=True)
        return uscita.last_hidden_state[:, -1, :]

    def riallinea_vettore(self, stato: torch.Tensor) -> torch.Tensor:
        """Da stato nascosto finale a embedding d'ingresso del passo latente successivo (eq. 3 del paper)."""
        allineato = stato.to(torch.float32) @ self.matrice
        allineato = allineato * (self.norma / allineato.norm(dim=-1, keepdim=True).clamp_min(1e-6))
        return allineato.to(self.dtype)

    @torch.no_grad()
    def passo_latente(self, stato: torch.Tensor, cache: DynamicCache) -> torch.Tensor:
        """Una posizione latente: riceve riallinea(stato), allunga la cache di 1 e dà lo stato nuovo."""
        ingresso = self.riallinea_vettore(stato).unsqueeze(1)
        uscita = self.rete.model(inputs_embeds=ingresso, past_key_values=cache, use_cache=True)
        return uscita.last_hidden_state[:, -1, :]

    @torch.no_grad()
    def passi_latenti(self, cache: DynamicCache, stato_iniziale: torch.Tensor, passi: int) -> torch.Tensor:
        """`passi` posizioni latenti sopra la cache. Restituisce gli stati h_0..h_m, [m+1, D]: il passo t riceve
        riallinea(h_{t-1}), quindi h_0..h_{m-1} bastano a ricalcolare la KV dei passi latenti."""
        stati = [stato_iniziale]
        for _ in range(passi):
            stati.append(self.passo_latente(stati[-1], cache))
        return torch.cat(stati, dim=0)

    @torch.no_grad()
    def genera(
        self,
        cache: DynamicCache,
        ids: torch.Tensor,
        max_nuovi: int,
        *,
        consentiti: Callable[[list[int]], list[int] | torch.Tensor] | None = None,
        alternative: int = 5,
        osserva: list[int] | None = None,
    ) -> Generazione:
        """Decodifica greedy sopra la cache. Con `consentiti` sceglie solo fra i token ammessi (schema JSON).

        Logprob, alternative e `osservati` vengono dalla distribuzione del modello prima del vincolo.
        """
        stato = self.leggi(ids, cache)
        prompt = ids[0].tolist()
        generati: list[int] = []
        passi: list[Passo] = []
        for _ in range(max_nuovi):
            logprob = torch.log_softmax(self.rete.lm_head(stato).float(), dim=-1)[0]
            if consentiti is None:
                scelta = int(torch.argmax(logprob))
            else:
                ammessi = consentiti(prompt + generati)
                if isinstance(ammessi, torch.Tensor):
                    maschera = torch.zeros_like(logprob, dtype=torch.bool)
                    n = min(len(ammessi), len(maschera))
                    maschera[:n] = ammessi[:n].to(logprob.device)
                else:
                    maschera = torch.zeros_like(logprob, dtype=torch.bool)
                    maschera[list(ammessi)] = True
                scelta = int(torch.argmax(logprob.masked_fill(~maschera, float("-inf"))))
            if scelta in self.fine:
                break
            migliori = torch.topk(logprob, alternative)
            passi.append(
                Passo(
                    scelta,
                    self.tokenizer.decode([scelta]),
                    float(logprob[scelta]),
                    [
                        (self.tokenizer.decode([i]), float(v))
                        for v, i in zip(migliori.values, migliori.indices.tolist())
                    ],
                    {t: float(logprob[t]) for t in osserva or []},
                )
            )
            generati.append(scelta)
            stato = self.leggi(torch.tensor([[scelta]], device=self.dispositivo), cache)
        testo = self.tokenizer.decode(generati, skip_special_tokens=True).strip()
        return Generazione(testo, passi, token_letti=ids.shape[1])
