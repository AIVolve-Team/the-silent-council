# G1 on the MI300X: what we demonstrated (12 October 2026)

**In short: G1 passes, in the best zone, "demonstrated".**
Our telepathic engine runs on a single AMD MI300X together with the main agent. It generates **81% fewer tokens** than text, answers in about **a quarter of the time** and gets only one more problem out of 100 wrong.

Procedure: [README.md](README.md). Raw data: [`results-mi300x/`](results-mi300x/).

## What G1 is

G1 is the project's **first gate**: the first trial on the real GPU. It answers a single question: *does telepathy between agents really work on the MI300X, or only on the Mac?*

Had G1 failed, both the Help Desk and the council would have fallen, and we would have fallen back to the text floor.

## What we compared

Four agents, all Qwen3-14B, solve math word problems. They are the first 100 of the official test of **GSM8K**, a widely used public benchmark. The agents work in a row:
- three **analysts**: one plans, one reviews and one polishes;
- a **solver**, which writes the final answer.

Each problem is solved in three modes:

| Mode | How the analysts pass on their work |
|---|---|
| **Text** | Each writes its analysis, at most 1,024 tokens, and the next one reads it. It is the classic mode. |
| **Telepathy, 10 steps** | Each passes its **internal working memory** (the KV cache) on to the next, without writing anything. Before passing it on it "thinks in silence" for 10 steps. 10 is the value the LatentMAS authors used on GSM8K. |
| **No thoughts, 0 steps** | Like telepathy, but without the thinking steps: only the memory of the reading is passed on. It is the control group that tells whether the steps help. |

In all three modes only the solver writes. The surrounding rules were fixed before measuring, in the README:
- deterministic decoding, that is the same input gives the same output;
- thinking off;
- a single run.

## The metrics and the thresholds

They were fixed **before** measuring, in the team's pre-registration and in the README.

| Metric | What it measures | Threshold to pass |
|---|---|---|
| **Memory** | The engine (Qwen3-14B) and the main agent (Qwen3.6-35B-A3B on vLLM) run together on the same card without memory errors. | No errors |
| **Tokens generated** | How many tokens the agents write in telepathy compared with text. It is the cost: every generated token is GPU time. | At least **50% fewer** |
| **Accuracy** | Percentage of problems with the correct answer. Telepathy (10 steps) is compared with text. | Three zones, below |

The three accuracy zones, telepathy minus text:
- **within 3 points:** *demonstrated*;
- **from 3 to 10 points below:** we go on, and G2 and the council's eval decide;
- **more than 10 points below:** we stop and fall back to the text floor.

## The results

Full run on the 100 problems, from 16:34 to 17:52 (Italian time).

| Mode | Correct answers | Tokens generated | Seconds per problem |
|---|---|---|---|
| Text | **97** of 100 | 124,790 | 34.3 |
| Telepathy, 10 steps | **96** of 100 | 23,697 (**−81%**) | 7.6 |
| No thoughts, 0 steps | **98** of 100 | 16,135 (−87%) | 4.7 |

| Metric | Result | Outcome |
|---|---|---|
| Memory | Two models together: 138 GB used out of 206. Weights 99.9 GB, engine peak 37.9 GB. | ✓ |
| Tokens generated | −81% compared with text | ✓ (threshold −50%) |
| Accuracy | 96% against 97%: **−1.0 points** | ✓ zone **demonstrated** |

**G1 passes.**

### What it means, in plain words

1. **It works on the real hardware.** It is no longer a Mac experiment: it runs on the MI300X with the real model, in bf16, with ROCm's fast attention kernels.
2. **It costs much less.** To reach the same answer the agents write a fifth of the tokens and take less than a quarter of the time: 7.6 seconds against 34.3 per problem.
3. **It does not lose accuracy.** One point out of 100 is within the "demonstrated" threshold. There are few mistakes in all three modes:
   - text: problems 37, 58 and 62;
   - telepathy: problems 12, 20, 21 and 62;
   - no thoughts: problems 37 and 62.
4. **The "thoughts" are not the strong point.** Without the thinking steps telepathy is even a little more accurate (98 against 96) and faster (4.7 seconds against 7.6). The value lies in **passing on the working memory**, not in the extra thinking. It is the same pattern seen on the Mac with the council. How many steps to use for the council is decided by its calibration.
5. **The MI300X is really needed.** The two models together weigh 99.9 GB: on an 80 GB card, like an H100, they would not fit.

### A limit to state honestly

GSM8K is easy math for a 14B model: the solver could reach the correct answer almost on its own. G1 shows **cost, speed and memory** well. It says less about whether the memory passed between agents improves reasoning. For that, the council's eval on contracts counts.

## The other checks

- **fp32 versus bf16**, 5 problems. It is a safety check: on ROCm the attention kernels with masks have had bugs that gave wrong numbers without errors. The answers match 5 out of 5, all correct. The texts diverge a little, as expected with bf16's rounded numbers.
- **4,103-token latent message:**
  - it weighs 0.67 GB;
  - its check fingerprint is computed in 0.45 seconds;
  - the recomputation of the thoughts in bf16 is identical.
- **Main agent** (Qwen3.6 on vLLM, for Evolus): it answers in 0.8 seconds with a real call to the `examine_invoice` tool and no thinking. On the day the tool was still called by its Italian name, `esamina_fattura`.

## What changed compared with the procedure

1. **The fp32 reference uses PyTorch's "math" backend.**
   - **The problem:** the first attempt stopped with `No available kernel`. In fp32 none of the fast kernels accepts the format Qwen3 uses for memory (8 heads instead of 40), and the code forbade the slow and safe backend.
   - **The fix:** now **only** the fp32 reference uses that backend (`g1/run.py`, `sdpa_constraint`, with 3 tests in `tests/test_sdpa_constraint.py`). The real bf16 run keeps the ban. That way the reference is also independent of the kernels it checks.
2. **`--max-num-seqs 256` for vLLM.** Without the flag Qwen3.6 does not start with half a card. The memory used does not change. It is already in the README command.
3. **The card's name comes out empty** (`"gpu": ""` in `environment.json`). The cloud's virtualized MI300X does not expose it. Architecture gfx942, 304 compute units and 192 GB confirm it is an MI300X.
4. **Machine setup:**
   - `hf` has to be installed in a separate venv, with `python3.12-venv`;
   - the copied repo has to be handed over to root, otherwise git rejects it;
   - the firewall limits SSH connections in quick succession, so a shared connection is better.

## Real times

| Step | Time |
|---|---|
| Download of models and image (about 110 GB) | about 2 minutes |
| Container and venv | about 3 minutes |
| fp32 versus bf16 | about 3 minutes |
| vLLM start | about 4 minutes |
| Memory measurement | about 1 minute |
| Three runs on 100 problems | 78 minutes |

Machine: AMD Developer Cloud, 1× MI300X with 192 GB, ROCm 7.2. Software:
- image `vllm/vllm-openai-rocm:v0.30.0`;
- torch `2.12.0+git6bbd260` (HIP 7.2) and transformers 4.57.6;
- Qwen3-14B at revision `40c069824f4251a91eefaf281ebe4c544efd3e18`.
