# council/review — the Silent Council

The council runs on the telepathic engine in `engine/` and uses the data in `council/data/`.
The rules come from the team's decisions "Council setup", "Verdict and dissent" and "Engine interface".

For a contract:

1. **split**: one section per expert, with a rule on the clause headings; without headings, contiguous parts;
2. **relay** on the engine: legal → finance → risk think in order, the rapporteur receives everyone's memory and writes the verdict. On ContractNLI and CLAUDETTE finance is not convened;
3. **notes**: each expert writes its own from a copy of its memory, and the note does not enter the chain;
4. **verdict**: the rows of all the categories, the details with quote and rationale, the recommendation *sign / negotiate / do not sign*. JSON with a constrained schema, objections first;
5. **confidence** from the logprobs of the `true` and `false` tokens; **dissent**, major or minor, between note and verdict; **quotes** looked up word for word in the contract.

The prompts are in English and the council writes its rationales in English, for a small Italian business; quotes stay in the contract's own language.

| File | What it does |
|---|---|
| `review/split.py` | finds the headings (numbered, all caps, alone on a line) and gives each clause to a role with keywords per contract family |
| `review/categories.py` | the categories of each benchmark, with an English description for the prompts and the Italian name for the pages |
| `review/prompts.py` | the prompts of the experts and of the rapporteur, the same in telepathy and in text |
| `review/schemas.py` | the JSON schemas of note and verdict, with bounded items and characters |
| `review/council.py` | `Council.review`: split, relay, notes, verdict, confidence and dissent |
| `review/confidence.py` | p(yes) from the observed logprobs, levels high / medium / low |
| `review/quotes.py` | check of the quotes against the text of the contract |
| `review/scoring.py` | F1, precision, recall, MCC and the "always yes" baseline on the (contract, category) pairs, for the verdict and for the notes; agreement between notes and verdict |
| `review/run.py` | runs the council on a subset and writes one review per line in `results/` |
| `review/data.py` | reads contracts, correct answers, annotated spans and the demo set from `council/data` |
| `review/view.py` | from the review to the view of the verdict page, and the page with the data inside |
| `review/configurations.py` | the eval's comparison configurations: solo agent and vote among 4 independent agents |
| `review/metrics.py` | the eval's metrics: strict F1, paired bootstrap, costs, G4, sabotages, dissents, calibration, amounts and dates, chart |
| `review/eval.py` | runs the eval and writes its report; on the test it starts only with the frozen pre-registration |
| `review/blind.py` | the blind manual check: neutral, shuffled sheets, a sheet to fill in and counts with the key |
| `review/calibration.py` | chooses the latent steps and proposes the confidence thresholds from the dev runs |
| `review/live.py` | the catalog of the judges' live reviews: contracts picked from a list, never an arbitrary text |
| `page/verdict.html` | the verdict page for the person |
| `review/showcase.py` and `page/showcase.html` | the council's part of the judges' site: index of the contracts in English and Italian and verdict pages, for `site/build.py --council` |

## Usage

```bash
cd council/review
uv venv -p 3.12.venv && uv pip install -p.venv -e../../engine -r../../engine/requirements.txt
.venv/bin/python -m pytest -q -m "not model" # 51 fast tests
.venv/bin/python -m pytest -q # 55 tests, with Qwen3-0.6B

# The contracts of the measurement set come from council/data/cache (prepare.py downloads them).
.venv/bin/python -m review.run --benchmark cuad --mode telepathy --steps 10 --model Qwen/Qwen3-1.7B
.venv/bin/python -m review.run --benchmark demo --mode text
.venv/bin/python -m review.run --benchmark cuad --steps 0 10 20 40 # calibration of the latent steps 
.venv/bin/python -m review.run --benchmark demo --no-realign --steps 0 10 40 # diagnosis 
```

- The demo set is in `council/data/demo-set`, outside the repo; `COUNCIL_DEMO_SET` points to another folder.
- `run` runs only on the **dev** subset. The test runs only once, with the pre-registered eval.
- The reviews end up in `results/`, one per line, with notes, verdict, confidences, dissents, checked quotes, tokens, time and message fingerprints.
- `--no-realign` turns off LatentMAS's W_a matrix on the latent steps, as LatentMAS does by default; the file name ends with `-no-realign`. The summary of each run also gives the F1 of the notes taken as the verdict and the agreement between notes and verdict, to see whether a flag gets lost in the experts or in the rapporteur.
- For the pre-registered tests and for the demo, `Council.review(..., thoughts_from=..., attacks=...)` passes the options to the engine's relay.

## The verdict page

`page/verdict.html` shows the person the verdict of a review, with the rules of "Verdict and dissent":

- at the top the recommendation *sign / negotiate / do not sign*, with its rationale;
- the rows of all the categories, grouped by expert: quote with the "found in the contract" or "not found" badge, rationale and confidence;
- the major dissent with a confident expert always highlighted, the other dissents open with a click. On each dissent the person chooses who is right;
- the seal: "communication between experts intact" with the message fingerprints, or the red notice without a verdict;
- "Show what each expert thought" opens the notes;
- "Download the summary (PDF)" prints recommendation, flagged clauses, dissents and choices; "Save the choices" downloads a JSON.

The page is bilingual (Italian and English): the client business starts from Italian, the judges' site from English.

```bash
.venv/bin/python -m review.view results/<run>.jsonl --contract <id> --title "Contract..." --output view.json --html verdict.html
```

With `--html` the page already contains the data: it is a single file, to open or attach. Without it, the page reads `?view=view.json` or a file chosen by hand.
`page/example.html` is the page of an invented review (`page/example-review.json`): it contains nothing from the demo set, which stays private.
To regenerate it:

```bash
.venv/bin/python -c "import json; from pathlib import Path; from review import BENCHMARK; from review.view import page, view; r = json.loads(Path('page/example-review.json').read_text); Path('page/example.html').write_text(page(view(r, BENCHMARK['demo'], 'Contratto di fornitura di componenti (esempio)')))"
```

The link with Evolus (email with the link to the page, choices sent back by the second workflow) waits for the integration with Evolus.

## The eval

The rules are in [`council/PREREGISTRAZIONE.md`](../PREREGISTRAZIONE.md), which must be frozen and committed before the test run.

```bash
# All the configurations with the model loaded once: telepathy, text, solo agent, vote among 4 and the three
# sabotage tests (zeroed thoughts, thoughts from another contract, swapped contract).
.venv/bin/python -m review.eval run --benchmark cuad --subset dev --steps 10 --output eval
.venv/bin/python -m review.eval run --benchmark demo --steps 10 --configurations telepathy text --output eval
.venv/bin/python -m review.eval report eval # report.md, numbers.json and one chart per benchmark

# Calibration, from the runs of review.run with --steps 0 10 20 40
.venv/bin/python -m review.calibration results --benchmark cuad
```

- Each configuration writes `<benchmark>-<subset>-<configuration>.jsonl`, in the shape of the council's reviews; `eval-<benchmark>-<subset>.json` gives model, dtype, device, steps, commit of the code and of the pre-registration.
- **On the test** `eval` starts only if the pre-registration is no longer a draft, is committed and the code in `council/` and `engine/` has no local changes. The test runs once: a second run needs `--deviation "reason"`.
- The report has aggregate numbers only and can be published; the `.jsonl` files contain sentences of the contracts and stay within the team.

## Choices

- **Split without an LLM.** Headings are recognized with rules on numbers, capitals and short lines:
  - tables of contents (a heading followed by a page number) and repeated lines (EDGAR headers and footers) are discarded;
  - unnumbered headings count only if there are at least three in the body of the text, so the addresses and signatures of a letter are not enough.

  The heading keywords are in `KEYWORDS`, for three families: commercial contracts (CUAD and the demo set), NDAs and ToS. They are in English and Italian, because the demo contracts and the CLAUDETTE ToS are Italian. Without a keyword the clause goes to the legal expert.
- **Bounded schemas.** At most 3 quotes per note and 8 details in the verdict, with a maximum of characters: note and verdict always close within 300 and 1,100 tokens.
- **Confidence.** The high / medium / low thresholds (0.9 and 0.7) are provisional: they are set on the dev set with Qwen3-14B.
- **Translation of the quotes** only with `translate=True`: it helps when the person reads a contract that is not in English, not in the eval.

## What is missing

- The trial with Qwen3-14B on the MI300X, the choice of the latent steps and the confidence thresholds: they need the GPU (G1).
- The full eval, with the comparison configurations and the sabotage tests, belongs to the pre-registered eval.
