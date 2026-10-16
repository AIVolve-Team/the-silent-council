# g1 — the first gate: the engine on the MI300X

The rules were pre-registered by the team before the run; here are the script and the instructions for 12 October.
It uses the telepathic engine in `../engine`.

## What G1 decides

- **G1 passes if:**
  - the engine (Qwen3-14B on Transformers) and the main agent (Qwen3.6-35B-A3B on vLLM) run **on the same MI300X without memory errors**;
  - in telepathy the **tokens generated** are **at least 50% fewer** than in text.
- **Accuracy** of telepathy with 10 latent steps, against text, in three zones:
  - **within 3 points:** *"demonstrated"*;
  - **from 3 to 10 points below:** we go on, and G2 and the council's eval decide;
  - **more than 10 points below:** we stop and fall back to the text floor.

## Choices fixed here, before measuring

The pre-registration did not fix them; they hold from this commit, and any change after the measurement is a deviation to write down in the report.

- **Problems:** the first 100 of the official GSM8K test ([openai/grade-school-math](https://github.com/openai/grade-school-math) at commit `3101c7d`, MIT license), copied to `data/gsm8k-test-100.jsonl`. The script checks the file's fingerprint (`1d266ea0…ff90`) on every start.
- **Agents:** three analysts (`strategist`, `reviewer`, `polisher`) and a `solver` that writes the answer in `\boxed{}`, like the LatentMAS chain but with names and prompts of our own. The prompts are in English, like the problems.
- **Three runs:** text, telepathy with 10 latent steps (the authors' value on GSM8K), telepathy with no thoughts (`m=0`). The third is the `m=0` versus `m>0` comparison promised in the pre-registration.
- **Lengths:** in text mode each analyst writes at most **1,024 tokens**, like the Help Desk; the final answer at most 1,024 tokens in every mode. The report counts the truncated messages.
- **Decoding** deterministic (greedy) and thinking off, as in the engine; a single run.
- **Model's answer:** the last number of the last `\boxed{}`; with no box, the last number in the text. Compared as a number (`18` = `18.0`).
- **Model:** `Qwen/Qwen3-14B` at revision `40c069824f4251a91eefaf281ebe4c544efd3e18`, the same as the council's; in bf16 on the MI300X.
- **SDPA:** on the MI300X only the flash and efficient kernels; the fallback to the math backend is forbidden, so a kernel problem gives an error instead of wrong numbers.
- **Order:** one problem at a time in the three modes. If time runs out, the report compares the finished problems and says "partial".

| File | What it does |
|---|---|
| `g1/run.py` | the three runs: every finished problem is written right away, and relaunching restarts from where it stopped |
| `g1/agent.py` | check of the main agent's vLLM endpoint: a call to `examine_invoice`, no thinking |
| `g1/metrics.py` | memory with the two models together, fingerprint, recomputation of the thoughts, fp32 versus bf16 comparison |
| `g1/summary.py` | the verdict and the report |
| `g1/gsm8k.py` | the 100 problems and the extraction of the answers |
| `tests/` | the tests, with and without a model |

## On the Mac

```bash
cd g1
uv venv -p 3.12 .venv && uv pip install -p .venv/bin/python -r requirements.txt
.venv/bin/python -m pytest           # the tests with Qwen3-0.6B take about a minute
.venv/bin/ruff check . && .venv/bin/ruff format --check .

# the full trial, with a small model and a few problems
M="--model Qwen/Qwen3-0.6B --revision c1899de289a04d12100db370d81485cdf75e47ca"
.venv/bin/python -m g1.run $M --problems 3 --output /tmp/g1
.venv/bin/python -m g1.metrics memory $M --vllm-weights-gb 71.9 --output /tmp/g1/memory.json
.venv/bin/python -m g1.summary /tmp/g1
```

The model tests read `G1_MODEL` and `G1_REVISION` to use a model other than Qwen3-0.6B.

Trial of 8 October 2026 on a 16 GB Mac M4 (MPS, fp32), with Qwen3-0.6B, 3 problems and the real limits (1,024 tokens):

| Run | Accuracy | Tokens generated | Seconds per problem |
|---|---|---|---|
| text | 2 of 3 | 2,572 | 38.4 |
| telepathy (10 steps) | 2 of 3 | 372 | 6.9 |
| no thoughts | 2 of 3 | 456 | 7.0 |

Memory measurement with a 1,000-token text: a 0.25 GB message, fingerprint in 0.26 s, identical recomputation of the thoughts, a 6.6 GB peak.
With 4,000 tokens the Mac swaps: the relay reaches about 16,000 positions, about 3.7 GB per copy in fp32, and the engine holds about three of them.
On the MI300X, with Qwen3-14B in bf16, a 4,000-token message weighs about 0.66 GB.
The verdict of the trial does not count: it only shows that everything runs.

## On 12 October on the MI300X

The participants' card arrives at the kickoff (17:00) and **G1 is due at 22:00**. We do not know yet what form it comes in:
- **a machine with Docker**, like the AMD Developer Cloud droplet of the spike: follow the steps below;
- **a notebook-like environment** with PyTorch ROCm already installed, like in ACT II: skip Docker, create the venv of step 3 and carry on the same way. vLLM must still run on the same card for the memory measurement.

Times *(estimate)* to correct here after the real run:

| # | Step | Time |
|---|---|---|
| 1 | Check the card, start the downloads | 5 min, then the downloads in background |
| 2 | Copy `g1/` and `engine/` from the Mac | 2 min |
| 3 | Container and venv of the engine | 10 min |
| 4 | fp32 versus bf16 comparison, with vLLM off | 10-15 min |
| 5 | Start vLLM with Qwen3.6 | 5-10 min |
| 6 | Memory measurement with the two models together | 5 min |
| 7 | The three runs on the 100 problems | to be measured: step 7 tells after 5 problems |
| 8 | Write the report | 5 min |

### 1. The card and the downloads

```bash
rocm-smi --showproductname --showmeminfo vram --showdriverversion   # 1x MI300X, about 192 GB
df -h                                    # about 130 GB free are needed: 72 GB of Qwen3.6, 30 of Qwen3-14B, 12 of image
export HF_HOME=/root/hf                  # on the big disk; in ~/.bashrc if other SSH sessions need it
command -v hf || pip install -U "huggingface_hub[cli]"   # the hf command on the host
nohup docker pull vllm/vllm-openai-rocm:v0.30.0 > pull.log 2>&1 &
nohup hf download Qwen/Qwen3-14B --revision 40c069824f4251a91eefaf281ebe4c544efd3e18 > dl-14b.log 2>&1 &
nohup hf download Qwen/Qwen3.6-35B-A3B --revision 995ad96eacd98c81ed38be0c5b274b04031597b0 > dl-36.log 2>&1 &
```

If the machine is a DigitalOcean droplet, **you pay for it even when it is off**: at the end it must be destroyed.
The models go on the boot disk, not on the scratch disk: the snapshot of the final step only covers the boot disk.

### 2. The code

No GitHub token on the machine (as in the spike): the code is copied from the Mac.

```bash
# on the Mac, from the root of the repo
rsync -a --exclude .venv --exclude results g1 engine root@<IP>:~/hackathon/
```

### 3. Container and venv of the engine

The engine uses the image's ROCm torch and its own `transformers` 4.57.6, in a venv separate from vLLM's.

```bash
docker run -d --name engine --network=host --ipc=host --shm-size 16G \
  --device=/dev/kfd --device=/dev/dri --group-add video --cap-add=SYS_PTRACE --security-opt seccomp=unconfined \
  -v "$HF_HOME":/root/hf -e HF_HOME=/root/hf -v ~/hackathon:/work -w /work/g1 \
  --entrypoint sleep vllm/vllm-openai-rocm:v0.30.0 infinity
docker exec -it engine bash
# inside the container
python -m venv --system-site-packages /root/venv && . /root/venv/bin/activate
pip install -r requirements-rocm.txt
python -c "import torch, transformers; print(torch.__version__, torch.version.hip, torch.cuda.get_device_name(0), transformers.__version__)"
python -m pytest -m "not model"        # the tests without a model
```

If `torch.cuda.is_available()` is false or the card's name is not MI300X, stop here and note the error.

### 4. fp32 versus bf16 (vLLM off)

On ROCm the SDPA masks have had bugs, so we compare against an fp32 reference.

```bash
python -m g1.metrics fp32 --problems 5 --output results/fp32.json
```

The answers are expected to match; the texts may diverge slightly. If the answers diverge on more than 1 problem out of 5, note it before going on.

### 5. vLLM with Qwen3.6

vLLM usually takes 90% of the card's memory: here it is limited to half, so the engine fits. Start it **before** the engine.

```bash
docker run -d --name vllm --network=host --ipc=host --shm-size 16G \
  --device=/dev/kfd --device=/dev/dri --group-add video --security-opt seccomp=unconfined \
  -v "$HF_HOME":/root/hf -e HF_HOME=/root/hf --entrypoint vllm vllm/vllm-openai-rocm:v0.30.0 \
  serve Qwen/Qwen3.6-35B-A3B --revision 995ad96eacd98c81ed38be0c5b274b04031597b0 --port 8000 \
  --api-key "$VLLM_API_KEY" --gpu-memory-utilization 0.5 --max-model-len 32768 --max-num-seqs 256 \
  --enable-auto-tool-choice --tool-call-parser qwen3_coder --reasoning-parser qwen3 \
  --default-chat-template-kwargs '{"enable_thinking": false}' \
  --override-generation-config '{"temperature": 0.7, "top_p": 0.8, "top_k": 20, "min_p": 0.0, "presence_penalty": 1.5, "repetition_penalty": 1.0}'
docker logs -f vllm 2>&1 | grep -m2 -E "Model loading took|startup complete"   # note the GB of the first one
python -m g1.agent --url http://127.0.0.1:8000 --key "$VLLM_API_KEY"     # must end with ✓
```

`--max-num-seqs 256` has been needed since the run of 12 October. Qwen3.6 is a hybrid model and with half a card it has 785 Mamba cache blocks, fewer than the 1,024 that vLLM prepares by default. Without the flag the start stops with `max_num_seqs (1024) exceeds available Mamba cache blocks`.

The main agent's parameters are those of the Evolus building block (not `hermes`).
Evolus does not pass request parameters, so "thinking" and sampling are fixed here, on the server side:

- **No thinking** (`enable_thinking: false`): the agent chooses the path and writes a short notice, the reasoning on the invoice is done by the engine; that way it is faster and more predictable, and we do not know Evolus's timeout yet.
- **Sampling** from the Qwen3.6 model card for the non-thinking mode: temperature 0.7, top_p 0.80, top_k 20, min_p 0, presence_penalty 1.5.
- If `vllm serve --help` of v0.30.0 lacks one of the two flags, look for the new name in the help: the `g1.agent` check says whether thinking is really off.

`g1.agent` sends the request the way Evolus would, with the `examine_invoice` tool and no parameters, and checks that a real tool call comes back (not XML in the text, so the right parser), with JSON arguments and no thinking.

### 6. Memory with the two models together

```bash
python -m g1.metrics memory --vllm-weights-gb <GB from the vLLM log> --output results/memory.json
```

It measures the relay in telepathy on a 4,000-token text (instead of the longest invoice, if the invoice generator is not there yet): the engine's peak, the card's memory as seen by `rocm-smi` with vLLM on, the time of the fingerprint (if it weighs, BLAKE3) and the recomputation of the thoughts in bf16.

### 7. The three runs

```bash
nohup python -m g1.run --output results > results/run.log 2>&1 &
tail -f results/run.log
```

After 5 problems `python -m g1.summary results` gives the seconds per problem of each mode: multiplied by 100 they tell whether it finishes by 22:00.
If the run is interrupted, relaunch the same command and it restarts from the first missing problem.

### 8. The report

```bash
python -m g1.summary results > results/report.md
```

Copy `results/` to the Mac (`rsync -a root@<IP>:~/hackathon/g1/results/ g1/results-mi300x/`) and publish the report, by 22:00.

### After G1, if the machine is a droplet

With `site/mi300x/mi300x.sh` of the judges' site, which talks to the AMD Developer Cloud API (it is DigitalOcean's):

- **Snapshot** of the boot disk, with the models inside: `mi300x.sh snapshot`. It takes about 1-3 minutes per GB used, and meanwhile you pay for the machine: better to launch it at the end of the day. First prepare the services that must restart on their own (`site/mi300x/README.md`, "The golden machine").
- **Destroy the machine:** `mi300x.sh destroy`, which checks again and gives an error if one is still on.
- **The boot time from a snapshot**, the next morning: `mi300x.sh create wait`, which prints the seconds until the machine is active and, with `MI300X_HEALTH`, until the engine is ready. It goes in the report.

## The recorded results

`results-mi300x/` holds the run of 12 October, renamed to English after the fact: file names (`text.jsonl`, `telepathy.jsonl`, `no_thoughts.jsonl`, `environment.json`, `memory.json`, `report.md`, `run.log`, `vllm-first-start.log`) and, in the `.json`/`.jsonl` files, the keys and the mode values, so that `g1.summary` still reads them. The values are untouched, including what the model wrote (`final_text`). `report.md` was regenerated from the migrated files with `python -m g1.summary results-mi300x`: same numbers as the report published on 12 October, now in English.

The `.log` files stay as the program printed them on the day, so they are in Italian (for example `testo gsm8k-test-0000: giusta (959 token, 32.196 s)`, today `text gsm8k-test-0000: correct (959 tokens, 32.196 s)`).
