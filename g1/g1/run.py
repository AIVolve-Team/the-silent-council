"""The three G1 runs on GSM8K: text, telepathy with 10 latent steps, telepathy with no thoughts.

    python -m g1.run --output results/

Every finished problem is written right away to `<output>/<mode>.jsonl`: if the run is interrupted, relaunching the
same command restarts from the first missing problem.
"""

from __future__ import annotations

import argparse
import contextlib
import json
import platform
from datetime import UTC, datetime
from pathlib import Path

import torch
import transformers
from engine import Agent, Engine, Model, Relay
from engine.message import TELEPATHY, TEXT

from .gsm8k import Problem, extract_answer, is_correct, load_problems

MODES = {"text": (TEXT, 0), "telepathy": (TELEPATHY, 10), "no_thoughts": (TELEPATHY, 0)}

# Three agents that reason and one that answers, like the LatentMAS chain, with names and prompts of our own.
STRATEGIST = Agent(
    "strategist",
    "You are the first of three analysts working together on a math word problem. Read the problem carefully and "
    "work out a clear step-by-step plan to solve it: which quantities matter and which operations to do, in order. "
    "Do not give the final answer.",
)
REVIEWER = Agent(
    "reviewer",
    "You are the second of three analysts working together on a math word problem. You know the first analyst's "
    "plan. Check it step by step: find mistakes in reasoning or arithmetic and anything missing, and say how to fix "
    "them.",
)
POLISHER = Agent(
    "polisher",
    "You are the third of three analysts working together on a math word problem. You know the plan and the review "
    "of your colleagues. Combine them into a corrected, complete solution path, with the calculations.",
)
SOLVER = Agent(
    "solver",
    "You solve math word problems using what your colleagues worked out. Reason briefly and compute carefully. "
    "End with the final answer as a number in the form \\boxed{answer}.",
)
ANALYSTS = [STRATEGIST, REVIEWER, POLISHER]


def sdpa_constraint(device: str, dtype: torch.dtype = torch.bfloat16):
    """On the MI300X no fallback to the SDPA math backend: if the fast kernels are not enough, better an error.

    The exception is the fp32 reference of the comparison: without a mask Transformers passes SDPA the 8 KV heads of
    Qwen3 with `enable_gqa`, which no fast kernel accepts in fp32 (flash wants bf16, efficient wants the heads
    expanded). The reference goes on math, so it is also independent of the kernels it checks.
    """
    if device != "cuda":
        return contextlib.nullcontext()
    from torch.nn.attention import SDPBackend, sdpa_kernel

    if dtype == torch.float32:
        return sdpa_kernel([SDPBackend.MATH])
    return sdpa_kernel([SDPBackend.FLASH_ATTENTION, SDPBackend.EFFICIENT_ATTENTION])


def solve(engine: Engine, mode: str, problem: Problem, max_answer_tokens: int) -> dict:
    engine_mode, steps = MODES[mode]
    relay = Relay(engine, ANALYSTS, SOLVER, mode=engine_mode, latent_steps=steps)
    text = f"Problem:\n{problem.question}"
    texts = {agent.name: text for agent in [*ANALYSTS, SOLVER]}
    with sdpa_constraint(engine.model.device, engine.model.dtype):
        outcome = relay.run(f"g1-{mode}-{problem.id}", texts, max_tokens=max_answer_tokens)
    final = outcome.final.text if outcome.final else None
    answer = extract_answer(final) if final else None
    truncated = sum(m.label["tokens_generated"] >= engine.max_text_tokens for m in outcome.messages if m.text)
    if outcome.final and outcome.final.tokens_generated >= max_answer_tokens:
        truncated += 1
    return {
        "id": problem.id,
        "mode": mode,
        "latent_steps": steps,
        "correct_answer": problem.answer,
        "answer": answer,
        "correct": is_correct(answer, problem.answer),
        "tokens_generated": outcome.tokens_generated,
        "tokens_read": outcome.tokens_read,
        "latent_positions": outcome.latent_positions,
        "seconds": round(outcome.seconds, 3),
        "truncated": truncated,
        "stopped": None if outcome.stopped is None else f"{outcome.stopped.check}: {outcome.stopped.reason}",
        "final_text": final,
    }


def run_mode(
    engine: Engine, mode: str, problems: list[Problem], output: Path, *, max_answer_tokens: int = 1024
) -> list[dict]:
    """Solves the problems missing from `output` and returns all the rows, old and new, in order."""
    done = {}
    if output.exists():
        done = {r["id"]: r for r in map(json.loads, output.read_text().splitlines())}
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("a") as f:
        for problem in problems:
            if problem.id in done:
                continue
            row = solve(engine, mode, problem, max_answer_tokens)
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
            f.flush()
            done[problem.id] = row
            print(
                f"{mode} {problem.id}: {'correct' if row['correct'] else 'wrong'} "
                f"({row['tokens_generated']} tokens, {row['seconds']} s)",
                flush=True,
            )
    return [done[p.id] for p in problems]


def environment(model: Model, args: argparse.Namespace) -> dict:
    device = model.device
    return {
        "time": datetime.now(UTC).isoformat(),
        "model": model.name,
        "revision": model.revision,
        "dtype": str(model.dtype).removeprefix("torch."),
        "device": device,
        "gpu": torch.cuda.get_device_name(0) if device == "cuda" else platform.processor(),
        "torch": torch.__version__,
        "hip": getattr(torch.version, "hip", None),
        "transformers": transformers.__version__,
        "max_text_tokens": args.max_text_tokens,
        "max_answer_tokens": args.max_answer_tokens,
        "problems": args.problems,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--model", default="Qwen/Qwen3-14B")
    parser.add_argument("--revision", default="40c069824f4251a91eefaf281ebe4c544efd3e18")
    parser.add_argument("--problems", type=int, default=100)
    parser.add_argument("--modes", nargs="+", choices=list(MODES), default=list(MODES))
    parser.add_argument("--output", type=Path, default=Path("results"))
    parser.add_argument("--max-text-tokens", type=int, default=1024, help="per agent, in text mode")
    parser.add_argument("--max-answer-tokens", type=int, default=1024, help="for the final answer, in every mode")
    parser.add_argument("--dtype", choices=["bf16", "fp32"], default=None, help="default: bf16 on GPU, fp32 elsewhere")
    args = parser.parse_args()

    dtype = {"bf16": torch.bfloat16, "fp32": torch.float32, None: None}[args.dtype]
    model = Model(args.model, args.revision, dtype=dtype)
    engine = Engine(model, max_text_tokens=args.max_text_tokens)
    args.output.mkdir(parents=True, exist_ok=True)
    (args.output / "environment.json").write_text(json.dumps(environment(model, args), indent=2) + "\n")
    # One problem at a time in the three modes: if time runs out, the finished problems can still be compared.
    for problem in load_problems(args.problems):
        for mode in args.modes:
            run_mode(
                engine,
                mode,
                [problem],
                args.output / f"{mode}.jsonl",
                max_answer_tokens=args.max_answer_tokens,
            )


if __name__ == "__main__":
    main()
