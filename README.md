![The Silent Council: memory, not messages](assets/banner.jpg)

# Silent Council

**AIVolve at the AMD Developer Hackathon ACT III.**

The Silent Council reviews a business contract with a council of agents running on an AMD Instinct MI300X.
A legal expert, a finance expert and a risk expert each read their part of the contract. A rapporteur, the devil's
advocate, writes the verdict: a recommendation (sign, negotiate or do not sign), the clauses to flag with exact quotes,
and the dissents between the experts. A person then decides on each dissent from the verdict page.

The experts do not write to each other. They hand over their **memory**: each agent passes the next one a *latent
message* (the KV cache of what it read and of its latent steps), sealed with an Ed25519 signature that the next agent
checks before using it. The same council also runs in **text mode**, with the same agents and prompts, as the
baseline: the eval compares the two on public contract benchmarks.

Three things sit around the relay:

- **Institutional memory**: the company's
  playbook and the precedents its people decide on the verdict pages, read once and sealed at the head of every
  telepathy review. Each choice of the person becomes a precedent for the next contracts.
- **The visual mode**: a rule-based inspector finds the PDF pages
  with signatures, stamps, initials or scans; a visual expert, Gemma 4 31B, sees them as images at the head of the
  chain. In telepathy its memory holds the pages themselves, so the council answers questions about them that nobody
  planned for (on two contracts, 4 of 4 right in telepathy, 1 of 4 in text).
- **Questions afterwards** (`ask_council`): the server keeps the memory of the last reviews on the GPU, never on disk,
  and answers new questions on a case from it, without the contract.

Contracts arrive by email through [Evolus](council/evolus/README.md), which calls the council on the MI300X and sends
the notice to the person.

## Repository layout

| Folder | What it contains |
|---|---|
| [`engine/`](engine/README.md) | the telepathic engine: Qwen3 agents that pass latent messages, the relay, the seal and its verification |
| [`council/review/`](council/review/README.md) | the Silent Council on the engine: split of the contract by role, prompts, verdict, dissents, eval, verdict pages |
| [`council/service/`](council/service/README.md) | the council server: `review_contract`, `record_choices` and `ask_council` over MCP and HTTP, the visual mode, the institutional memory, the verdict page for the person |
| [`council/data/`](council/data/README.md) | the measurement set (CUAD, ContractNLI, CLAUDETTE) with its correct answers, and the demo set checks |
| [`council/evolus/`](council/evolus/README.md) | the Evolus workflow: from the email with the contract to the notice for the person, and its limits |
| [`site/`](site/README.md) | the judges' site on Vercel: recorded verdicts, live reviews while the MI300X is on, MI300X scheduling |
| [`g1/`](g1/README.md) | the first gate: the engine on the MI300X on GSM8K, telepathy against text, with the recorded results |

Domain terms are defined in [`CONTEXT.md`](CONTEXT.md). The end-to-end flow is in [`council/FLOW.md`](council/FLOW.md).

## Results and method

- [`council/PREREGISTRATION.md`](council/PREREGISTRATION.md): the eval rules, frozen before the test run.
- [`council/HOW-WE-MEASURE.md`](council/HOW-WE-MEASURE.md): how the numbers are measured, in plain words.
- [`council/CALIBRATION-MI300X.md`](council/CALIBRATION-MI300X.md) and
  [`council/REPLICATION-REPORT-MI300X.md`](council/REPLICATION-REPORT-MI300X.md): the runs on the MI300X.
- [`g1/RESULTS-MI300X.md`](g1/RESULTS-MI300X.md): the G1 results.

## Built during the hackathon

The hackathon ran from 12 to 18 October 2026. The commit history keeps its real dates: the work before 12 October is
the starting point we brought to the event.

**Before 12 October (2–9 October), the starting point:**

- the telepathic engine (`engine/`): Qwen3 agents that pass each other latent messages, the relay, the Ed25519 seal;
- the council on the engine (`council/review/`): roles, prompts, notes and verdict, a first verdict page, the trial
  on a Mac with one command;
- the measurement set (CUAD, ContractNLI, CLAUDETTE) and the fingerprints of the demo set;
- the code of the pre-registered eval and of the calibration, not yet run on the MI300X;
- a first council server for Evolus (two tools over MCP and HTTP) and a first judges' site with the MI300X scheduled
  in windows;
- G1, the first gate on GSM8K, ready to run.

**From 12 to 17 October, during the hackathon:**

- every run on the AMD Instinct MI300X: G1, the calibration of the latent steps, the pre-registered test (frozen on
  12 October, re-frozen on 13 October) and the replication on the 72 never-used CUAD test contracts, with their
  reports;
- the judges' site as it is now: the home page with the engine's demonstration, live reviews while the MI300X is on,
  recorded verdicts in English;
- routing by contract length, Qwen3-14B for short contracts and Gemma 4 31B for long ones, with the engine on
  transformers 5 and the fix for Gemma 4's sliding-window layers;
- the Evolus workflow tested end to end, from the email with the contract to the notice for the person;
- the specialists trial and the council against the solo agent;
- the visual mode: the PDF inspector, the visual expert with Gemma 4 reading the page images, and the PDF read from
  the contracts mailbox;
- the institutional memory: the company playbook and the person's precedents at the head of every review, taught from
  the verdict page;
- `ask_council`: questions on a reviewed case, answered from the memory of its review;
- the demo reviews recorded on the MI300X, the whole repository translated to English, and this README.

## Getting started

Requirements: Python 3.12 with [uv](https://docs.astral.sh/uv/), Node.js 20 or later.

Each Python package has its own virtual environment. For example, the engine:

```bash
cd engine
uv venv -p 3.12 .venv && uv pip install -p .venv -r requirements.txt
.venv/bin/python -m pytest -q -m "not model"   # fast tests, no model download
```

The same pattern works in `g1/`, `council/review/`, `council/service/` and `council/data/` (see each README).
Tests marked `model` download a small Qwen3 model and need several GB of free memory.

The judges' site:

```bash
cd site && npm test
```

To run the council on a real contract benchmark, follow [`council/TRIAL.md`](council/TRIAL.md) on a Mac or
[`council/MI300X.md`](council/MI300X.md) on the MI300X.

## Configuration and secrets

No secret is stored in the repository. The four secrets the project needs are read from environment variables, listed
in [`.env.example`](.env.example): on Vercel and in GitHub Actions they are set in the service settings.

## Data and licenses

The benchmark contracts and their annotations come from public datasets (CUAD, ContractNLI and the Italian
Terms of Service of multilingual CLAUDETTE, all under CC BY 4.0); sources and changes are in [`council/data/NOTICE.md`](council/data/NOTICE.md). The GSM8K problems used by G1
are under the MIT license ([`g1/NOTICE.md`](g1/NOTICE.md)). The models are Qwen3 and Gemma 4 from Hugging Face, at pinned revisions.
