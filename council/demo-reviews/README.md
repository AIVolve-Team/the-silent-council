# Council reviews for the demo, one pair per model of the router

Real reviews from the MI300X, copied byte for byte from earlier runs. They are the demo's replays: three short contracts that the router sends to Qwen3-14B, two long ones that it sends to Gemma 4 31B.
Every contract comes reviewed both in telepathy and in text mode, so the demo can race the two on the same contract.

| File | CUAD contract | Tokens | Model | Mode | Seconds | Recommendation |
|---|---|---|---|---|---|---|
| `short-westerncopper-telepathy.json` | Western Copper, Non-Competition Agreement | 3,577 | Qwen3-14B | telepathy | 56 | negoziare |
| `short-westerncopper-text.json` | the same | 3,577 | Qwen3-14B | text | 144 | negoziare |
| `short-tuniu-telepathy.json` | Tuniu, Cooperation Agreement | 3,605 | Qwen3-14B | telepathy | 55 | negoziare |
| `short-tuniu-text.json` | the same | 3,605 | Qwen3-14B | text | 160 | negoziare |
| `short-mfafinancial-telepathy.json` | MFA Financial, Joint Filing Agreement | 947 | Qwen3-14B | telepathy | 23 | firmare |
| `short-mfafinancial-text.json` | the same | 947 | Qwen3-14B | text | 82 | firmare |
| `long-fusion-supply-telepathy.json` | Fusion Pharmaceuticals, Supply Agreement | 8,674 | Gemma 4 31B | telepathy | 150 | negoziare |
| `long-fusion-supply-text.json` | the same | 8,674 | Gemma 4 31B | text | 214 | negoziare |
| `long-elfbeauty-cooperation-telepathy.json` | e.l.f. Beauty, Cooperation Agreement | 9,269 | Gemma 4 31B | telepathy | 128 | negoziare |
| `long-elfbeauty-cooperation-text.json` | the same | 9,269 | Gemma 4 31B | text | 220 | negoziare |

- **Where they come from:**
  - the short ones: one line each of `replica/cuad-replica-telepatia.jsonl` (sha256 `7f834ed5…`) and `replica/cuad-replica-testo.jsonl` (sha256 `fc17d916…`), the CUAD replication on 72 contracts, Qwen3-14B only;
  - the long ones: one line each of `gara-finestra/cuad-train-telepatia.jsonl` (sha256 `72ff49ac…`) and `gara-finestra/cuad-train-testo.jsonl` (sha256 `965d35cf…`), run on 17/10/2026 on the MI300X with the engine fix for Gemma 4's sliding layers (write-up), on the `spike/gemma4-text` branch, with a short contract first to warm up the GPU;
  - neither results folder is in the repo.
- **Why the long ones were run again:** the Gemma 4 trial of 15/10 had them in telepathy only, with the engine treating Gemma's sliding layers as full ones. With the fix, telepathy goes from 194 to 150 s on Fusion and from 172 to 128 s on e.l.f. Beauty on a different machine, and from 299 to 150 s and 248 to 128 s on the same one. The answers on the 19 categories are the same as on 15/10; a few words change in the verdict's rationales.
- **Which model:** the router's rule (`council/service/reviewer/routing.py`): up to 6,000 tokens with the Qwen3-14B tokenizer goes to Qwen3-14B, beyond to Gemma 4 31B. Tokens from `tokens-per-contract.csv` and the Gemma trial's `lunghezze.json`.
- **Configuration of the runs, not of the service:** 0 latent steps, no realignment, bf16. The contract is split by its headings (`"taglio": "titoli"`), except Fusion and MFA Financial, split in contiguous parts (`"contiguo"`). The service starts with 10 latent steps.
- **MFA Financial** is there to show a contract that comes out "sign": a two-page SEC joint filing agreement with none of the 19 categories, where the council agrees with the CUAD lawyers on all 19. It is a trivial contract, not a complex one that happens to be safe.
- **Hand-picked** as good cases to show: a recommendation with flagged clauses and dissents for the person to choose on. The short ones also near the replication's median speed ratio between text and telepathy (2.7×); the two long ones among the faster Gemma reviews of the 15/10 trial. They are not a random sample, and they say nothing about accuracy or speed on their own.
- **Field names are in Italian** (`contratto`, `note`, `verdetto`, `dissensi`, …): all these runs used the pre-refactor code.
