"""Starts the council's server for Evolus: Qwen3 loaded once, the two tools via MCP and HTTP.

    export COUNCIL_SECRET=$(openssl rand -hex 32)      # the same goes into Evolus's connector
    python -m reviewer --model Qwen/Qwen3-14B --steps 10 \\
        --link "https://council.example.org/verdict/{id}?key={key}" --public-host council.example.org

With `--long-model google/gemma-4-31B-it` the contracts over `--threshold` tokens (6,000 by default) go to that model,
the others to `--model` (`routing.py`). Gemma 4 needs transformers 5.

With `--playbook playbook.md` the telepathy reviews start from the institutional memory: the playbook and the
precedents the people decide on the verdict pages, kept in `--institution`.

For the judges' live reviews add `--live dev` (and `test` only after the eval of “Council eval”; `--with-demo` only at
delivery). On a small Mac, `--max-tokens 14000` leaves out the long contracts.

TLS is done by Caddy in front (`caddy reverse-proxy --from council.example.org --to 127.0.0.1:8001`), or by uvicorn
with `--ssl-certfile`, `--ssl-keyfile` and `--host 0.0.0.0`. Each case is saved in `--cases/<id>/`: review, view,
verdict page and the person's choices. The contract's text is not saved.

The questions on a case (`ask_council`) are answered from the memory of its review, kept on the GPU within
`--memory-gb` and never written to disk: after a restart, or when newer reviews push it out, the contract must be
reviewed again.

A contract in PDF is inspected first (`review.visual`, no model): a simple PDF goes as above; a complex one
(scanned pages, signatures, stamps, drawings, hidden text) is read without its hidden text. Its case says why, in
`visual.json`. The visual mode is on when Gemma 4 31B is loaded, as `--model` or `--long-model`: a visual expert sees
the pages that fired a signal as images at the head of the council's chain, and the council then answers the visual
checks (who signed, stamps, handwriting) from the memory of the review. Without Gemma 4 31B complex PDFs go the text
way.

Evolus sends only the text of an attachment: with `COUNCIL_IMAP_USER` and `COUNCIL_IMAP_PASSWORD` (an app
password) the server reads the PDF from the same contracts mailbox, read-only, and a complex one goes the visual way.
`COUNCIL_IMAP_FOLDER` is the folder Evolus reads ("Contratti" by default), `COUNCIL_IMAP_HOST` the server (Gmail).
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

from .institution import Institution, Memory
from .mailbox import Mailbox
from .manager import Reviewer
from .memory import Memories
from .routing import THRESHOLD, Router
from .server import create_app

# The visual mode always reads the pages with Gemma 4 31B, the router aside: the model of the probe.
VISION = "google/gemma-4-31B-it"
# Soft tokens per page image: in the probe of 17/10 on A, B, C and D, 560 found what 1120 found, in less time.
VISUAL_TOKENS = 560


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
    parser.add_argument(
        "--memory-gb", type=float, default=24.0, help="memory of the last reviews kept for ask_council, on the GPU"
    )
    parser.add_argument(
        "--playbook", type=Path, help="the company's playbook: turns on the institutional memory in telepathy"
    )
    parser.add_argument("--institution", type=Path, default=Path.home() / ".council" / "institution")
    args = parser.parse_args()

    secret = os.environ.get("COUNCIL_SECRET", "")
    if len(secret) < 32:
        sys.exit(
            "COUNCIL_SECRET of at least 32 characters is required, for example: export COUNCIL_SECRET=$(openssl rand -hex 32)"
        )

    memories = Memories(int(args.memory_gb * 2**30))
    institution = Institution(args.playbook, args.institution) if args.playbook else None

    def load(name: str) -> tuple[Model, Callable[..., dict]]:
        model = Model(
            name,
            MODELS[name],
            dtype=getattr(torch, args.dtype) if args.dtype else None,
            realign=not args.no_realign,
            soft_tokens_per_page=VISUAL_TOKENS,
        )
        engine = Engine(model, log_dir=args.cases / "log")
        councils: dict[tuple[str, str], Council] = {}
        memory = Memory(institution, engine) if institution else None

        def review(case_id: str, text: str, mode: str, benchmark: str = "demo", visual: tuple | None = None) -> dict:
            # One council per benchmark and mode: the CUAD contracts of the live reviews with the CUAD rules.
            if (benchmark, mode) not in councils:
                councils[(benchmark, mode)] = Council(engine, BENCHMARK[benchmark], mode=mode, latent_steps=args.steps)
            council = councils[(benchmark, mode)]
            if memory is None or mode != "telepathy":
                # the institutional memory is a cache to pass on: in text mode there is none
                result = council.review(case_id, text, visual=visual).as_dict() | {"institution": None}
            else:
                version, base = memory.current()
                result = council.review(case_id, text, base=base, visual=visual).as_dict() | {
                    "institution": {
                        "version": version,
                        "precedents": len(institution.precedents()),
                        "base_fingerprints": [m.fingerprint for m in base],
                    }
                }
            # The questions on this case are answered by the same council, from this memory.
            memories.keep(case_id, council, council.memory)
            return result

        return model, review

    model, review = load(args.model)
    reviews = {args.model: review}

    def length(text: str) -> int:
        return len(model.tokenizer.encode(text, add_special_tokens=False))

    if args.long_model:
        _, review_long = load(args.long_model)
        reviews[args.long_model] = review_long
        review = Router(review, review_long, length, args.threshold)
        print(f"Routing: up to {args.threshold} tokens {args.model}, beyond {args.long_model}")

    items = None
    if args.live:
        items = catalog(tuple(args.live), with_demo=args.with_demo, length=length, max_tokens=args.max_tokens)
        print(f"Live reviews on: {len(items)} contracts", flush=True)
    visual_review = None
    if VISION in reviews:
        from review.visual import SECTIONS, render_pages, skill_text

        # The visual expert's instructions are the whole skill, the same for every PDF, not the sections its signals
        # call for: in the probe of 17/10 it found as much, and a fixed prompt is the same for every case.
        instructions = skill_text(SECTIONS)
        review_pages = reviews[VISION]

        def visual_review(case_id, text, pdf, pages, mode, benchmark, skill) -> dict:
            """The visual route (manager.Reviewer): the visual expert sees `pages` as images at the head of the chain,
            the experts read the clauses in `text`, the visible text. Called under the review lock: it calls nothing of
            the Reviewer. `skill` is not used: the visual expert has the whole skill. Keeps the memory like `review`,
            so the visual checks and ask_council answer from it."""
            images = render_pages(pdf, pages)
            return review_pages(case_id, text, mode, benchmark, visual=(instructions, pages, images))

        print(f"Visual mode on: the pages go to {VISION}, {VISUAL_TOKENS} soft tokens each")
    mailbox = None
    if os.environ.get("COUNCIL_IMAP_USER") and os.environ.get("COUNCIL_IMAP_PASSWORD"):
        mailbox = Mailbox(
            os.environ["COUNCIL_IMAP_USER"],
            os.environ["COUNCIL_IMAP_PASSWORD"],
            host=os.environ.get("COUNCIL_IMAP_HOST", "imap.gmail.com"),
            folder=os.environ.get("COUNCIL_IMAP_FOLDER", "Contratti"),
        )
        print(f"Contracts mailbox on: {mailbox.folder} of {mailbox.user}, for the PDFs Evolus sends as text")
    reviewer = Reviewer(
        review,
        args.cases,
        secret=secret,
        link=args.link,
        catalog=items,
        ask=memories.ask,
        visual_review=visual_review,
        institution=institution,
        find_pdf=mailbox.find_pdf if mailbox else None,
    )
    if institution:
        print(f"Institutional memory on: {len(institution.precedents())} precedents, version {institution.version()}")
    app = create_app(reviewer, secret, public_hosts=tuple(args.public_host))
    uvicorn.run(app, host=args.host, port=args.port, ssl_certfile=args.ssl_certfile,
                ssl_keyfile=args.ssl_keyfile)  # fmt: skip


if __name__ == "__main__":
    main()
