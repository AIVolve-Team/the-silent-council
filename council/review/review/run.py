"""Runs the council on a subset of contracts and writes one review per line.

Examples:
    python -m review.run --benchmark cuad --subset dev --mode telepathy --steps 10
    python -m review.run --benchmark demo --mode text
    python -m review.run --benchmark cuad --subset dev --steps 0 10 20 40   # calibration of the steps
    python -m review.run --benchmark demo --no-realign --steps 0 10 40   # diagnosis
"""

from __future__ import annotations

import argparse
import gc
import json
from collections import Counter
from pathlib import Path

import torch
from engine import TELEPATHY, TEXT, Engine, Model

from .categories import BENCHMARK
from .council import MAX_ANALYSIS_TOKENS, Council
from .data import contracts, correct_answers, demo
from .scoring import agreement, score

MODELS = {
    "Qwen/Qwen3-0.6B": "c1899de289a04d12100db370d81485cdf75e47ca",
    "Qwen/Qwen3-1.7B": "70d244cc86ccca08cf5af4e1e306ecf908b1ad5e",
    "Qwen/Qwen3-4B": "1cfa9a7208912126459214e8b04321603b3df60c",
    "Qwen/Qwen3-8B": "b968826d9c46dd6066d109eabc6255188de91218",
    # The council's model, at the same revision as the tokenizer used to count the tokens.
    "Qwen/Qwen3-14B": "40c069824f4251a91eefaf281ebe4c544efd3e18",
    # Gemma 4 spike: hybrid attention, 5 sliding-window layers of 1024 tokens and 1 global; needs transformers 5.
    "google/gemma-4-12B-it": "707f0a3b8a3c7ad586ed01e27eafbad8a27dd0f7",
    "google/gemma-4-31B-it": "842da3794eaa0b77d5f08bae87a17459d91ff475",
}


def _contracts_and_answers(benchmark: str, subset: str) -> tuple[list[tuple[str, str]], dict]:
    if benchmark == "demo":
        items = demo()
        correct = {(cid, r["category"]): r["should_flag"] for cid, _, expected in items for r in expected["rows"]}
        return [(cid, text) for cid, text, _ in items], correct
    return contracts(benchmark, subset), correct_answers(benchmark, subset)


def free_memory() -> None:
    """Between one contract and the next: on a Mac the GPU cache does not go back to the system by itself."""
    gc.collect()
    if torch.backends.mps.is_available():
        torch.mps.empty_cache()
    elif torch.cuda.is_available():
        torch.cuda.empty_cache()


def synopsis(reviews: list[dict], correct: dict) -> str:
    s = score(reviews, correct)
    # The notes taken as the verdict and the agreement with the verdict tell where a flag gets lost: in the experts or
    # in the rapporteur.
    from_notes = score(reviews, correct, from_notes=True)
    same, compared = agreement(reviews)
    notes = [n for r in reviews for n in r["notes"].values()]
    valid = sum(r["verdict"] is not None and r["verdict"]["data"] is not None for r in reviews)
    dissents = Counter(d["type"] for r in reviews for d in r["dissents"])
    n = len(reviews) or 1
    return (
        f"{len(reviews)} contracts | valid verdicts {valid}/{len(reviews)} | valid notes "
        f"{sum(x['data'] is not None for x in notes)}/{len(notes)} | F1 {s.f1:.1f} (P {s.precision:.1f}, "
        f"R {s.recall:.1f}, MCC {s.mcc:.2f}; always yes {s.f1_always_yes:.1f}) | notes as verdict F1 "
        f"{from_notes.f1:.1f} (P {from_notes.precision:.1f}, R {from_notes.recall:.1f}) | notes and verdict agree "
        f"{same}/{compared} | dissents {dict(dissents)} | "
        f"tokens generated {sum(r['tokens_generated'] for r in reviews) / n:.0f} and read "
        f"{sum(r['tokens_read'] for r in reviews) / n:.0f} per contract | {sum(r['seconds'] for r in reviews) / n:.0f} s"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Runs the council on a subset of contracts.")
    parser.add_argument("--benchmark", choices=sorted(BENCHMARK), required=True)
    parser.add_argument("--subset", choices=["dev", "test"], default="dev")
    parser.add_argument("--mode", choices=[TELEPATHY, TEXT], default=TELEPATHY)
    parser.add_argument("--steps", type=int, nargs="+", default=[10], help="latent steps; several values to calibrate")
    parser.add_argument("--model", default="Qwen/Qwen3-1.7B")
    parser.add_argument("--revision", help="model revision on Hugging Face (by default the one pinned here)")
    parser.add_argument("--limit", type=int, help="only the first N contracts, among those within --max-tokens")
    parser.add_argument(
        "--max-tokens", type=int, help="skips the longer contracts (on a Mac the relay's memory is not enough)"
    )
    parser.add_argument("--translate", action="store_true", help="English translation of the quotes")
    parser.add_argument(
        "--no-realign",
        action="store_true",
        help="the latent steps without LatentMAS's W_a matrix, which is off by default there (diagnosis of 12/10)",
    )
    parser.add_argument(
        "--dtype",
        choices=["float32", "bfloat16", "float16"],
        help="by default bf16 on GPU, fp32 elsewhere; on a 16 GB Mac bf16 is better",
    )
    parser.add_argument("--output", type=Path, default=Path("results"))
    args = parser.parse_args()

    if args.subset == "test":
        raise SystemExit("The test runs only with the pre-registered eval, once, after the rules are committed.")
    dtype = getattr(torch, args.dtype) if args.dtype else None
    model = Model(args.model, args.revision or MODELS[args.model], dtype=dtype, realign=not args.no_realign)
    engine = Engine(model, log_dir=args.output / "log", max_text_tokens=MAX_ANALYSIS_TOKENS)
    items, correct = _contracts_and_answers(args.benchmark, args.subset)
    if args.max_tokens:
        length = {cid: len(model.tokenizer.encode(text, add_special_tokens=False)) for cid, text in items}
        for cid, n in length.items():
            if n > args.max_tokens:
                print(f"  skipped {cid[:60]}: {n} tokens, over {args.max_tokens}", flush=True)
        items = [(cid, text) for cid, text in items if length[cid] <= args.max_tokens]
    items = items[: args.limit] if args.limit else items
    args.output.mkdir(parents=True, exist_ok=True)
    for steps in args.steps:
        council = Council(
            engine, BENCHMARK[args.benchmark], mode=args.mode, latent_steps=steps, translate=args.translate
        )
        name = f"{args.benchmark}-{args.subset}-{args.mode}-m{steps}-{args.model.split('/')[-1]}"
        if args.no_realign:
            name += "-no-realign"  # the normal runs are not overwritten
        reviews = []
        with (args.output / f"{name}.jsonl").open("w") as f:
            for contract, text in items:
                review = council.review(contract, text).as_dict()
                reviews.append(review)
                f.write(json.dumps(review, ensure_ascii=False) + "\n")
                f.flush()
                print(f"  {contract[:60]}: {review['seconds']:.0f} s", flush=True)
                free_memory()
        print(f"{name}: {synopsis(reviews, correct)}", flush=True)


if __name__ == "__main__":
    main()
