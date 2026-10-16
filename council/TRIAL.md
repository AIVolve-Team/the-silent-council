# Trying the Silent Council

One command prepares everything, runs the council on the contracts and opens the verdict page.

```bash
git clone https://github.com/AIVolve-Team/the-silent-council.git
cd the-silent-council
./council/trial.sh
```

Since 12/10/2026 all the work is on `main`, the branch the clone starts on. If you had already cloned the repo, switch to `main` with `git fetch origin && git checkout -B main origin/main`, even if your `main` had fallen behind; if there are unsaved changes git stops, and you need `git stash` first.

On a Mac there is also `council/trial.command`: with a double click in the Finder the trial starts in a Terminal window of its own, which stays open at the end with the summary. To start it from Claude Code see [With Claude Code](#with-claude-code).

While it runs, the Mac does not go to sleep on its own: just keep it plugged in and with the lid open.

## What you need

- **A Mac with an Apple chip and at least 64 GB of memory**, or Linux with an NVIDIA GPU of at least 48 GB, to use **Qwen3-14B**, the council's model. With less memory the script picks a smaller model by itself (8B, 4B), which only shows that everything works. On a PC what counts is the graphics card's memory, not the RAM: with a 24 GB GPU the script uses the 4B.
- Below 80 GB the longest CUAD contract (22,863 tokens) is skipped: the council would keep up to three copies of it in memory, and with the 14B that is estimated at about 46 GB for that contract alone.
- **About 40 GB free on disk**: 30 for the model, the rest for data and libraries.
- **Internet** for the first run.
- **Nothing else**: the script prepares Python and the libraries. If `uv`, the Python manager, is missing, it installs it in the user's folder, without `sudo`.

On Windows the script must be launched inside WSL2 (Ubuntu).

## What it does

| Step | What | Time, the first time |
|---|---|---|
| 1 | Looks at memory and GPU, picks the model | right away |
| 2 | Python 3.12 and libraries, at pinned versions, in `council/.venv` | a few minutes |
| 3 | Fast tests of engine, data and council, without a model | one minute |
| 4 | Downloads CUAD, ContractNLI and CLAUDETTE and checks their fingerprints | one minute |
| 5 | Looks for the demo set and checks its fingerprints (see below) | right away |
| 6 | Downloads the model: Qwen3-14B weighs about 30 GB | depends on the network |
| 7 | Runs the council, in telepathy and in text | see below |
| 8 | Writes the verdict pages and opens the first one | right away |

With Qwen3-14B on a 64 GB Mac, step 7 should take **about 2-3 hours** for the full run (4 demo contracts and 4 CUAD ones, each in telepathy and in text), longer on older chips. With `--quick` only telepathy runs, on the demo contracts: **about half an hour**.

Running it again is safe: what is already downloaded is not downloaded again, and the results of the previous run are overwritten.

## What to look at

At the end the script prints a summary for each run and opens the page of the first contract.

- **The verdict page** (`council/results-trial/pages/`): recommendation, clauses to flag, dissent among the experts, quotes with the "found in the contract" badge. There is one per contract and per mode.
- **The summary** of each run:
  - valid verdicts and notes;
  - F1, the 0 to 100 score on the clauses found, with the "always yes" baseline next to it;
  - tokens written and read and seconds per contract.

  The comparison that counts is **telepathy against text**: the same quality (at most 3 F1 points less) with fewer tokens and less time.
- **The complete reviews** (`council/results-trial/*.jsonl`): everything the experts and the rapporteur wrote, with confidences, dissents, tokens and times.

These are numbers from the **dev set**, to see how it goes. The numbers for the jury come from the pre-registered eval, on the test set and on the MI300X.

The summary also has two numbers that say **where a flag gets lost**, in the experts or in the rapporteur:

- **notes as verdict**: the F1 the council would have if the verdict were made by putting the experts' notes together;
- **notes and verdict agree**: on how many categories the rapporteur says the same as the expert who looks at them.

If the notes are good and the verdict is not, the problem is in the rapporteur.

## The diagnosis trial

With Qwen3-14B, in the trial of 8/10, in telepathy the experts' notes were good while the rapporteur's verdict was not. The diagnosis is there to understand why:

```bash
./council/trial.sh --diagnosis
```

On a Mac there is also `council/diagnosis.command`, which does the same thing in a Terminal window of its own (double click in the Finder, or `open council/diagnosis.command`).

- It runs **telepathy only** and **only on the 4 contracts of the demo set**, which must therefore be there (see [The demo set](#the-demo-set)).
- It **turns off the realignment** of the latent steps: a correction of the experts' "thoughts" before passing them on (LatentMAS's W_a matrix). In the council it is on; in LatentMAS it is off by default.
- It does **three runs**, with 0, 10 and 40 latent steps, the steps in which each expert "thinks" without writing. The model is loaded only once.
- With Qwen3-14B on a 64 GB M1 Max Mac it takes **about an hour**. With models smaller than the 8B the realignment changes almost nothing: the trial only shows that everything works.
- The results go to `council/results-trial/diagnosis/`, so those of the normal trial stay. At the end the script prepares the zip `council/results-trial/diagnosis.zip`.
- **The zip contains sentences of the demo set:** send it privately to whoever asked for it, never on GitHub.

How to read the numbers, comparing them with the trial of 8/10 (10 steps with realignment):

- **with 0 steps** the rapporteur receives only the memory of what the experts read, without "thoughts": if the verdict stays broken, the rapporteur cannot find the information in the others' memory without having the contract in front of it;
- if instead **with 0 and 10 steps without realignment** the verdict comes back close to the text one, the culprit is the realignment;
- if it goes well with 0 steps but not with 10, even without realignment, what confuses the rapporteur is the "thoughts" themselves.

## The check on CUAD

The diagnosis of 12/10 blamed the realignment: without it, telepathy on the demo set reaches F1 98.2, with 0, 10 and 40 steps. Before freezing the pre-registration this must be confirmed on the CUAD dev contracts, where G4 is measured:

```bash
./council/trial.sh --diagnosis-cuad
```

On a Mac there is also `council/diagnosis-cuad.command` (double click in the Finder, or `open council/diagnosis-cuad.command`).

- It runs **only on the CUAD dev contracts**. On a Mac below 80 GB these are the 4 contracts up to 14,000 tokens, the same as in the trial of 8/10. The demo set is not needed.
- **Telepathy without realignment with 0 and 10 steps:** 0 is the value to confirm, 10 is for the pre-registered zeroed-thoughts check.
- **Text redone with today's code**, so the comparison with telepathy is clean. The text run of 8/10 came from older code.
- With Qwen3-14B on a 64 GB M1 Max Mac it takes **about an hour and a quarter**.
- The results go to `council/results-trial/diagnosis-cuad/`, and at the end the script prepares the zip `council/results-trial/diagnosis-cuad.zip`.
- **The zip contains only CUAD contracts, which are public:** nothing from the demo set.

## With Claude Code

If you ask Claude Code for the trial, these are the rules for it:

- **Always in a fresh clone**, made just for the trial, even if the repo is already on the computer: never in a folder where other Claude Code sessions or other people work. If someone switches branch in that folder while the trial runs, the trial stops halfway, for example with `No module named review.run`.

  ```bash
  FOLDER=~/council-trial-$(date +%Y%m%d-%H%M)
  git clone https://github.com/AIVolve-Team/the-silent-council.git "$FOLDER"
  ```

  The model is not downloaded again, because it sits in the Hugging Face cache outside the clone, and the script takes the demo set again by itself from the private repo. If instead the set was handed to you, copy it into `council/data/demo-set/` of the fresh clone.
- **Nothing is changed.** No modified files, no packages installed by hand, no different model: `trial.sh` does everything.
- **The script downloads the model:** Qwen3-14B from Hugging Face, at a pinned revision. A Qwen already installed with Ollama or LM Studio cannot be used: the council passes the model's internal memory (the KV cache) from one agent to the next, and those programs do not expose it.
- **The trial starts outside Claude Code**, in a Terminal window of its own:

  ```bash
  open council/trial.command
  ```

  For the [diagnosis trial](#the-diagnosis-trial) the command is `open council/diagnosis.command`, for the [check on CUAD](#the-check-on-cuad) `open council/diagnosis-cuad.command`.

  The run takes hours and uses a lot of memory: a command launched inside Claude Code can be stopped when memory fills up. The first time macOS may ask permission for the Terminal to open the folder: accept it.
- **To follow it**, just read `council/results-trial/trial.log` (for the diagnosis `council/results-trial/diagnosis/trial.log`, for the check on CUAD `council/results-trial/diagnosis-cuad/trial.log`), which grows as the trial goes on.
  - It has finished when the line starting with `Done.` appears at the bottom of the log.
  - It has stopped if `pgrep -f council/trial.sh` finds nothing any more and that line is not there.
- **At the end** the log has the summary of each run: explain it in plain words, comparing telepathy and text (F1, tokens, seconds). The verdict pages are in `council/results-trial/pages/`.
  In the diagnosis, instead, compare the three runs (0, 10 and 40 steps) and remind them to send the zip privately.
  In the check on CUAD, compare telepathy with 0 steps against text, and telepathy with 0 steps against telepathy with 10.
- **If it stops, no fixes:** report the error message and the last lines of `trial.log`.

## The demo set

The 4 Italian contracts written by the team **are not in the repo** until the delivery. The script looks for them in two places:

1. in the folder `council/data/demo-set/`, if someone on the team handed them to you;
2. in the private repo `AIVolve-Team/consiglio-set-dimostrativo`, which the script downloads by itself with the same access used for the clone, without asking for a password.

In both cases it checks that the fingerprints match `council/data/demo-set.sha256`. Without the demo set the run uses only the CUAD contracts, and the pages are of those.

By the pre-registered rules, whoever wrote or reviewed the expected answers of the demo set does not do the eval's manual check.

## If something goes wrong

- **The Mac slows down a lot or swaps:** close heavy applications (virtual machines, browsers with many tabs) and run it again. Or try `./council/trial.sh --quick` first.
- **You want another model:** `MODEL=Qwen/Qwen3-8B./council/trial.sh`.
- **Everything that happened** is in `council/results-trial/trial.log`: if there are problems, just send that file.
