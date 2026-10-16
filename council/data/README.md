# council/data — the council's measurement set and demo set

The rules come from the team's decisions "Benchmarks and trial contracts" and "Council setup".
The terms (measurement set, demo set, clause to flag, correct answer) are the ones in `CONTEXT.md`.

`prepare.py` downloads CUAD, ContractNLI and CLAUDETTE's Italian ToS from the official sources, at pinned versions and with their hash checked.
It then counts the Qwen3 tokens of each contract, draws the sample with a fixed seed among the contracts under the token cap and writes the correct answer for each (contract, category) pair.

| File | What it contains |
|---|---|
| `prepare.py` | download, token count, sample and correct answers |
| `categories.py` | the categories of each benchmark and the role that reviews them |
| `test_prepare.py` | tests of the yes/no rules and of the reading of CLAUDETTE's tags |
| `demo.py` | checks the demo set and writes its hash |
| `test_demo.py` | tests of the checks on the demo set |
| `measurement-set/sample.json` | the drawn contracts, by benchmark and subset |
| `measurement-set/correct-answers.jsonl` | one row per (contract, category) pair of the drawn contracts |
| `measurement-set/sample-replication.json` | the 72 contracts of the CUAD replication |
| `measurement-set/correct-answers-replication.jsonl` | the correct answers of the replication, one row per pair |
| `measurement-set/counts.json` | how many contracts fit under the token cap, with median, p90 and max |
| `measurement-set/tokens-per-contract.csv` | the Qwen3 tokens of every contract of the three benchmarks |
| `NOTICE.md` | attributions and licences of the data |

## Usage

```bash
cd council/data
uv venv -p 3.12 .venv && uv pip install -p .venv -r requirements.txt
.venv/bin/python -m pytest -q
.venv/bin/python prepare.py                 # 24k cap; --token-cap 12000 is the fallback decided in the council setup
.venv/bin/ruff check . && .venv/bin/ruff format --check .
```

The downloaded files stay in `cache/`, out of the repo.
Two runs of the script produce the same files.

The files of the measurement set were renamed to English (file names, keys and enum values) after the pre-registration, which pins the hashes of the Italian originals.
The content is unchanged: `test_prepare.py` rebuilds the original bytes from the committed files and checks them against the pre-registered hashes.

## Rules

- **Token cap:** 24,000 Qwen3 tokens, counted on the contract text only with the Qwen3-14B tokenizer.
- **Sample:** seed 60, an independent draw per benchmark and subset.
  - CUAD and ContractNLI: 5 dev contracts from the *train* split and 20 test contracts from the official *test* split.
  - CLAUDETTE, which has no official split: 20 test contracts, and all the others under the cap as dev.
  - CUAD replication: all the test contracts under the cap that the test did not use, 72, with no draw. It lives in separate files because the test ones are pinned by hash in the pre-registration.
- **Correct answer:**
  - CUAD: "yes" if there is at least one annotated piece of text for one of the 19 categories. The answers come from `CUADv1.json`; the split files are only used to know which split a contract belongs to.
  - ContractNLI: "yes" if the hypothesis is labelled Contradiction; the original label stays in the row.
  - CLAUDETTE: "yes" if at least one clause of the category has grade 2 or 3; grade 3 alone is in the `should_flag_grade_3` field.
- **Fixes to CLAUDETTE:** two badly closed tags in the Italian ToS (Weebly and Yelp), fixed as in the English version of the same ToS. They are in `CLAUDETTE_FIXES`, and the script stops if the original text changes.

## Sample numbers (24k cap)

| Benchmark | Under the cap | Test: pairs | Test: to flag | F1 of always saying "yes" |
|---|---|---|---|---|
| CUAD | train 357/408, test 92/102 | 380 | 74 (19%) | 32.6 |
| ContractNLI | 423/423, 123/123 | 340 | 38 (11%) | 20.1 |
| CLAUDETTE | 42/50 | 180 | 143 (79%) | 88.5 |

On CLAUDETTE almost every pair should be flagged: a system that always says "yes" already gets F1 88.5.
On grade 3 alone (46 pairs out of 180) the same baseline drops to F1 40.7.
Decided by the team: the eval reports next to each F1 the "always yes" baseline and the MCC, which is 0 for always saying "yes", and for CLAUDETTE also the view on grade 3 alone.

## Roles per benchmark

Decided on 6/10/2026, in `categories.py`:

- **CUAD and the demo set:** legal, finance, risk and the rapporteur, with the table of the council setup.
- **ContractNLI and CLAUDETTE:** none of the 17 hypotheses and 9 categories is financial, so finance is not convened and the council has three members: legal, risk and the rapporteur.
  - ContractNLI: legal gets what is confidential and intellectual property (8 hypotheses), risk gets use, sharing and duration of the obligations (9).
  - CLAUDETTE: legal gets liability, arbitration, jurisdiction, governing law, acceptance by use and privacy (6), risk gets unilateral change, unilateral termination and content removal (3).
- `READERS` gives, for each benchmark, the roles that read a section in relay order; the rapporteur always closes it.

## Demo set

The Italian B2B contracts written by the team live in `demo-set/`, which git ignores: they stay out of the repo until delivery.
Each contract is a `<name>.txt` file next to its expected answer `<name>.json`, in the format of "Verdict and dissent":

- the `recommendation` (`sign`, `negotiate` or `do not sign`) with its `rationale`;
- the 19 CUAD `rows`, each with `category`, `role` and `should_flag`, plus `quote` and `rationale` for the "yes" rows;
- the `expected_dissent`: where an expert's note and the verdict may plausibly disagree (`expected_note` and `expected_verdict`, one `yes` and one `no`), its `type` (`major` or `minor`), `who_is_right` (`expert` or `verdict`) and `why`;
- the `amounts_and_dates` the verdict must report correctly.

```bash
.venv/bin/python demo.py           # checks quotes, amounts, categories and dissents
.venv/bin/python demo.py --hash    # after the review: writes demo-set.sha256
shasum -a 256 -c demo-set.sha256   # at delivery, to check that the set has not changed
```

Only `demo-set.sha256` goes in the repo, written after a team member has reviewed the set.
Whoever reviews the set does not do the eval's manual check.
