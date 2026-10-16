# Four council reviews for the demo, one per model of the router

Four real reviews from the MI300X, copied byte for byte from the Gemma 4 trial of 15/10/2026.
They are the demo's replays: two short contracts that the router sends to Qwen3-14B, two long ones that it sends to Gemma 4 31B.

| File | CUAD contract (train) | Tokens | Model | Seconds | Recommendation |
|---|---|---|---|---|---|
| `short-innerscope-distributor.json` | Innerscope Hearing Technologies, Distributor Agreement | 4,536 | Qwen3-14B | 62 | negoziare |
| `short-ashworth-promotion.json` | Ashworth, Promotion Agreement | 5,089 | Qwen3-14B | 78 | negoziare |
| `long-fusion-supply.json` | Fusion Pharmaceuticals, Supply Agreement | 8,674 | Gemma 4 31B | 194 | negoziare |
| `long-elfbeauty-cooperation.json` | e.l.f. Beauty, Cooperation Agreement | 9,269 | Gemma 4 31B | 172 | negoziare |

- **Where they come from:** one line each of `qwen14b-80/cuad-train-telepatia.jsonl` (sha256 `3833bffb…`) and `gemma31b/cuad-train-telepatia.jsonl` (sha256 `6c32361a…`) of the trial's results, not in the repo. They are the reviews behind the router's 77.4 F1.
- **Which model:** the router's rule (`council/service/reviewer/routing.py`): up to 6,000 tokens with the Qwen3-14B tokenizer goes to Qwen3-14B, beyond to Gemma 4 31B. The tokens are the trial's own count (`lunghezze.json`).
- **Configuration of the trial, not of the service:** telepathy, 0 latent steps, no realignment, bf16. The contract is split by its headings (`"taglio": "titoli"`), except Fusion, split in contiguous parts (`"contiguo"`). The service starts with 10 latent steps.
- **Hand-picked** among the 80 contracts as good cases to show: a recommendation with flagged clauses and dissents for the person to choose on. The two long ones were also picked among the faster Gemma reviews (the trial's mean on long contracts is 258 s). They are not a random sample, and they say nothing about accuracy or speed on their own.
- **Field names are in Italian** (`contratto`, `note`, `verdetto`, `dissensi`, …): the trial ran before the English refactor.
