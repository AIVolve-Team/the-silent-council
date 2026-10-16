# Pre-registration of the council's eval

> This is the English translation of the frozen pre-registration. The Italian original, as it was frozen, is
> `consiglio/PREREGISTRAZIONE.md` at commit `1bcb50c`. The rules, numbers and hashes are the same.
> After the freeze the files in the [Data](#data) tables were renamed:
> `consiglio/dati/set-di-misura/campione.json` → `council/data/measurement-set/sample.json`,
> `risposte-giuste.jsonl` → `correct-answers.jsonl`, `campione-replica.json` → `sample-replication.json`,
> `risposte-giuste-replica.jsonl` → `correct-answers-replication.jsonl` (same folder), and
> `consiglio/dati/set-dimostrativo.sha256` → `council/data/demo-set.sha256`.
> The tables keep the old paths because they name what was hashed. The hashes refer to the original files: for the
> measurement set, `council/data/test_prepare.py` rebuilds those files byte for byte from the renamed ones and checks
> each hash. The demo-set fingerprints file only changed its folder prefix (`set-dimostrativo/` → `demo-set/`); its
> hash refers to the file at commit `1bcb50c`.

Status: frozen on 13/10/2026

While the line above is still the draft line, `review.eval` does not run the test set.
To freeze the rules: fill in the points marked **to be fixed**, change the line to `Status: frozen on DD/MM/YYYY` and commit **before** the test run.
After that, the test runs only once, and every change is written among the [deviations](#deviations) with its reason.

The rules come from the team's decisions "Pre-registered eval of the council" and "Metrics and thresholds G1-G4", and from the notes on the data.
The **operational definitions** are new, written with the code of the eval: the team was to review them before the freeze. This was not done: see the [deviations](#deviations).

## Data

| File | SHA-256 |
|---|---|
| `consiglio/dati/set-di-misura/campione.json` | `3edaa8a7ae97019716d1c9b8ad3205c2836bb7b4b5b737327908e162b81751aa` |
| `consiglio/dati/set-di-misura/risposte-giuste.jsonl` | `c2b783c2a3c452683823b7c0d9113484c7193a451b7c4f025223a91824ee6675` |
| `consiglio/dati/set-dimostrativo.sha256` (fingerprints of the demo set) | `608bd5e51dc260a92aaafc151c041d80208de3204990702e58bf9dd910f280c6` |

- **Test set:** 20 CUAD contracts, 20 ContractNLI and 20 CLAUDETTE, the ones in `sample.json` (fixed seed, under 24,000 tokens).
- **Demo set:** the 4 Italian contracts, outside the repo until delivery. At delivery they are published and must match the fingerprints.
- **Split by role:** the contract is divided among the experts by headings (`review/split.py`), with no gaps: every annotated span of the test lies whole in one section. On the CUAD test set, though, 34 of the 74 pairs to flag (46%) lie in the section of an expert who does not have that category, almost always the legal expert, who acts as the fallback role. In text mode an expert writes only about their own categories, so those clauses risk being lost; in telepathy the rapporteur also works on the memory of their reading (see Configurations).
- **Labels:** pair (contract, category) → flag yes/no.
  CUAD has 19 categories, ContractNLI 17 hypotheses and CLAUDETTE 9 categories.

## Model and decoding

- **Qwen3-14B**, revision `40c069824f4251a91eefaf281ebe4c544efd3e18`, in bf16, on one MI300X, batch 1.
- **Environment:** the G1 engine container (`vllm/vllm-openai-rocm:v0.30.0`, with the image's ROCm torch), after the G1 fp32 versus bf16 comparison (`g1/README.md`, step 4): on ROCm the attention masks have had bugs. The guide is `council/MI300X.md`.
- **Greedy decoding** in every configuration, that is temperature 0: one run per configuration.
- **Latent steps: 0**, fixed with the calibration on the MI300X of 12/10/2026 (`mi300x.sh calibration`, section [Calibration on the MI300X](#calibration-on-the-mi300x)), on the CUAD dev set: 0, 10, 20 and 40 are tried, the highest F1 wins and, under 1 point of difference, the value with fewer steps. 0 won with F1 71.4, against 65.1 with 10 steps.
  - 10, 20 and 40 are the pre-registered values. The 0 is the *early check* of the thoughts: if it wins, the thoughts do not help on the dev set, and the rules allow the system to be corrected before the freeze.
  - On the Mac (M1 Max, 12/10/2026, without realignment) CUAD dev gave F1 68.8 with 0 steps and 56.2 with 10; text 51.6.
- **W_a realignment** of the latent steps: **off**, with the diagnosis of 12/10/2026 (Qwen3-14B on M1 Max). With it on, telepathy scored 28.6 on the demo set and 19.0 on CUAD dev; with it off, 98.2 and 68.8, against 78.3 and 51.6 for text. On Qwen3-14B, which has separate input and output embeddings, the realignment breaks the memory passed to the rapporteur.

## Configurations

All with the same model and the same schema of 19 rows (`review/schemas.py`).

1. **Solo agent:** reads the whole contract and writes the verdict without objections.
2. **4 independent agents and a vote:** legal, finance, risk and devil's advocate each read the whole contract, from their own point of view, and write a verdict without objections (`independent_instructions`).
   - For each category the majority of the valid verdicts wins.
   - On a 2-2 tie the group with the highest mean confidence wins, that is the mean probability of the chosen position. With equal confidence "yes" wins.
   - The recommendation is the most frequent one; on a tie, the most cautious (do not sign, then negotiate, then sign).
   - Tokens and times are the sum of the 4.
3. **Council in text mode.** Each expert writes an analysis of their section, at most **2,048 tokens** (`MAX_ANALYSIS_TOKENS`), and the rapporteur reads the analyses. With the engine's default of 512 tokens the calibration truncated all of them (9 out of 9); with 2,048 the longest in dev reaches 1,414. The report counts the analyses that hit the cap.
4. **Council in telepathy.** The rapporteur works on the memory of the reading of all the sections, that is of the whole contract, instead of on written analyses. This is the mechanism, and the report describes it that way. The rapporteur's prompt says "You have not read the contract" in both modes: in telepathy this is not literally true, but it stays as it was in the calibration.

On ContractNLI and CLAUDETTE the council has three members, that is legal, risk and rapporteur, in text mode too. The vote stays among 4.
JEV is not run: the 77.38% published on ContractNLI uses another metric, so it is only context, not a comparison.

## Scoring

- **F1 on the pairs (contract, category)**, one number per benchmark, never added up. CUAD is the main number. ContractEval (Qwen3-14B alone at 47.3) has a different task, categories and sample: it is context, not a like-for-like reference. The like-for-like reference is our configuration 1, the solo agent.
- Next to every F1: **missed clauses** and **false alarms**, **MCC** and the **"always yes"** baseline. For CLAUDETTE also the **grade 3 only** view.
- An invalid or missing verdict counts as "no" on all its pairs, and is counted separately.
- **Strict version.** A correct "yes" counts only if a quote of the verdict for that category **overlaps** an annotated span; otherwise it counts as a missed clause. False alarms stay false alarms.
  - *Overlaps* means having at least **5 words in a row** in common with the annotated span, or the whole quote if it is shorter. The comparison is made after the normalization of `quotes.normalize`: no capitals, double spaces, typographic quotes and apostrophes.
  - Quotes of fewer than 3 words do not count.
  - In the demo set the annotated spans are the quotes of the expected answers.

## Success criterion and G4

- **Quality.** F1 of telepathy minus F1 of text on CUAD is computed, with a **95% interval with a paired bootstrap**:
  - the **contracts** are resampled with replacement, the same ones for the two configurations, **10,000** times, with seed **62**;
  - the interval goes from the 2.5th to the 97.5th percentile;
  - if the lower bound too is within −3 points we say *"does not lose, shown"*, otherwise *"compatible results"*;
  - ContractNLI and CLAUDETTE are reported without a threshold and without a judgement.
- **Telepathy against the solo agent** on CUAD, with the same paired bootstrap, **without a threshold** and outside G4. It is the comparison that isolates the channel: in telepathy the rapporteur works on the memory of the reading of the whole contract, the solo agent reads the whole contract. On dev the solo agent was ahead (see Calibration on the MI300X).
- **Tokens.** All of them are counted, read and generated, separately and summed, notes for the person included. The **means per contract** are compared.
- **Time.** Seconds per contract on the MI300X, batch 1, mean over the contracts.
- **G4: the council can be delivered if**, on CUAD:
  - F1 telepathy ≥ F1 text − 3 points;
  - generated tokens at least −50%;
  - telepathy is not slower than text.

## Sabotage tests

All in telepathy, with the chosen latent steps.

- **Zeroed thoughts:** latent steps 0; the read sections remain.
- **Thoughts from another contract:** contract *i* receives, for each expert, the thoughts of the same expert on contract *i+1* in the order of the sample (the last one receives them from the first). The read sections stay correct. The engine recomputes the memory of the thoughts from those hidden states (`thoughts_from`).
- **Swapped contract:** the council reads contract *i+1* and is scored with the answers of contract *i*. It is the baseline check: it must collapse, otherwise there is a bug in the code.
- **What we say:**
  - *"The agents pass each other their thoughts"* is always said;
  - *"The thoughts improve the result"* only if the zeroed thoughts lower the F1 by **at least 2 points** and the thoughts from another contract lower it;
  - otherwise: *"The agents pass each other the memory of what they read instead of rewriting it: same quality, fewer tokens."*

**With 0 latent steps** there are no thoughts: the *zeroed thoughts* and *thoughts from another contract* tests are not run (the first would be the same run as telepathy, the second has no thoughts to swap) and the fallback sentence applies. The sentence that is always said also describes the mechanism for what it is: *"The agents pass each other the memory of what they read."* The *swapped contract* stays.

The sabotage tests do not block delivery: they decide the sentence.

## Metrics without a threshold

- **Who was right in the dissents** between the expert's note and the verdict:
  - in a major dissent (expert "yes", verdict "no"), how often the expert was right;
  - in a minor one (expert "no", verdict "yes"), how often the rapporteur was right.
- **Calibration of the verdict's confidence:** share of correct decisions per level high, medium and low, with the thresholds fixed in the calibration: **high from 0.9, medium from 0.7**. The calibration on CUAD says that no threshold reaches 9 correct decisions out of 10 (above 0.99, 89% are correct): the thresholds stay these, and the report says so.
- **Agreement between notes and verdict**, and F1 of the notes taken as a verdict.
- **Amounts and dates in the verdict**, only on the demo set: how many there are, and how many do not appear in the contract. An amount that is not in the contract is always reported, even if it happens only once.
- **By length (exploratory):** F1 of solo agent, telepathy and text on the CUAD test contracts above and below the median length, in Qwen3-14B tokens. It is computed from the `.jsonl` files after the test and reported as a hint, without a threshold: contracts above 24,000 tokens are excluded from the sample, so on really long texts the test says nothing.
- **CLAUDETTE** is unbalanced: 79% of the pairs are to be flagged and "always yes" scores F1 88.5. There MCC and the "always yes" baseline are what count.
- **Quality versus cost chart:** F1 against generated tokens per contract, for the 4 configurations.

## Manual check (demo set)

- It is done by a team member **who has neither written nor reviewed the expected answers**, blind: they do not know which verdict comes from text and which from telepathy.
- They judge: recommendation correct yes/no, expected dissent found yes/no, amounts correct.
- **Procedure** (proposed, to be reviewed): the organizer runs `python -m review.blind prepare <eval folder>`.
  - It produces one sheet per verdict, with neutral names (`verdict-01` …) and order shuffled with seed 31. Each sheet has recommendation, flagged clauses with quote, objections and dissents, with no mode, tokens, times or thoughts.
  - It also produces a form to fill in.
  - The checker receives sheets, form and contracts, but not the `.json` files of the expected answers.
  - The key (`key.json`) stays with the organizer, who counts at the end with `python -m review.blind count`.

## Calibration on the MI300X

12/10/2026, 1× MI300X (AMD Developer Cloud, ROCm 7.2), container `vllm/vllm-openai-rocm:v0.30.0` with torch `2.12.0+git6bbd260` and transformers 4.57.6, code at commit `1ad3b02`, realignment off. Full explanation in [CALIBRATION-MI300X.md](CALIBRATION-MI300X.md).

| F1 | 0 steps | 10 steps | 20 steps | 40 steps | text |
|---|---|---|---|---|---|
| CUAD, dev (5 contracts) | **71.4** | 65.1 | 58.5 | 61.5 (1 invalid verdict) | 52.6 |
| Demo set (4 contracts) | **98.2** | 98.2 | 98.2 | 98.2 | 76.6 |

- **Chosen steps: 0**, with the rule above. The rules for 0 steps of the [sabotage tests](#sabotage-tests) apply: no tests on the thoughts, fallback sentence, the swapped contract stays.
- **Confidence thresholds: 0.9 and 0.7**, as above.
- **Pair-by-pair agreement** of the verdict's yes/no with the Mac runs on the same code (12/10/2026): CUAD 98.7% with 0 steps, 96.1% with 10, 98.7% in text mode (4 contracts in common, 76 pairs each); demo set 100% with 0, 10 and 40 steps. No divergence to look into before the test.

**Trial of 13/10/2026 on CUAD dev, after the review of the metrics**, with the new cap on the text analyses (same machine, same model):

| Configuration | F1 | Generated tokens per contract | Seconds per contract |
|---|---|---|---|
| Solo agent | **76.2** | 586 | 31 |
| Council in telepathy, 0 steps (12/10) | 71.4 | 1,217 | 70 |
| Council in text mode, analyses up to 2,048 tokens | 58.5 | 4,767 | 169 |
| Council in text mode, analyses at 512 tokens (12/10) | 52.6 | 2,776 | 103 |

No analysis hits the new cap (the longest is 1,414 tokens). The chosen steps do not change: the rule looks only at telepathy.

## Replication on CUAD

Decided on 13/10/2026 around 13:25, while the test was still running on ContractNLI and before its report existed: it is done **whatever the result of the test**. On CUAD the F1 per configuration was already known (solo agent 75.9, vote among 4 74.8, telepathy 72.5, text 70.7), not the intervals. The first version planned 50 contracts drawn at random. On the evening of 13/10/2026 it moved to all 72, for the GPU time requested by the team.

- **Why:** with 20 contracts the 95% interval of the F1 differences is wide, and differences of 2-3 points cannot be told apart from chance. With 92 contracts it narrows to about 0.47 times.
- **Contracts:** all the CUAD test contracts under 24,000 tokens (Qwen3-14B tokenizer, as in the test), **excluding the 20 of the test**: they are 72, with no drawing. 1,368 pairs, 244 to flag. The files are separate, so the test ones stay those of the table in [Data](#data):

  | File | SHA-256 |
  |---|---|
  | `consiglio/dati/set-di-misura/campione-replica.json` | `6efc690d4432877859bb534eca96d850c677bd62c0d4db1a8c8c5d46818bf6b1` |
  | `consiglio/dati/set-di-misura/risposte-giuste-replica.jsonl` | `61eeab9edcfe3e88bb7f184fbd095d1e02bd78e043747666467d075d8d5cb7d4` |

- **Configurations:** telepathy (0 steps), text (analyses up to 2,048 tokens) and solo agent. The vote among 4 and the sabotage tests are not repeated: the test has already measured them.
- **Same code and same rules as the test:** model, revision, decoding, environment, W_a off, metrics and paired bootstrap (10,000 repetitions, seed 62). **It runs only once**: a second run is a deviation, as for the test.
- **What is reported:** test (20), replication (72) and total (92), each with F1, tokens and time, and with the 95% interval of telepathy against text and of telepathy against the solo agent. The total resamples the test and replication contracts together.
- **G4 stays decided on the test of 20.** On replication and total the *"does not lose, shown"* judgement is not given. The replication **confirms** G4 if the three conditions of G4, computed on the replication alone, give the same outcome as the test (passed in both, or failed in both); if not, it **contradicts** it. The replication alone is used, not the total, because the total contains the test.
- **How to run it:** `STEPS=0 ./council/mi300x.sh replication`, after the end of the test. The script links the CUAD runs of the test and writes the report with the three sections.

## How to run it

In the G1 engine container, from the root of the repo (the guide is `council/MI300X.md`):

```bash
STEPS=<fixed steps> ./council/mi300x.sh test
```

`mi300x.sh` runs the four benchmarks with the realignment off and writes the report. By hand these are the commands:

```bash
cd council/review
.venv/bin/python -m review.eval run --benchmark cuad --subset test --steps <fixed steps> --no-realign --output eval-test
.venv/bin/python -m review.eval run --benchmark contractnli --subset test --steps <fixed steps> --no-realign --output eval-test
.venv/bin/python -m review.eval run --benchmark claudette --subset test --steps <fixed steps> --no-realign --output eval-test
.venv/bin/python -m review.eval run --benchmark demo --steps <fixed steps> --no-realign --output eval-test
.venv/bin/python -m review.eval report eval-test
```

On the test the command checks that this file is frozen and committed, and that the code in `council/` and `engine/` has no local changes. In `eval-<benchmark>-test.json` it writes the commit of the code and the one of this file.

## Deviations

1. **Frozen without the team's review of the operational definitions** (line at the top). On 12/10/2026 we chose to freeze and launch the test right after the calibration, to have the numbers before the G4 of 16/10. The review is still to be done afterwards: if it finds a mistake, it is written here and the report says so, without silently rerunning the test.
2. **The G1 fp32 versus bf16 comparison** (section Model and decoding) ran with the fp32 reference on the SDPA math backend instead of the fast kernels only, which in fp32 stopped with `No available kernel` (commit `903d2ee`, explained in [g1/RESULTS-MI300X.md](../g1/RESULTS-MI300X.md)). Identical answers 5 out of 5. The council run does not change.
3. **Reopened and frozen again on 13/10/2026, before the test.** A review of the metrics, of the correct answers and of the fairness of the comparison found that text started at a disadvantage: analyses truncated at 512 tokens, all of them. The correct answers were regenerated from the sources and are identical; the formulas are correct. Changes, in the code and here:
   - cap of the text analyses from 512 to 2,048 tokens, with the count of the truncated ones;
   - telepathy against solo agent comparison in the report, without a threshold;
   - "shown" only on CUAD, as already written in Success criterion;
   - exploratory analysis by length;
   - the notes on the split by role, the rapporteur's prompt, the external references and CLAUDETTE.

   The test had not run yet: these are rules fixed before seeing its results. The dev numbers of the solo agent were, however, already known: they motivated the extra comparison, without changing G4.
