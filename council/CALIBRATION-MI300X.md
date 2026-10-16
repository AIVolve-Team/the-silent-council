# Calibration of the council on the MI300X (12/10/2026)

**In short: 0 latent steps win.**
On the dev set telepathy beats text in quality (F1 71.4 against 52.6 on CUAD) and costs less: less than half the tokens generated and about a third less time.
The agreement with the Mac runs is between 96 and 100%, so the pre-registered test can start after the freezing.

Rules: [PREREGISTRATION.md](PREREGISTRATION.md). Procedure: [MI300X.md](MI300X.md).
Here there are only aggregate numbers. The `.jsonl` files of the demo set contain sentences of the contracts and stay private.

## What we calibrated

The calibration tunes **two things** before the test, on the **dev** set. You choose on one set and measure on another, only once: that way the result of the test cannot be "adjusted".

1. **The latent steps**, the knob of telepathy. Each agent reads its section of the contract and passes its working memory (the KV cache) to its colleague. Before passing it, it can "think in silence" for a few steps: each step is a word the model adds to the memory without writing it. 0, 10, 20 and 40 steps are tried.
   - **Rule** (pre-registration): on the CUAD dev set the highest F1 wins and, within 1 point of difference, the value with fewer steps.
2. **The confidence thresholds.** For each clause the council also says how sure it is, a probability from 0 to 1. The verdict page shows a label, high, medium or low. The calibration checks whether the labels tell the truth: when it says "high" it should be right at least 9 times out of 10.

## The metrics

For each contract there is the list of clauses to flag, with the correct answer (CUAD: expert annotations; demo set: ours). For each clause the council says yes or no.

| Metric | What it measures |
|---|---|
| **Precision (P)** | Of the clauses flagged, how many really had to be flagged: the false alarms |
| **Recall (R)** | Of the clauses to flag, how many it found: the ones that slipped through |
| **F1** | The mean of precision and recall, from 0 to 100: the quality score |
| **MCC** | Correlation between answers and truth, from −1 to 1; it also counts the correct "no"s |
| **Notes as verdict** | The F1 if the notes of the single agents were used instead of the final verdict |

## The results

Qwen3-14B in bf16 with the W_a realignment off, as decided by the diagnosis of 12/10/2026.

### CUAD (public, 5 dev contracts)

| Mode | Steps | F1 | P | R | MCC | Tokens generated per contract | Seconds per contract |
|---|---|---|---|---|---|---|---|
| telepathy | **0** | **71.4** | 71.4 | 71.4 | 0.63 | 1,217 | 70 |
| telepathy | 10 | 65.1 | 63.6 | 66.7 | 0.55 | | |
| telepathy | 20 | 58.5 | 60.0 | 57.1 | 0.47 | | |
| telepathy | 40 | 61.5 | 66.7 | 57.1 | 0.52 | | |
| text | | 52.6 | 58.8 | 47.6 | 0.41 | 2,776 | 103 |

With 40 steps one verdict in 5 is not valid.

### Demo set (Italian, private, 4 contracts)

| Mode | Steps | F1 | P | R | MCC | Tokens generated per contract | Seconds per contract |
|---|---|---|---|---|---|---|---|
| telepathy | 0, 10, 20, 40 | **98.2** | 96.6 | 100 | 0.97 | 1,438 (0 steps) | 67 (0 steps) |
| text | | 76.6 | 94.7 | 64.3 | 0.69 | 2,894 | 101 |

### Steps chosen: **0**

With the pre-registration's rule 0 steps win (F1 71.4 on CUAD). On the demo set the steps change nothing.
By the pre-registered rules, with 0 steps the tests on the thoughts are not run and the fallback sentence applies for the jury.

It is the same pattern seen elsewhere:
- on the Mac, CUAD: 68.8 with 0 steps against 56.2 with 10;
- G1 on GSM8K: 98 out of 100 with 0 steps against 96 with 10 ([g1/RESULTS-MI300X.md](../g1/RESULTS-MI300X.md)).

**The value of telepathy lies in handing over the memory of the reading, not in the extra thinking.** This holds for the model as it is, without training: training it to use the steps is a proposal for after the hackathon.

### Quality, not only cost

With 0 steps telepathy **finds many more risky clauses** than text:
- **recall:** 71 against 48 on CUAD, 100 against 64 on the demo set;
- **precision:** it does not drop; it even rises a little.

A possible explanation: in text each agent summarises and loses details, in telepathy the colleague receives the whole memory of the reading.

### Confidence: the model is overconfident

Decisions (verdicts and notes) of telepathy and text, with 0 steps:

| Confidence | CUAD: decisions | CUAD: correct | Demo: decisions | Demo: correct |
|---|---|---|---|---|
| 0.50–0.60 | 2 | 100% | | |
| 0.60–0.70 | 4 | 75% | | |
| 0.70–0.80 | 9 | 67% | 1 | 100% |
| 0.80–0.85 | 1 | 100% | | |
| 0.85–0.90 | 4 | 75% | | |
| 0.90–0.95 | 7 | 86% | 1 | 100% |
| 0.95–0.99 | 14 | 64% | 2 | 100% |
| 0.99–1.00 | 149 | 89% | 148 | 97% |

- **On CUAD no threshold reaches 9 correct decisions out of 10:** even above 0.99 89% are correct. Almost all decisions are above 0.99, so the "high" label does not tell the sure decisions from the doubtful ones.
- **On the demo set** the script proposes 0.60 for both thresholds, but with 4 cases below 0.99 the figure does not hold up.
- **Thresholds confirmed** from before the calibration: 0.9 for "high" and 0.7 for "medium". In the pre-registration the confidence calibration is a **metric without a threshold**: it is reported, it does not decide the verdict. It must be written clearly that today "high" does not mean "trust it without checking".

## Agreement with the Mac

Same code, same contracts, the verdict's yes/no compared clause by clause between the Mac runs (diagnosis of 12/10) and those of the MI300X:

| Run | Contracts in common | Pairs | Agreement |
|---|---|---|---|
| CUAD, telepathy 0 steps | 4 | 76 | 98.7% |
| CUAD, telepathy 10 steps | 4 | 76 | 96.1% |
| CUAD, text | 4 | 76 | 98.7% |
| Demo, telepathy 0 steps | 4 | 76 | 100% |
| Demo, telepathy 10 steps | 4 | 76 | 100% |
| Demo, telepathy 40 steps | 4 | 76 | 100% |

The divergences are few and consistent with different hardware (MPS in fp32 on the Mac, ROCm in bf16 on the MI300X). No reason to stop before the test.

## Caveats

- **Few contracts:** it is the dev set, which is for calibrating, not for proving. The official number comes from the **test**: CUAD, ContractNLI and CLAUDETTE, with the rules frozen beforehand.
- **We wrote the demo set ourselves**, so it is indicative. The solid figure is CUAD.

## Next steps

1. **Freezing** on this branch:
   - the steps at 0;
   - the thresholds;
   - the "Calibration on the MI300X" section of the pre-registration, from this document;
   - someone on the team rereads the operational definitions;
   - `Status: frozen`, commit and push.
2. **Test**, only once: `STEPS=0 ./council/mi300x.sh test` (then `PASSI=0 ./consiglio/mi300x.sh test`; see MI300X.md, step 5).

## Machine and times

- **Machine:** AMD Developer Cloud, 1× MI300X with 192 GB, ROCm 7.2.
- **Software:** image `vllm/vllm-openai-rocm:v0.30.0`, torch `2.12.0+git6bbd260`, transformers 4.57.6.
- **Code:** branch `feat/eval` at commit `1ad3b02`.
- **Quick trial:** `Done.` (then `Fatto.`), `GPU: cuda`, weights in bfloat16; telepathy with 10 steps on the demo set F1 98.2, as on the Mac.
- **Calibration:** from 17:59 to 18:59 (Italian time), about an hour for 45 reviews.
