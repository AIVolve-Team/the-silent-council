"""The other G1 metrics: memory, fingerprint, recomputation of the thoughts and comparison with fp32.

    python -m g1.metrics memory --vllm-weights-gb 71.9 --output results/memory.json   # with vLLM on
    python -m g1.metrics fp32 --problems 5 --output results/fp32.json                 # with vLLM off

If the invoice generator is not there yet, the long text is made of GSM8K problems in a row.
"""

from __future__ import annotations

import argparse
import gc
import json
import shutil
import subprocess
import time
from pathlib import Path

import torch
from engine import Engine, Model, Relay
from engine.check import FingerprintCheck

from .gsm8k import load_problems
from .run import ANALYSTS, SOLVER, run_mode, sdpa_constraint

GB = 1e9


def long_text(tokenizer, tokens: int) -> str:
    """GSM8K problems one after the other, until the text reaches at least `tokens` tokens."""
    problems = load_problems()
    pieces: list[str] = []
    while True:
        pieces.append(problems[len(pieces) % len(problems)].question)
        text = "\n\n".join(pieces)
        if len(tokenizer(text).input_ids) >= tokens:
            return text


def kv_bytes(message) -> int:
    return sum(t.numel() * t.element_size() for kv in (message.kv_read, message.kv_thoughts) for p in kv for t in p)


def rocm_vram() -> dict | None:
    """The card's memory as seen by ROCm, including vLLM running in another process."""
    if shutil.which("rocm-smi") is None:
        return None
    output = subprocess.run(
        ["rocm-smi", "--showmeminfo", "vram", "--json"], capture_output=True, text=True, check=False
    )
    return json.loads(output.stdout) if output.returncode == 0 else {"error": output.stderr.strip()}


def peak_gb(device: str) -> float | None:
    if device == "cuda":
        return torch.cuda.max_memory_reserved() / GB
    if device == "mps":
        return torch.mps.driver_allocated_memory() / GB
    return None


def measure_engine(engine: Engine, *, tokens: int = 4000) -> dict:
    """The relay in telepathy on a long text: peak memory, size of a message, time of the fingerprint and
    recomputation of the thoughts, which with the message's own states must give back the same KV."""
    model = engine.model
    if model.device == "cuda":
        torch.cuda.reset_peak_memory_stats()
    text = long_text(model.tokenizer, tokens)
    relay = Relay(engine, ANALYSTS, SOLVER, latent_steps=10)
    with sdpa_constraint(model.device):
        outcome = relay.run("g1-memory", {a.name: text for a in [*ANALYSTS, SOLVER]}, max_tokens=16)
        first = outcome.messages[0]
        start = time.perf_counter()
        fingerprint = FingerprintCheck()(first, [])
        fingerprint_seconds = time.perf_counter() - start
        recomputed = engine.recompute_thoughts(first, [])
    identical = all(
        torch.equal(a, b)
        for (ka, va), (kb, vb) in zip(first.kv_thoughts, recomputed.kv_thoughts, strict=True)
        for a, b in ((ka, kb), (va, vb))
    )
    return {
        "device": model.device,
        "dtype": str(model.dtype).removeprefix("torch."),
        "tokens_read_first_agent": first.n_read,
        "message_kv_gb": kv_bytes(first) / GB,
        "fingerprint_seconds": fingerprint_seconds,
        "fingerprint_ok": fingerprint.passed,
        "recompute_identical": identical,
        "relay_seconds": outcome.seconds,
        "stopped": None if outcome.stopped is None else f"{outcome.stopped.check}: {outcome.stopped.reason}",
        "engine_peak_gb": peak_gb(model.device),
        "engine_weights_gb": sum(p.numel() * p.element_size() for p in model.net.parameters()) / GB,
        "rocm_vram": rocm_vram(),
    }


def compare_fp32(name: str, revision: str, problems: int, folder: Path, max_answer_tokens: int) -> dict:
    """The same problems in telepathy with the model in fp32 and in bf16: the answers must match."""
    rows = {}
    for dtype in (torch.float32, torch.bfloat16):
        label = str(dtype).removeprefix("torch.")
        engine = Engine(Model(name, revision, dtype=dtype), max_text_tokens=1024)
        rows[label] = run_mode(
            engine,
            "telepathy",
            load_problems(problems),
            folder / f"fp32-{label}.jsonl",
            max_answer_tokens=max_answer_tokens,
        )
        del engine
        gc.collect()
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
    pairs = list(zip(rows["float32"], rows["bfloat16"], strict=True))
    return {
        "problems": problems,
        "same_answers": sum(a["answer"] == b["answer"] for a, b in pairs),
        "same_texts": sum(a["final_text"] == b["final_text"] for a, b in pairs),
        "correct_fp32": sum(a["correct"] for a, _ in pairs),
        "correct_bf16": sum(b["correct"] for _, b in pairs),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("metric", choices=["memory", "fp32"])
    parser.add_argument("--model", default="Qwen/Qwen3-14B")
    parser.add_argument("--revision", default="40c069824f4251a91eefaf281ebe4c544efd3e18")
    parser.add_argument("--tokens", type=int, default=4000, help="length of the text read by each agent")
    parser.add_argument("--vllm-weights-gb", type=float, default=None, help="from the vLLM log: 'Model loading took …'")
    parser.add_argument("--problems", type=int, default=5)
    parser.add_argument("--max-answer-tokens", type=int, default=512)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)

    if args.metric == "fp32":
        result = compare_fp32(args.model, args.revision, args.problems, args.output.parent, args.max_answer_tokens)
    else:
        try:
            result = measure_engine(Engine(Model(args.model, args.revision)), tokens=args.tokens)
            result["ok"] = result["stopped"] is None and result["fingerprint_ok"]
        except torch.OutOfMemoryError as error:
            result = {"ok": False, "error": f"out of memory: {error}"}
        result["vllm_weights_gb"] = args.vllm_weights_gb
        if args.vllm_weights_gb is not None and "engine_weights_gb" in result:
            result["two_models_weights_gb"] = result["engine_weights_gb"] + args.vllm_weights_gb
    args.output.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n")
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
