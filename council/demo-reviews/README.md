# Council reviews for the demo, one pair per model of the router

Real reviews from the MI300X, copied byte for byte from two earlier runs. They are the demo's replays: two short contracts that the router sends to Qwen3-14B, two long ones that it sends to Gemma 4 31B.
The short ones come with the same contract reviewed in text mode too, so the demo can race telepathy against text on the same contract.

| File | CUAD contract | Tokens | Model | Mode | Seconds | Recommendation |
|---|---|---|---|---|---|---|
| `short-westerncopper-telepathy.json` | Western Copper, Non-Competition Agreement | 3,577 | Qwen3-14B | telepathy | 56 | negoziare |
| `short-westerncopper-text.json` | the same | 3,577 | Qwen3-14B | text | 144 | negoziare |
| `short-tuniu-telepathy.json` | Tuniu, Cooperation Agreement | 3,605 | Qwen3-14B | telepathy | 55 | negoziare |
| `short-tuniu-text.json` | the same | 3,605 | Qwen3-14B | text | 160 | negoziare |
| `long-fusion-supply.json` | Fusion Pharmaceuticals, Supply Agreement | 8,674 | Gemma 4 31B | telepathy | 194 | negoziare |
| `long-elfbeauty-cooperation.json` | e.l.f. Beauty, Cooperation Agreement | 9,269 | Gemma 4 31B | telepathy | 172 | negoziare |

- **Where they come from:**
  - the short ones: one line each of `replica/cuad-replica-telepatia.jsonl` (sha256 `7f834ed5…`) and `replica/cuad-replica-testo.jsonl` (sha256 `fc17d916…`), the CUAD replication on 72 contracts, Qwen3-14B only;
  - the long ones: one line each of `gemma31b/cuad-train-telepatia.jsonl` (sha256 `6c32361a…`), the Gemma 4 trial of 15/10/2026 on CUAD train, the reviews behind the router's 77.4 F1;
  - neither results folder is in the repo.
- **Which model:** the router's rule (`council/service/reviewer/routing.py`): up to 6,000 tokens with the Qwen3-14B tokenizer goes to Qwen3-14B, beyond to Gemma 4 31B. Tokens from `tokens-per-contract.csv` and the Gemma trial's `lunghezze.json`.
- **Configuration of the runs, not of the service:** 0 latent steps, no realignment, bf16. The contract is split by its headings (`"taglio": "titoli"`), except Fusion, split in contiguous parts (`"contiguo"`). The service starts with 10 latent steps. Text mode exists only for Qwen3-14B: Gemma was never run in text mode.
- **Hand-picked** as good cases to show: a recommendation with flagged clauses and dissents for the person to choose on. The short ones also near the replication's median speed ratio between text and telepathy (2.7×); the two long ones among the faster Gemma reviews (the trial's mean on long contracts is 258 s). They are not a random sample, and they say nothing about accuracy or speed on their own.
- **Field names are in Italian** (`contratto`, `note`, `verdetto`, `dissensi`, …): both runs came before the English refactor.
