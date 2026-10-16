# How we measure the council

An explanation for the whole team, without code: what the council's eval measures, how it scores and how the systems are compared.
The official rules, fixed before measuring, are in the pre-registration: [`council/PREREGISTRATION.md`](PREREGISTRATION.md).

## 1. The question

Given a contract, **which types of clause does it contain?**
On CUAD, the main benchmark, there are 19 types: for example "cap on liability", "exclusivity", "automatic renewal", "non-compete".
For each contract and each type the answer is **yes or no**.

## 2. The material: contracts with the correct answers

- **CUAD** is a public dataset of real commercial contracts in which **lawyers** annotated, clause by clause, where each type is.
- Those annotations give the **correct answer**: "yes" if the lawyers found at least one span of that type in the contract, "no" otherwise.
- The test uses **20 contracts** that nobody looked at during development. With 19 types they make **380 questions** with a known answer.

The unit of measure is the **pair (contract, clause type)**.

## 3. The flow: what happens to each contract

1. The contract goes to the system under evaluation.
2. The system returns a **verdict** in a fixed format, the same for everyone:
   - for each of the 19 types, **yes or no**;
   - for each "yes", a **quote** from the contract as evidence;
   - a **recommendation**: sign, negotiate or do not sign.
3. The **costs** are recorded: tokens read, tokens generated, seconds.
4. The **confidence** is recorded: for each yes/no, the probability the model gave it, read from its internal probabilities.
5. The verdict is compared with the correct answers.

## 4. The systems compared

The same model, **Qwen3-14B**, with the same decoding rules, on the same MI300X. Only the way the work is organized changes.

| Configuration | How it works | What it is for |
|---|---|---|
| **Solo agent** | One model reads the whole contract and decides | Is a group really needed? |
| **Vote among 4** | Four experts read everything, each on their own; the majority wins | Is a group that does not communicate enough? |
| **Council in text mode** | Three experts read one section each and write each other their analyses; a rapporteur decides | The group that communicates in writing |
| **Council in telepathy** | As above, but the experts pass each other the **memory of their reading** instead of writing it | Our system |
| **Swapped contract** | The system reads one contract and is scored with the answers of another | Check: the score must collapse |

## 5. How the score is given

Each pair (contract, type) ends up in one of four boxes:

| | Correct answer **yes** | Correct answer **no** |
|---|---|---|
| The system says **yes** | ✅ found (true positive) | ❌ false alarm |
| The system says **no** | ❌ missed | ✅ correct silence |

From these boxes, summed over all the contracts:

- **Precision:** of the clauses the system flagged, how many were real? It measures the **false alarms**.
- **Recall:** of the real clauses, how many did it find? It measures the ones that **slipped through**.
- **F1:** the harmonic mean of precision and recall, from 0 to 100. It is **the main score**. It is high only if the system finds the clauses **without inventing any**: a system that flags everything has high recall and low precision, one that flags little the opposite, and in both cases the F1 stays low.
- **MCC:** from −1 to 1. It also takes the correct "no" answers into account and is useful when the "yes" answers are few.
- **"Always yes":** the F1 of a fake system that always says yes. It is the **floor**: on the CUAD test set it is 32.6, and a serious system must be well above it.

### An example

A contract has 4 real clauses among the 19 types. The system flags 5: 3 right and 2 wrong.
- Precision = 3 / 5 = 60%
- Recall = 3 / 4 = 75%
- F1 = 2 × 60 × 75 / (60 + 75) ≈ 67

The official F1 is **not** the mean of the F1 of the single contracts: the found, false alarms and missed of **all** the contracts are summed and the F1 is computed only once.

### Two strictness rules

- **Invalid or missing verdict:** it counts as "no" on all its types, and is reported separately. A system that gets the format wrong is not rewarded.
- **Strict F1:** a correct "yes" counts only if the **quote** matches the span annotated by the lawyers, with at least 5 words in a row in common. It checks that the system found **the** clause, not that it guessed.

## 6. The cost

- **Generated tokens:** how much the system writes, that is notes, analyses and verdict. On the GPU every generated token is compute time.
- **Read tokens:** how much text the model processes as input.
- **Seconds per contract:** real time on the MI300X, one contract at a time (batch 1), so the times are comparable.

## 7. How two systems are compared

With 20 contracts a difference of 2-3 F1 points can be luck. To find out, the **paired bootstrap** is used:

1. 20 contracts are drawn at random from the 20, with repetitions, **the same ones for the two systems**;
2. the F1 difference is recomputed;
3. this is repeated **10,000 times**, with a fixed seed.

The result is a **95% interval**, for example "telepathy minus text: from −4 to +7 points". If the interval contains zero, the difference is not certain.

## 8. The success criterion (G4, on CUAD)

The council in telepathy **can be delivered** if:

1. **quality:** F1 of telepathy ≥ F1 of text − 3 points. To say *"does not lose, shown"* the **lower bound** of the interval must also be within −3;
2. **cost:** at least **50% fewer generated tokens** than text;
3. **speed:** telepathy is not slower than text.

Next to it, **without a threshold**, telepathy against the solo agent is reported: it is the comparison that isolates the effect of the channel.

## 9. Why it can be trusted

- **Pre-registration:** all the rules above were written and committed **before** running the test, with date and commit. Every change is written among the deviations, with its reason.
- **Only once:** the test runs once. Running it again is a deviation to be declared.
- **Dev and test kept apart:** the number of telepathy steps was chosen on other contracts (the calibration), never on the test ones.
- **Correct answers checked again:** before the test they were regenerated from scratch from the original sources, and they were identical.
- **Swapped contract check:** if the system did not really read the contract, the score would not collapse.
- **Blind manual check** on the Italian demo contracts: a team member judges the verdicts without knowing which system they come from.

## 10. What this measure does not say

- It says whether a system **finds the right clause types**, not whether a contract is good or bad for the client.
- The contracts are under 24,000 tokens: on very long documents it says nothing.
- Twenty contracts are enough to see large differences; for differences of 2-3 points the replication on 72 new contracts is needed.
- It does not measure the value that is not F1: notes per role, visible dissents, signed chain of messages.

## In 30 seconds

> "We take real contracts in which lawyers have already marked the clauses. For each contract the system says which of 19 clause types it contains, with a quote as evidence. We compare its answers with the lawyers' ones and compute the F1: how many clauses it finds without inventing any. We compare four ways of organizing the same model, with the rules written before measuring and a confidence interval on every difference."
