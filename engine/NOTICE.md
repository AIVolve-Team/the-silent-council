# NOTICE

The code in this folder belongs to the team, except for the parts listed here.

## LatentMAS

- **Source:** https://github.com/Gen-Verse/LatentMAS, commit `9a9e4d3`.
- **License:** Apache License 2.0, https://www.apache.org/licenses/LICENSE-2.0.
- **What derives from it:** in `engine/model.py`, the computation of the realignment matrix `W_a` with norm normalisation (`models.py:158-213`) and the latent-step loop (`models.py:277-350`).
- **Changes:** one agent at a time (batch 1); the hidden states of the latent steps are returned instead of discarded; the cache goes through the base model (`model.model`) and the greedy decoding is ours; with zero latent steps the cache stays; prompts and roles are the engine's, not LatentMAS's templates.
- **Citation:** Jiaru Zou et al., "Latent Collaboration in Multi-Agent Systems", ICML 2026, https://arxiv.org/abs/2511.20639.

## Model used in the tests

Qwen3-0.6B (https://huggingface.co/Qwen/Qwen3-0.6B, revision `c1899de289a04d12100db370d81485cdf75e47ca`, Apache 2.0 license). The tests download it and the repo does not redistribute it.
