#!/usr/bin/env bash
# Trial of the Silent Council with one command: prepares everything, runs the council and opens the
# verdict pages. Guide: council/PROVA.md.
#
#   ./council/trial.sh                            full run: demo set (if present) and CUAD dev,
#                                                 in telepathy and in text
#   ./council/trial.sh --quick                    telepathy only, demo set only (or 2 CUAD contracts)
#   ./council/trial.sh --diagnosis                where telepathy breaks: telepathy only on the demo set,
#                                                 without realignment, with 0, 10 and 40 latent steps;
#                                                 the results go to council/results-trial/diagnosis
#   ./council/trial.sh --diagnosis-cuad           the same check on CUAD dev: telepathy without
#                                                 realignment with 0 and 10 steps, and text, with today's code;
#                                                 the results go to council/results-trial/diagnosis-cuad
#   MODEL=Qwen/Qwen3-8B ./council/trial.sh        picks the model instead of letting the script decide
#   SYSTEM_TORCH=1 ./council/trial.sh             on the MI300X, in the G1 container: uses the image's ROCm torch
#   NO_REALIGN=1 ./council/trial.sh               the telepathy runs without W_a, as decided with the diagnosis
#
# Works on macOS (Apple Silicon) and on Linux with an NVIDIA GPU; on Windows it must be launched inside WSL2.
# Running it again is safe: what is already downloaded is not downloaded again.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
COUNCIL="$ROOT/council"
VENV="$COUNCIL/.venv"
QUICK=0
DIAGNOSIS=0
DIAGNOSIS_CUAD=0
for argument in "$@"; do
  case "$argument" in
    --quick) QUICK=1 ;;
    --diagnosis) DIAGNOSIS=1 ;;
    --diagnosis-cuad) DIAGNOSIS=1; DIAGNOSIS_CUAD=1 ;;
    -h | --help) sed -n '2,19p' "$0"; exit 0 ;;
    *) echo "Unknown option: $argument (see --help)"; exit 2 ;;
  esac
done
OUTPUT="$COUNCIL/results-trial"
DIAGNOSIS_NAME="diagnosis"
[ "$DIAGNOSIS_CUAD" = 1 ] && DIAGNOSIS_NAME="diagnosis-cuad"
[ "$DIAGNOSIS" = 1 ] && OUTPUT="$OUTPUT/$DIAGNOSIS_NAME"
mkdir -p "$OUTPUT"
exec > >(tee -a "$OUTPUT/trial.log") 2>&1

step() { printf '\n== %s\n' "$*"; }
fail() { printf '\n!! %s\n' "$*"; exit 1; }

step "1/8 The computer"
SYSTEM="$(uname -s)"
GPU_GB=0
if [ "$SYSTEM" = "Darwin" ]; then
  [ "$(uname -m)" = "arm64" ] || fail "A Mac with an Apple chip (M1 or later) is needed."
  MEMORY_GB=$(($(sysctl -n hw.memsize) / 1073741824))
  CHIP="$(sysctl -n machdep.cpu.brand_string)"
  DEVICE="mps"
  GPU_GB=$MEMORY_GB  # on the Mac the memory is shared with the GPU
elif [ "$SYSTEM" = "Linux" ]; then
  MEMORY_GB=$(($(awk '/MemTotal/ {print $2}' /proc/meminfo) / 1048576))
  CHIP="$(uname -m)"
  if command -v nvidia-smi >/dev/null 2>&1; then
    DEVICE="cuda"
    GPU_GB=$(($(nvidia-smi --query-gpu=memory.total --format=csv,noheader,nounits | head -1) / 1024))
  elif command -v rocm-smi >/dev/null 2>&1 || [ -e /dev/kfd ]; then
    DEVICE="rocm"
    GPU_GB=192
  else
    DEVICE="cpu"
    GPU_GB=$MEMORY_GB
  fi
else
  fail "Unsupported system: $SYSTEM. On Windows launch the script inside WSL2 (Ubuntu)."
fi
echo "System $SYSTEM ($CHIP), memory $MEMORY_GB GB, compute on $DEVICE ($GPU_GB GB available for the model)."
# The run lasts hours: while the script is alive the Mac does not go to sleep on its own (the screen can still turn off).
if [ "$SYSTEM" = "Darwin" ] && command -v caffeinate >/dev/null 2>&1; then caffeinate -i -w $$ & fi

# The largest model that fits: the 14B is the council's; the others are only for trying things out.
if [ -z "${MODEL:-}" ]; then
  if [ "$GPU_GB" -ge 48 ]; then MODEL="Qwen/Qwen3-14B"
  elif [ "$GPU_GB" -ge 28 ]; then MODEL="Qwen/Qwen3-8B"
  elif [ "$GPU_GB" -ge 14 ]; then MODEL="Qwen/Qwen3-4B"
  else MODEL="Qwen/Qwen3-1.7B"; fi
fi
# The relay keeps in memory up to three copies of the contract's KV: the chain, the working cache and the copy
# that grows. With Qwen3-0.6B the longest CUAD contract (22,863 tokens) reaches 12 GB; with the 14B it is estimated
# at about 46 GB, too much for a 64 GB Mac. Below 80 GB the contracts over 14,000 tokens are skipped.
MAX_TOKENS=""
CAP=""
if [ "$GPU_GB" -lt 80 ]; then MAX_TOKENS="--max-tokens 14000"; CAP=", contracts up to 14,000 tokens"; fi
echo "Model: $MODEL$CAP."
if [ "$DIAGNOSIS" = 1 ]; then
  case "$MODEL" in
    *Qwen3-0.6B | *Qwen3-1.7B | *Qwen3-4B)
      echo "Warning: with $MODEL the realignment changes almost nothing (input and output embeddings"
      echo "are the same): the diagnosis says something only with Qwen3-8B or 14B, here it shows that everything works." ;;
  esac
fi
[ "$DEVICE" = "cpu" ] && echo "Warning: without a GPU the run is very slow (even hours per contract)."

step "2/8 Python and libraries (a few minutes the first time)"
LIBRARIES=("transformers==4.57.6" "safetensors==0.8.0" "huggingface-hub==0.36.2" "lm-format-enforcer==0.11.3" \
  "cryptography==50.0.2" "tokenizers==0.22.2" "pytest==9.1.1" -e "$ROOT/engine")
PY="$VENV/bin/python"
if [ "${SYSTEM_TORCH:-0}" = 1 ]; then
  # On the MI300X, inside G1's engine container (vllm/vllm-openai-rocm, g1/README.md step 3): torch stays
  # the image's ROCm one, the same that G1 checks with fp32 against bf16; the rest goes in the venv.
  [ -x "$PY" ] || python3 -m venv --system-site-packages "$VENV" || fail "The venv cannot be created."
  "$PY" -m pip install -q "${LIBRARIES[@]}" || fail "The libraries cannot be installed."
else
  if ! command -v uv >/dev/null 2>&1; then
    echo "Installing uv, the Python manager, in the user's folder (no sudo)."
    curl -LsSf https://astral.sh/uv/install.sh | sh
    export PATH="$HOME/.local/bin:$PATH"
  fi
  [ -x "$PY" ] || uv venv -q -p 3.12 "$VENV"
  if [ "$DEVICE" = "rocm" ]; then
    [ -n "${TORCH_INDEX_URL:-}" ] || fail "On an AMD GPU: SYSTEM_TORCH=1 in the G1 container, or TORCH_INDEX_URL=https://download.pytorch.org/whl/rocm... ./council/trial.sh"
    uv pip install -q -p "$PY" --index-url "$TORCH_INDEX_URL" "torch==2.14.1"
  fi
  uv pip install -q -p "$PY" "torch==2.14.1" "${LIBRARIES[@]}"
fi
"$PY" -c "import torch, transformers; print('torch', torch.__version__, '| transformers', transformers.__version__, '| GPU:', 'mps' if torch.backends.mps.is_available() else ('cuda' if torch.cuda.is_available() else 'none'))"
# Qwen3 is trained in bf16: in float16 Qwen models can overflow and write meaningless tokens,
# without errors. float16 is kept only for the GPUs that cannot do bf16, and that is found out by trying it.
case "$DEVICE" in rocm) TORCH_DEVICE="cuda" ;; *) TORCH_DEVICE="$DEVICE" ;; esac
DTYPE="bfloat16"
if ! "$PY" -c "import sys, torch; a = torch.ones(8, 8, dtype=torch.bfloat16, device=sys.argv[1]); (a @ a).sum().item()" \
  "$TORCH_DEVICE" >/dev/null 2>&1; then
  DTYPE="float16"
fi
echo "Model weights in $DTYPE."

step "3/8 Fast tests, without a model"
(cd "$ROOT/engine" && "$PY" -m pytest -q -p no:cacheprovider -m "not model")
(cd "$COUNCIL/data" && "$PY" -m pytest -q -p no:cacheprovider)
(cd "$COUNCIL/review" && "$PY" -m pytest -q -p no:cacheprovider -m "not model")

step "4/8 Benchmark data (CUAD, ContractNLI, CLAUDETTE), with the fingerprints checked"
(cd "$COUNCIL/data" && "$PY" prepare.py)

step "5/8 Demo set"
DEMO="$COUNCIL/data/demo-set"
if ! ls "$DEMO"/*.txt >/dev/null 2>&1; then
  # The team's private repo next to this one, with the same access used for the clone (HTTPS or SSH): without
  # asking for a password; if there is no access, the run goes on with CUAD.
  ORIGIN="$(git -C "$ROOT" remote get-url origin 2>/dev/null || true)"
  DEMO_REPO="${DEMO_SET_REPO:-${ORIGIN%/*}/consiglio-set-dimostrativo.git}"
  if GIT_TERMINAL_PROMPT=0 GIT_SSH_COMMAND="ssh -o BatchMode=yes" git clone -q "$DEMO_REPO" "$DEMO" 2>/dev/null; then
    echo "Demo set taken from the private repo $DEMO_REPO."
  else
    echo "The private repo $DEMO_REPO cannot be reached."
  fi
fi
WITH_DEMO=0
if ls "$DEMO"/*.txt >/dev/null 2>&1; then
  # The set must be the one reviewed in the fingerprints are in the repo since 6/10.
  (cd "$COUNCIL/data" && "$PY" -c '
import hashlib, sys
rows = [r.split() for r in open("demo-set.sha256") if r.strip()]
different = [f for h, f in rows if hashlib.sha256(open(f, "rb").read()).hexdigest() != h]
sys.exit("The demo set does not match the fingerprints in the repo: " + ", ".join(different) if different else 0)
') && WITH_DEMO=1 && echo "Demo set found and verified: $(ls "$DEMO"/*.txt | wc -l | tr -d ' ') contracts."
else
  echo "Demo set not found: the run uses CUAD only (see PROVA.md to get it)."
fi
if [ "$DIAGNOSIS" = 1 ] && [ "$DIAGNOSIS_CUAD" = 0 ] && [ "$WITH_DEMO" = 0 ]; then
  fail "The diagnosis runs on the verified demo set, which is missing here (see PROVA.md to get it)."
fi

step "6/8 Model $MODEL (the first time it can take long: the 14B weighs about 30 GB)"
REVISION="$(cd "$COUNCIL/review" && "$PY" -c "from review.run import MODELS; print(MODELS['$MODEL'])")"
"$PY" -c "import sys; from huggingface_hub import snapshot_download; snapshot_download(sys.argv[1], revision=sys.argv[2])" "$MODEL" "$REVISION"

step "7/8 The council"
# Every run has its latent steps; ROWS counts the summary rows they will write (one per value of the steps).
runs=()
ROWS=0
add_run() { runs+=("$1"); ROWS=$((ROWS + $2)); }
if [ "$DIAGNOSIS_CUAD" = 1 ]; then
  # The confirmation on CUAD dev before freezing the pre-registration: telepathy without
  # realignment with 0 steps (and 10, for the check of the zeroed thoughts) against text redone with the same
  # code, so the comparison is clean.
  add_run "--benchmark cuad --mode telepathy --no-realign --steps 0 10" 2
  add_run "--benchmark cuad --mode text --steps 10" 1
elif [ "$DIAGNOSIS" = 1 ]; then
  # A single run, so the model is loaded once for the three values of the steps. With 0 steps the rapporteur only
  # receives the memory of what the experts read: if it stays broken, the problem is not the latent steps.
  add_run "--benchmark demo --mode telepathy --no-realign --steps 0 10 40" 3
else
  if [ "$WITH_DEMO" = 1 ]; then
    add_run "--benchmark demo --mode telepathy --steps 10" 1
    [ "$QUICK" = 1 ] || add_run "--benchmark demo --mode text --steps 10" 1
  fi
  if [ "$QUICK" = 1 ]; then
    [ "$WITH_DEMO" = 1 ] || add_run "--benchmark cuad --mode telepathy --limit 2 --steps 10" 1
  else
    add_run "--benchmark cuad --mode telepathy --steps 10" 1
    add_run "--benchmark cuad --mode text --steps 10" 1
  fi
fi
# The diagnosis already turns realignment off by itself; in the other runs NO_REALIGN=1 turns it off.
NO_WA=""
[ "${NO_REALIGN:-0}" = 1 ] && [ "$DIAGNOSIS" = 0 ] && NO_WA=" --no-realign"
for run in "${runs[@]}"; do
  [[ "$run" == *"--mode telepathy"* ]] && run="$run$NO_WA"
  echo "-- $run ($(date +%H:%M))"
  # shellcheck disable=SC2086
  (cd "$COUNCIL/review" && "$PY" -u -m review.run $run --model "$MODEL" \
    --dtype "$DTYPE" $MAX_TOKENS --output "$OUTPUT" 2>&1 | grep --line-buffered -v -E "Warning|warn\(|Loading checkpoint") ||
    echo "!! The run '$run' stopped: the rest goes on (details in $OUTPUT/trial.log)."
done

step "8/8 Verdict pages"
if [ "$DIAGNOSIS" = 1 ]; then
  echo "In the diagnosis the pages are not needed: the numbers of the summary are what counts."
elif [ ! -f "$COUNCIL/review/review/view.py" ]; then
  echo "This version of the repo has no verdict page: for now there are only the .jsonl files."
else
(cd "$COUNCIL/review" && "$PY" - "$OUTPUT" "$DEMO" <<'PAGES'
import json, sys
from pathlib import Path
from review import BENCHMARK
from review.view import page, view

output, demo = Path(sys.argv[1]), Path(sys.argv[2])
folder = output / "pages"
folder.mkdir(exist_ok=True)
for run in sorted(output.glob("*.jsonl")):
    for line in run.open():
        r = json.loads(line)
        contract = demo / f"{r['contract']}.txt"
        title = r["contract"]
        if r["benchmark"] == "demo" and contract.exists():
            lines = [x.strip() for x in contract.read_text().splitlines() if x.strip()]
            # The demo contracts are Italian: their subject line starts with "Oggetto:".
            subject = next((x.split(":", 1)[1].strip() for x in lines if x.lower().startswith("oggetto:")), None)
            title = subject or lines[0]
            title = title[0].upper() + title[1:].lower()
        short = r["contract"][:50].rstrip("-_. ")
        name = f"{r['benchmark']}-{short}-{r['mode']}".replace("/", "_").replace(" ", "_")
        (folder / f"{name}.html").write_text(page(view(r, BENCHMARK[r["benchmark"]], title)))
print(f"Pages in {folder}")
PAGES
)
# The page of an Italian contract of the demo set opens first, if there is one.
FIRST=""
for candidate in "$OUTPUT"/pages/demo-*telepathy.html "$OUTPUT"/pages/*telepathy.html; do
  if [ -f "$candidate" ]; then FIRST="$candidate"; break; fi
done
if [ -n "$FIRST" ]; then
  if command -v open >/dev/null 2>&1; then open "$FIRST"; elif command -v xdg-open >/dev/null 2>&1; then xdg-open "$FIRST"; fi
fi
fi

step "Summary"
grep -h " contracts | " "$OUTPUT/trial.log" | tail -n "$ROWS" || true
if [ "$DIAGNOSIS" = 1 ]; then
  SEND="Compress the folder $OUTPUT and send the zip."
  if command -v zip >/dev/null 2>&1; then
    rm -f "$OUTPUT.zip"
    # Without the full copies of the messages that the engine saves only if the seal breaks: they weigh GBs.
    (cd "$(dirname "$OUTPUT")" && zip -qr "$DIAGNOSIS_NAME.zip" "$DIAGNOSIS_NAME" -x "$DIAGNOSIS_NAME/log/*.safetensors") &&
      SEND="The zip to send is $OUTPUT.zip."
  fi
  if [ "$DIAGNOSIS_CUAD" = 1 ]; then
    RUNS_DONE="telepathy without realignment with 0 and 10 steps, and text"
    PRIVATE="It contains only CUAD contracts, which are public: nothing from the demo set."
  else
    RUNS_DONE="one file per number of latent steps (0, 10, 40)"
    PRIVATE="Send it only privately to whoever asked for it, not on GitHub: it contains sentences of the demo set."
  fi
  cat <<END

Done. Diagnosis results in $OUTPUT:
- *.jsonl          the complete reviews: $RUNS_DONE
- trial.log        everything that happened
$SEND
$PRIVATE
END
  exit 0
fi
cat <<END

Done. Results in $OUTPUT:
- pages/           the verdict pages, one per contract and mode (the first one opened by itself)
- *.jsonl          the complete reviews: notes, verdict, confidences, dissents, tokens and times
- trial.log        everything that happened
To share them with the team just send the results-trial folder (the demo set stays out: it is in the .jsonl files
only as quotes, so it must be shared only within the team).
END
