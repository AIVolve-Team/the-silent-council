# Hackathon AMD ACT III

The shared language of the team's projects for the AMD Developer Hackathon ACT III.
It holds the terms of the Silent Council, the contract review in telepathy, those of the telepathic engine and of the truth machine, shared with the Help Desk, and those of the telepathic Help Desk, which examines invoices.

## Language

### Silent Council: trial contracts

**Measurement set**:
The contracts taken from public benchmarks with which the council is measured. It is the only source of the numbers to bring to the jury.
_Avoid_: test dataset, benchmark (when the chosen subset is meant)

**Demo set**:
The few Italian B2B contracts written by the team for the demo, with expected verdict and dissent. It never enters the numbers.
_Avoid_: trial contracts, synthetic contracts, the 20 contracts

**Clause to flag**:
A clause that a reviewer brings to the person's attention, whichever party of the contract they are. What counts is that it is there, not who it is a problem for.
_Avoid_: risky clause, unfair clause, red flag

**Correct answer**:
For each pair (contract, category), whether it should be flagged yes or no, with the text spans that prove it. It is written before measuring.
_Avoid_: ground truth, gold, label

### Telepathic engine and truth machine

**Latent message**:
What an agent passes to the next one instead of text: the memory of what it read and of its latent steps, with a label. There is one per agent, and in a row they give back the memory of the whole relay.
_Avoid_: envelope (only in conversation), KV cache (when the whole message is meant), embedding

**Relay**:
The sequence of agents in which each one receives the latent messages of the previous ones and adds its own. It exists in telepathy mode and in text mode, with the same agents and the same prompts.
_Avoid_: pipeline, chain (when the sequence of agents is meant)

**Seal**:
An agent's digital signature on its latent message, covering the whole message plus the sequence number and the hash of the previous message. It says that nobody touched the message after the signature, not that the content is true.
_Avoid_: HMAC, hash (when the seal is meant), encrypted

**Commitment**:
In the Help Desk, the invoice data that the extractor declares in clear next to its latent message, in JSON with a fixed schema. It is in the label, so it is covered by the seal.
_Avoid_: extraction, extractor output

**Reading**:
The critical invoice data that the verifier derives from the latent message, without seeing the invoice. It is compared with the commitment: if they do not match, the agent carried in its memory something different from what it declared.
_Avoid_: verification (when the reading is meant), second extraction

**Translator**:
The third level of the truth machine: it shows a person what a latent message contains. It is a window, not a defense: the defense remains seal and consistency.
_Avoid_: decoder, interpreter, logit lens (it is only one of the tools)

**Memory transcript**:
The text that a reader without tools, with the same model, copies word for word from the memory that the extractor passes to the verifier. The lines that are hidden text in the PDF are marked in red. It mostly shows what the agent read, not its thoughts: the thoughts alone, read with the logit lens, do not show the data.
_Avoid_: translation of the thoughts, reading of the thoughts, summary

### Help Desk: anomalies and attacks

> ⚠️ Superseded: the Help Desk is excluded from the hackathon and its code was removed from the repo on 13/10/2026 (tag `archivio/sportello`). The terms remain as history.

**Harmful action**:
What the Help Desk must never do, written as a publishable rule: paying twice, paying a beneficiary different from the registered one, paying an unknown or deactivated supplier, paying more than due, paying without an order.
_Avoid_: error, risk (when the action to prevent is meant)

**Anomaly**:
A defect of the invoice with respect to order and master data, which the generator inserts in the test invoices. Each one has an expected outcome: pay, pass to a person or block.
_Avoid_: attack, fraud (when the inserted defect is meant)

**Attack**:
A manipulation of the system, not of the invoice: for example a tampered latent message or hidden text in the PDF. The seal and the consistency stop it.
_Avoid_: anomaly

**Borderline invoice**:
A clean invoice built close to a rule without breaking it, for example with the price above the order within the tolerance. It serves to measure the false alarms.
_Avoid_: limit case, edge case

### Help Desk: outcome and case passed to a person

> ⚠️ Superseded: the Help Desk is excluded from the hackathon and its code was removed from the repo on 13/10/2026 (tag `archivio/sportello`). The terms remain as history.

**Outcome**:
The Help Desk's decision on an invoice: **pay** (a payment proposal is created), **pass to a person** (there is a doubt and the person decides) or **block** (a rule or a mismatch among the three witnesses denies the payment). If more than one fires, the most severe wins.
_Avoid_: verdict (it belongs to the council), escalation, rejection

**Three witnesses**:
Commitment, reading and payment proposal, which must match on the payment data. If they do not match, the outcome is block.
_Avoid_: double check, triangulation

**Case passed to a person**:
An invoice with outcome pass to a person or block. The person receives a notice email with the link to the case page, sees what does not add up and decides: approve, reject or report a fraud. A blocked case is approved only with a verification note made with the contacts in the master data.
_Avoid_: escalation, ticket, file

**Payment proposal**:
The payment that the Help Desk prepares when the outcome is pay, always to the IBAN in the master data, waiting for a person to approve it. The Help Desk never pays on its own.
_Avoid_: payment (until it is approved), bank transfer

**Case record**:
The file downloaded from the case page: outcome, checks, signatures of the messages and public keys, with the command to verify it yourself.
_Avoid_: incident record (the checker writes it when a seal fails), log, report
