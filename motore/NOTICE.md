# NOTICE

Il codice di questa cartella è del team, tranne le parti indicate qui.

## LatentMAS

- **Fonte:** https://github.com/Gen-Verse/LatentMAS, commit `9a9e4d3`.
- **Licenza:** Apache License 2.0, https://www.apache.org/licenses/LICENSE-2.0.
- **Cosa deriva da lì:** in `motore/modello.py`, il calcolo della matrice di riallineamento `W_a` con la normalizzazione della norma (`models.py:158-213`) e il ciclo dei passi latenti (`models.py:277-350`).
- **Modifiche:** un agente alla volta (batch 1); gli stati nascosti dei passi latenti vengono restituiti invece che scartati; la cache passa attraverso il modello base (`model.model`) e la decodifica greedy è nostra; con zero passi latenti la cache resta; i prompt e i ruoli sono del motore, non i template di LatentMAS.
- **Citazione:** Jiaru Zou et al., "Latent Collaboration in Multi-Agent Systems", ICML 2026, https://arxiv.org/abs/2511.20639.

## Modello usato nei test

Qwen3-0.6B (https://huggingface.co/Qwen/Qwen3-0.6B, revisione `c1899de289a04d12100db370d81485cdf75e47ca`, licenza Apache 2.0). I test lo scaricano e il repo non lo ridistribuisce.
