# engine — the telepathic engine

The engine is shared with the Silent Council.
The interface is the one decided in "Engine interface", the seal the one decided by the team.
The terms (latent message, relay, seal) are those of `CONTEXT.md`.

Qwen3 agents that pass each other **one latent message per agent** instead of text: the KV of what the agent read, the KV of its latent steps, the hidden states of those steps and a label.
The same relay also runs **in text**, as a comparison.

| File | What it does |
|---|---|
| `engine/model.py` | loads Qwen3, LatentMAS realignment and latent steps, greedy decoding with a JSON constraint |
| `engine/message.py` | the latent message: label, fingerprint, copy, saving to safetensors |
| `engine/engine.py` | the `think`, `write` and `deliver` commands and recomputing the thoughts |
| `engine/relay.py` | the agents in a row, in telepathy or in text |
| `engine/check.py` | the checks inside `deliver`: fingerprint and chain |
| `engine/seal.py` | Ed25519 signature per role and its check |
| `engine/verify.py` | verification of saved messages, even without the engine |
| `tests/` | the tests, with and without the model |

## Usage

```bash
cd engine
uv venv -p 3.12 .venv && uv pip install -p .venv -r requirements.txt
.venv/bin/python -m pytest -q                  # 22 tests, about 30 s on an M4 Mac; downloads Qwen3-0.6B the first time
.venv/bin/python -m pytest -q -m "not model"   # only the fast tests, without the model
.venv/bin/ruff check . && .venv/bin/ruff format --check .
```

```python
from engine import Agent, Engine, Model, Relay

model = Model("Qwen/Qwen3-14B", "<revision>")  # bf16 on GPU (ROCm too), fp32 on Mac and CPU
engine = Engine(model, log_dir=Path("log"))
legal = Agent("legal", "You are the legal expert. ...")
# ... finance, risk, rapporteur
relay = Relay(engine, [legal, finance, risk], rapporteur, mode="telepathy", latent_steps=10)
outcome = relay.run(
    "contract-A",
    {"legal": section_1, "finance": section_2, "risk": section_3, "rapporteur": "Write the verdict."},
    schema=verdict_schema,
)
outcome.final.text, outcome.tokens_generated, outcome.seconds, outcome.stopped
```

- **`think(agent, text, received, ...)`** reads the text on top of the received messages, does the latent steps and returns the latent message. In text mode the agent writes its analysis instead, at most `max_text_tokens` tokens (512 by default).
- **`write(agent, text, received, schema=...)`** writes starting from the received messages, on a copy of the memory. With a JSON schema the decoding is constrained. Every token has its logprob and the 5 most likely alternatives, for the confidence of the verdict.
- **`deliver(message, chain)`** always goes through the checks and gives the recipient a copy, only if they all say "pass". If one stops it, it writes an incident log and saves the whole message as evidence.
- **Per-agent notes**: `write` by the same agent with its own message among the received ones. The note does not enter the chain.
- **Commitment**: `with_commitment(message, commitment)` puts it in the label and closes the message again, so it is sealed.
- **Pre-registered tests:** `latent_steps=0` keeps the KV of what was read; `Relay.run(thoughts_from={...})` replaces an agent's thoughts with those of another message and recomputes their KV in the right position.
- **Demo attacks:** `Relay.run(attacks={"finance": function})` tampers with a message after it is born and before delivery.

### Seal and verification

```python
from engine import SealCheck, create_keys, load_private, load_public

create_keys(Path("~/.engine/private-keys").expanduser(), Path("public-keys"), ["legal", "finance", "risk"])
engine = Engine(model, signing_keys=load_private(...), checks=[SealCheck(load_public(Path("public-keys")))])
```

```bash
.venv/bin/python -m engine.verify <folder of saved messages> --public public-keys
```

The command checks fingerprint, signature and chain of every saved message, including files without KV.
Private keys live outside the repo, with mode 600; only the public ones go in the repo.

## Rules

- **Lossless.** In the normal handoff the KV travels as it was born, with no recomputation or dtype conversion. Block hashes and fingerprint are computed when the message is born and checked again at delivery.
- **The receiver works on a copy.**
- **A piece does not move position.** The chain check verifies that every message starts where the previous one ends, that the sequence number adds up and that the hash of the previous one is right.
- **Roles:** the names `planner`, `critic`, `refiner` and `judger` are forbidden.
- **Prompts.** Every agent is a Qwen3 chat turn with its instructions as system. In telepathy the prompt ends as in LatentMAS (`assistant\n`) and the latent steps follow. To write, the model answers without a `<think>` block.
- **Realignment** `W_a` from LatentMAS is on by default (`Model(..., realign=False)` to turn it off). The norm normalisation always stays.

## On the MI300X (G1)

- Torch from the ROCm build. The pre-registered eval runs with `transformers` 4.57.6; with 5 the engine also handles Gemma 4 (after a spike), and the service uses 5. The model and the cache are born in bf16 and stay that way.
- For the first-day trial: compare against an fp32 reference and forbid the fallback to the SDPA math backend with `sdpa_kernel`.
- To measure: the hashing time on messages of a few GB and whether recomputing the thoughts stays identical in bf16. On the Mac in fp32 the difference is 0.

## What is missing

- **Coherence** is a check to add to the `Engine(checks=...)` list, without changing the rest.
- The **translator** reads `message.states`: the states h_0..h_m of the latent steps.
