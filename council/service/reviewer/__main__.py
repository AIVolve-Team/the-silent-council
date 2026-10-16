"""Starts the council's server for Evolus: Qwen3 loaded once, the two tools via MCP and HTTP.

    export COUNCIL_SECRET=$(openssl rand -hex 32)      # the same goes into Evolus's connector
    python -m reviewer --model Qwen/Qwen3-14B --steps 10 \\
        --link "https://council.example.org/verdict/{id}?key={key}" --public-host council.example.org

With `--long-model google/gemma-4-31B-it` the contracts over `--threshold` tokens (6,000 by default) go to that model,
the others to `--model` (`routing.py`). Gemma 4 needs transformers 5.

For the judges' live reviews add `--live dev` (and `test` only after the eval of “Council eval”; `--with-demo` only at
delivery). On a small Mac, `--max-tokens 14000` leaves out the long contracts.

TLS is done by Caddy in front (`caddy reverse-proxy --from council.example.org --to 127.0.0.1:8001`), or by uvicorn
with `--ssl-certfile`, `--ssl-keyfile` and `--host 0.0.0.0`. Each case is saved in `--cases/<id>/`: review, view,
verdict page and the person's choices. The contract's text is not saved.
"""

from __future__ import annotations

import argparse
import os
import sys
from collections.abc import Callable
from pathlib import Path

# The council lives in council/review, which is not installed: it is used from there.
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "review"))

import torch
import uvicorn
from engine import Engine, Model
from review import BENCHMARK, Council
from review.live import SUBSETS, catalog
from review.run import MODELS

from .manager import Reviewer
from .routing import THRESHOLD, Router
from .server import create_app


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--model", default="Qwen/Qwen3-14B", choices=list(MODELS))
    parser.add_argument("--long-model", choices=list(MODELS), help="the model for contracts over the threshold")
    parser.add_argument("--threshold", type=int, default=THRESHOLD, help="contract tokens, with the --model tokenizer")
    parser.add_argument("--dtype", choices=["float32", "bfloat16", "float16"], help="bf16 on GPU by default")
    parser.add_argument("--steps", type=int, default=10, help="latent steps: the ones chosen in “Council on the engine”")
    parser.add_argument("--no-realign", action="store_true")
    parser.add_argument(
        "--link", required=True, help='the page, with {id} and {key}: "https://…/verdict/{id}?key={key}"'
    )
    parser.add_argument("--cases", type=Path, default=Path.home() / ".council" / "cases")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8001)
    parser.add_argument("--public-host", action="append", default=[], help="the name it is reached by from outside")
    parser.add_argument("--ssl-certfile", default=None)
    parser.add_argument("--ssl-keyfile", default=None)
    parser.add_argument(
        "--live",
        nargs="+",
        choices=SUBSETS,
        help="turns on the judges' live reviews with the CUAD contracts of these subsets",
    )
    parser.add_argument("--with-demo", action="store_true", help="only at delivery: the demo set too")
    parser.add_argument("--max-tokens", type=int, help="live reviews: leaves out the longer contracts")
    args = parser.parse_args()

    secret = os.environ.get("COUNCIL_SECRET", "")
    if len(secret) < 32:
        sys.exit(
            "COUNCIL_SECRET of at least 32 characters is required, for example: export COUNCIL_SECRET=$(openssl rand -hex 32)"
        )

    def load(name: str) -> tuple[Model, Callable[..., dict]]:
        model = Model(
            name,
            MODELS[name],
            dtype=getattr(torch, args.dtype) if args.dtype else None,
            realign=not args.no_realign,
        )
        engine = Engine(model, log_dir=args.cases / "log")
        councils: dict[tuple[str, str], Council] = {}

        def review(case_id: str, text: str, mode: str, benchmark: str = "demo") -> dict:
            # One council per benchmark and mode: the CUAD contracts of the live reviews with the CUAD rules.
            if (benchmark, mode) not in councils:
                councils[(benchmark, mode)] = Council(engine, BENCHMARK[benchmark], mode=mode, latent_steps=args.steps)
            return councils[(benchmark, mode)].review(case_id, text).as_dict()

        return model, review

    model, review = load(args.model)

    def length(text: str) -> int:
        return len(model.tokenizer.encode(text, add_special_tokens=False))

    if args.long_model:
        _, review_long = load(args.long_model)
        review = Router(review, review_long, length, args.threshold)
        print(f"Routing: up to {args.threshold} tokens {args.model}, beyond {args.long_model}")

    items = None
    if args.live:
        items = catalog(tuple(args.live), with_demo=args.with_demo, length=length, max_tokens=args.max_tokens)
        print(f"Live reviews on: {len(items)} contracts", flush=True)
    reviewer = Reviewer(review, args.cases, secret=secret, link=args.link, catalog=items)
    app = create_app(reviewer, secret, public_hosts=tuple(args.public_host))
    uvicorn.run(app, host=args.host, port=args.port, ssl_certfile=args.ssl_certfile,
                ssl_keyfile=args.ssl_keyfile)  # fmt: skip


if __name__ == "__main__":
    main()
