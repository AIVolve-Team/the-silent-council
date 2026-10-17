"""The shared model: Qwen3 on Transformers, with LatentMAS realignment and latent steps.

Realignment and latent steps follow LatentMAS's `ModelWrapper` at commit 9a9e4d3 (`models.py:158-213` and
`models.py:277-350`, Apache-2.0, see NOTICE.md). Here they run one agent at a time (batch 1) and also return
the hidden states of the latent steps, which LatentMAS discards.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

import torch
from transformers import AutoModelForCausalLM, AutoTokenizer, DynamicCache


def default_device() -> str:
    """`cuda` also covers ROCm, hence the MI300X."""
    if torch.cuda.is_available():
        return "cuda"
    if torch.backends.mps.is_available():
        return "mps"
    return "cpu"


@dataclass
class Step:
    """A generated token, with its logprob and the most likely alternatives (before the schema constraint)."""

    token: int
    text: str
    logprob: float
    alternatives: list[tuple[str, float]]
    # logprob of the tokens asked for with `observe`, at every step: e.g. true and false, for confidence.
    observed: dict[int, float] = field(default_factory=dict)


@dataclass
class Generation:
    text: str
    steps: list[Step]
    tokens_read: int

    @property
    def tokens_generated(self) -> int:
        return len(self.steps)


class Model:
    def __init__(
        self,
        name: str,
        revision: str,
        *,
        device: str | None = None,
        dtype: torch.dtype | None = None,
        realign: bool = True,
        soft_tokens_per_page: int = 1120,
    ) -> None:
        self.name = name
        self.revision = revision
        self.device = device or default_device()
        # On GPU the model is born in bf16 and the cache stays that way: no conversion in transit.
        self.dtype = dtype or (torch.bfloat16 if self.device == "cuda" else torch.float32)
        self.tokenizer = AutoTokenizer.from_pretrained(name, revision=revision)
        self.net = AutoModelForCausalLM.from_pretrained(name, revision=revision, dtype=self.dtype)
        self.net.to(self.device).eval()
        self.realign = realign
        self.matrix, self.norm = self._realignment()
        self.end_tokens = self._find_end_tokens()
        # Gemma 4 takes 70 to 1120 soft tokens per image: a contract page in small print needs the most.
        self.soft_tokens_per_page = soft_tokens_per_page
        self.processor = None

    @property
    def n_layer(self) -> int:
        return self.net.config.get_text_config().num_hidden_layers

    def logit(self, state: torch.Tensor) -> torch.Tensor:
        """The next-token logits, with the final softcap if the model has one (Gemma 4: 30)."""
        logit = self.net.lm_head(state).float()
        softcap = getattr(self.net.config.get_text_config(), "final_logit_softcapping", None)
        return torch.tanh(logit / softcap) * softcap if softcap else logit

    @torch.no_grad()
    def _realignment(self, rows_per_block: int = 8192) -> tuple[torch.Tensor, torch.Tensor]:
        """W_a = (W_outᵀ W_out + 1e-5·I)⁻¹ W_outᵀ W_in in fp32, and the mean norm of the input embeddings.

        Without realignment the matrix is the identity, but the norm normalisation stays, as in LatentMAS.
        The products are accumulated in blocks of rows on the model's device: so no fp32 copy of the two
        embedding matrices is needed (3 GB for Qwen3-4B), which on a 16 GB Mac sends the system into swap.
        """
        w_in = self.net.get_input_embeddings().weight
        w_out = self.net.get_output_embeddings().weight
        size = w_in.shape[1]
        gram = torch.zeros(size, size, dtype=torch.float32, device=w_in.device)
        right = torch.zeros_like(gram)
        norm_sum = torch.zeros((), dtype=torch.float32, device=w_in.device)
        for start in range(0, w_in.shape[0], rows_per_block):
            inp = w_in[start : start + rows_per_block].to(torch.float32)
            out = w_out[start : start + rows_per_block].to(torch.float32)
            norm_sum += inp.norm(dim=1).sum()
            if self.realign:
                gram += out.T @ out
                right += out.T @ inp
        norm = norm_sum / w_in.shape[0]
        if not self.realign:
            return torch.eye(size, device=self.device), norm.to(self.device)
        # torch.linalg.solve is not guaranteed on MPS: the D×D solve runs on the CPU, where it is small.
        where = self.device if self.device == "cuda" else "cpu"
        gram = gram.to(where) + 1e-5 * torch.eye(size, device=where)
        matrix = torch.linalg.solve(gram, right.to(where))
        return matrix.to(self.device), norm.to(self.device)

    def _find_end_tokens(self) -> set[int]:
        end = {self.tokenizer.eos_token_id}
        if "<|im_end|>" in self.tokenizer.get_vocab():  # Qwen3's end of turn; Gemma 4 gives it in generation_config
            end.add(self.tokenizer.convert_tokens_to_ids("<|im_end|>"))
        eos = self.net.generation_config.eos_token_id
        end.update(eos if isinstance(eos, list) else [eos])
        return {t for t in end if t is not None}

    def prompt(self, instructions: str, text: str, *, thinking: bool) -> str:
        """An agent's turn in Qwen3's chat format.

        With `thinking` the prompt ends as in LatentMAS (`<|im_start|>assistant\\n`) and the latent steps follow.
        Without it, the model answers right away, without a `<think>` block.
        """
        messages = [{"role": "system", "content": instructions}, {"role": "user", "content": text}]
        options = {} if thinking else {"enable_thinking": False}
        return self.tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=True, **options)

    def encode(self, text: str) -> torch.Tensor:
        return self.tokenizer(text, return_tensors="pt", add_special_tokens=False).input_ids.to(self.device)

    def encode_with_pages(self, text: str, pages: list) -> tuple[torch.Tensor, dict]:
        """A prompt with page images: each image placeholder in `text` becomes the page's soft tokens.

        Only for models that read images (Gemma 4). Returns the ids and what the model needs besides them.
        """
        inputs = self._processor()(
            text=[text],
            images=[pages],
            return_tensors="pt",
            add_special_tokens=False,
            max_soft_tokens=self.soft_tokens_per_page,
        )
        extra = {
            "pixel_values": inputs["pixel_values"].to(self.device),
            "image_position_ids": inputs["image_position_ids"].to(self.device),
            "mm_token_type_ids": inputs["mm_token_type_ids"].to(self.device),
        }
        return inputs["input_ids"].to(self.device), extra

    @property
    def image_token(self) -> str:
        """The placeholder of one page in a prompt."""
        return self._processor().image_token

    def _processor(self):
        if self.processor is None:
            from transformers import AutoProcessor

            self.processor = AutoProcessor.from_pretrained(self.name, revision=self.revision)
        return self.processor

    @torch.no_grad()
    def read(self, ids: torch.Tensor, cache: DynamicCache, extra: dict | None = None) -> torch.Tensor:
        """Reads `ids` on top of the cache, which grows, and returns the last hidden state, [1, D].

        It is the state after the final normalisation, i.e. LatentMAS's `hidden_states[-1]`. `extra` carries the
        page images of `encode_with_pages`.
        """
        output = self.net.model(input_ids=ids, past_key_values=cache, use_cache=True, **(extra or {}))
        return output.last_hidden_state[:, -1, :]

    def realign_vector(self, state: torch.Tensor) -> torch.Tensor:
        """From final hidden state to input embedding of the next latent step (eq. 3 of the paper)."""
        aligned = state.to(torch.float32) @ self.matrix
        aligned = aligned * (self.norm / aligned.norm(dim=-1, keepdim=True).clamp_min(1e-6))
        return aligned.to(self.dtype)

    @torch.no_grad()
    def latent_step(self, state: torch.Tensor, cache: DynamicCache) -> torch.Tensor:
        """One latent position: receives realign(state), grows the cache by 1 and gives the new state."""
        inp = self.realign_vector(state).unsqueeze(1)
        output = self.net.model(inputs_embeds=inp, past_key_values=cache, use_cache=True)
        return output.last_hidden_state[:, -1, :]

    @torch.no_grad()
    def latent_steps(self, cache: DynamicCache, initial_state: torch.Tensor, steps: int) -> torch.Tensor:
        """`steps` latent positions on top of the cache. Returns the states h_0..h_m, [m+1, D]: step t receives
        realign(h_{t-1}), so h_0..h_{m-1} are enough to recompute the KV of the latent steps."""
        states = [initial_state]
        for _ in range(steps):
            states.append(self.latent_step(states[-1], cache))
        return torch.cat(states, dim=0)

    @torch.no_grad()
    def generate(
        self,
        cache: DynamicCache,
        ids: torch.Tensor,
        max_new: int,
        *,
        allowed: Callable[[list[int]], list[int] | torch.Tensor] | None = None,
        alternatives: int = 5,
        observe: list[int] | None = None,
        extra: dict | None = None,
    ) -> Generation:
        """Greedy decoding on top of the cache. With `allowed` it picks only among the allowed tokens (JSON schema).

        Logprobs, alternatives and `observed` come from the model's distribution before the constraint.
        """
        state = self.read(ids, cache, extra)
        prompt = ids[0].tolist()
        generated: list[int] = []
        steps: list[Step] = []
        for _ in range(max_new):
            logprob = torch.log_softmax(self.logit(state), dim=-1)[0]
            if allowed is None:
                choice = int(torch.argmax(logprob))
            else:
                permitted = allowed(prompt + generated)
                if isinstance(permitted, torch.Tensor):
                    mask = torch.zeros_like(logprob, dtype=torch.bool)
                    n = min(len(permitted), len(mask))
                    mask[:n] = permitted[:n].to(logprob.device)
                else:
                    mask = torch.zeros_like(logprob, dtype=torch.bool)
                    mask[list(permitted)] = True
                choice = int(torch.argmax(logprob.masked_fill(~mask, float("-inf"))))
            if choice in self.end_tokens:
                break
            best = torch.topk(logprob, alternatives)
            steps.append(
                Step(
                    choice,
                    self.tokenizer.decode([choice]),
                    float(logprob[choice]),
                    [(self.tokenizer.decode([i]), float(v)) for v, i in zip(best.values, best.indices.tolist())],
                    {t: float(logprob[t]) for t in observe or []},
                )
            )
            generated.append(choice)
            state = self.read(torch.tensor([[choice]], device=self.device), cache)
        text = self.tokenizer.decode(generated, skip_special_tokens=True).strip()
        return Generation(text, steps, tokens_read=ids.shape[1])
