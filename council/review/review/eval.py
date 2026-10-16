"""The council's eval: runs the compared configurations and writes their report.

Examples:
    python -m review.eval run --benchmark cuad --subset dev --steps 10 --model Qwen/Qwen3-14B
    python -m review.eval run --benchmark demo --steps 10 --configurations telepathy m0
    python -m review.eval report eval

The model is loaded once for all configurations. Each configuration writes
`<benchmark>-<subset>-<configuration>.jsonl`, one review per line; `eval-<benchmark>-<subset>.json` says what it ran
with. On the test set the eval starts only with the pre-registration frozen and committed
(`council/PREREGISTRAZIONE.md`), and only once: a second run is a deviation and asks for the reason. The CUAD
replication follows the same rules, and in addition starts only if the pre-registration has its section.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import time
from datetime import UTC, datetime
from pathlib import Path

import torch
from engine import TELEPATHY, TEXT, Engine, Model

from . import metrics
from .categories import BENCHMARK
from .configurations import SoloAgent, VoteAmongFour
from .council import MAX_ANALYSIS_TOKENS, Council
from .data import REPLICATION, answers_grade_3, correct_answers, demo, evidence
from .run import MODELS, _contracts_and_answers, free_memory, synopsis

ROOT = Path(__file__).resolve().parents[3]
PREREGISTRATION = ROOT / "council" / "PREREGISTRAZIONE.md"
# The status line of the pre-registration until it is frozen: with this line the test does not start. The
# pre-registration is a frozen Italian document, so these markers are its own words.
DRAFT = "Stato: bozza"
# Run order: telepathy comes first because its thoughts are needed by the swapped-thoughts test.
ORDER = ("telepathy", "text", "solo", "vote", "m0", "swapped-thoughts", "swapped-contract")
# The subsets that run only once, with the committed rules and all the contracts.
PREREGISTERED = ("test", REPLICATION)
# The replication starts only if the pre-registration has this section, and reruns only these three
# configurations.
REPLICATION_SECTION = "## Replica su CUAD"
REPLICATION_CONFIGURATIONS = ("telepathy", "text", "solo")
# Test and replication together, in the report: G4 stays decided on the test.
TOTAL = "total"


def _git(*args: str) -> str:
    return subprocess.run(["git", "-C", str(ROOT), *args], capture_output=True, text=True, check=True).stdout


def check_preregistration(subset: str = "test") -> dict:
    """The pre-registration must be frozen and committed, and the code without local changes. For the
    replication it must also have its section."""
    if not PREREGISTRATION.exists():
        raise SystemExit(f"The pre-registration is missing: {PREREGISTRATION}")
    text = PREREGISTRATION.read_text()
    if DRAFT in text:
        raise SystemExit(
            "The pre-registration is still a draft: it must be frozen and committed before the test."
        )
    if subset == REPLICATION and REPLICATION_SECTION not in text:
        raise SystemExit(
            f"For the replication the pre-registration must have the section «{REPLICATION_SECTION}»."
        )
    relative = str(PREREGISTRATION.relative_to(ROOT))
    if _git("status", "--porcelain", "--", relative).strip():
        raise SystemExit("The pre-registration has uncommitted changes: the test uses only committed rules.")
    if _git("status", "--porcelain", "--untracked-files=no", "--", "council", "engine").strip():
        raise SystemExit("The code in council/ or engine/ has uncommitted changes: the test runs on a commit.")
    commit, date = _git("log", "-1", "--format=%H %cI", "--", relative).split()
    return {
        "file": relative,
        "commit": commit,
        "commit_date": date,
        "sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
    }


def _correct(benchmark: str, subset: str) -> dict:
    if benchmark == "demo":
        return {(cid, r["category"]): r["should_flag"] for cid, _, expected in demo() for r in expected["rows"]}
    return correct_answers(benchmark, subset)


def run(args: argparse.Namespace) -> None:
    output: Path = args.output
    output.mkdir(parents=True, exist_ok=True)
    chosen = [c for c in ORDER if c in args.configurations]
    if args.subset == REPLICATION and set(chosen) != set(REPLICATION_CONFIGURATIONS):
        raise SystemExit(f"The replication reruns only {', '.join(REPLICATION_CONFIGURATIONS)}.")
    if args.steps == 0 and {"m0", "swapped-thoughts"} & set(chosen):
        # With 0 steps there are no thoughts: "zeroed thoughts" would be the same run as telepathy and the thoughts of
        # another contract do not exist. The two tests are not run (PREREGISTRAZIONE.md, sabotage tests).
        print("0 latent steps: no tests on the thoughts (zeroed thoughts, swapped thoughts).", flush=True)
        chosen = [c for c in chosen if c not in ("m0", "swapped-thoughts")]
    if "swapped-thoughts" in chosen and "telepathy" not in chosen:
        raise SystemExit("The swapped thoughts use the thoughts of the telepathy run: add telepathy.")
    preregistration, deviation = None, None
    if args.subset in PREREGISTERED:
        preregistration = check_preregistration(args.subset)
        previous = sorted(output.glob(f"{args.benchmark}-{args.subset}-*.jsonl"))
        if previous and not args.deviation:
            raise SystemExit(
                f"The {args.subset} runs only once. Another run needs --deviation with the reason, to be written "
                "also among the deviations of the pre-registration."
            )
        deviation = args.deviation
    dtype = getattr(torch, args.dtype) if args.dtype else None
    model = Model(args.model, args.revision or MODELS[args.model], dtype=dtype, realign=not args.no_realign)
    engine = Engine(model, log_dir=output / "log", max_text_tokens=MAX_ANALYSIS_TOKENS)
    items, correct = _contracts_and_answers(args.benchmark, args.subset)
    if args.max_tokens:
        length = {cid: len(model.tokenizer.encode(text, add_special_tokens=False)) for cid, text in items}
        items = [(cid, text) for cid, text in items if length[cid] <= args.max_tokens]
    items = items[: args.limit] if args.limit else items
    if len(items) < 2 and {"swapped-thoughts", "swapped-contract"} & set(chosen):
        raise SystemExit("The swaps need at least 2 contracts.")
    meta = {
        "benchmark": args.benchmark,
        "subset": args.subset,
        "model": args.model,
        "revision": model.revision,
        "dtype": str(model.dtype).removeprefix("torch."),
        "device": model.device,
        "realign": model.realign,
        "steps": args.steps,
        "configurations": chosen,
        "contracts": [cid for cid, _ in items],
        "code": _git("rev-parse", "HEAD").strip(),
        "local_changes": bool(_git("status", "--porcelain", "--untracked-files=no").strip()),
        "preregistration": preregistration,
        "deviation": deviation,
        "start": datetime.now(UTC).isoformat(),
    }
    (output / f"eval-{args.benchmark}-{args.subset}.json").write_text(json.dumps(meta, indent=2))
    benchmark = BENCHMARK[args.benchmark]
    thoughts: dict[str, dict] = {}
    for configuration in chosen:
        if configuration in ("solo", "vote"):
            cls = SoloAgent if configuration == "solo" else VoteAmongFour
            runner = cls(engine, benchmark, translate=args.translate)
        else:
            mode = TEXT if configuration == "text" else TELEPATHY
            steps = 0 if configuration == "m0" else args.steps
            runner = Council(engine, benchmark, mode=mode, latent_steps=steps, translate=args.translate)
        name = f"{args.benchmark}-{args.subset}-{configuration}"
        print(f"-- {name} ({time.strftime('%H:%M')})", flush=True)
        reviews = []
        with (output / f"{name}.jsonl").open("w") as f:
            for i, (contract, text) in enumerate(items):
                other, other_text = items[(i + 1) % len(items)]
                extra: dict = {"configuration": configuration}
                if configuration in ("solo", "vote"):
                    review = runner.review(contract, text)
                elif configuration == "swapped-thoughts":
                    review = runner.review(contract, text, thoughts_from=thoughts[other]).as_dict()
                    extra["thoughts_from"] = other
                elif configuration == "swapped-contract":
                    review = runner.review(contract, other_text).as_dict()
                    extra["text_from"] = other
                else:
                    review = runner.review(contract, text).as_dict()
                    if configuration == "telepathy":
                        thoughts[contract] = runner.thoughts
                review |= extra
                reviews.append(review)
                f.write(json.dumps(review, ensure_ascii=False) + "\n")
                f.flush()
                print(f"  {contract[:60]}: {review['seconds']:.0f} s", flush=True)
                free_memory()
        print(f"{name}: {synopsis(reviews, correct)}", flush=True)
    meta["end"] = datetime.now(UTC).isoformat()
    (output / f"eval-{args.benchmark}-{args.subset}.json").write_text(json.dumps(meta, indent=2))


# --- report --------------------------------------------------------------------------------------------------------


def _n(x: float, digits: int = 1) -> str:
    return f"{x:.{digits}f}"


def _signed(x: float) -> str:
    return ("+" if x > 0 else "") + _n(x)


def _integer(x: float) -> str:
    return f"{x:,.0f}"


def _fraction(pair: tuple[int, int]) -> str:
    a, n = pair
    return f"{a}/{n}" + (f" ({_n(100 * a / n, 0)}%)" if n else "")


def _runs(folder: Path) -> dict[tuple[str, str], dict[str, list[dict]]]:
    runs: dict[tuple[str, str], dict[str, list[dict]]] = {}
    for f in sorted(folder.glob("*.jsonl")):
        benchmark, subset, configuration = f.stem.split("-", 2)
        if configuration not in metrics.CONFIGURATIONS:
            continue
        rows = [json.loads(r) for r in f.read_text().splitlines() if r.strip()]
        runs.setdefault((benchmark, subset), {})[configuration] = rows
    return runs


def write_report(folder: Path) -> str:
    """Writes `report.md`, `numbers.json` and one chart per benchmark in the results folder. Aggregate numbers only:
    the report can be pasted into the ticket."""
    parts = ["# Council eval: report", ""]
    everything = {}
    runs = _runs(folder)
    for (benchmark, subset), subset_runs in runs.items():
        meta_file = folder / f"eval-{benchmark}-{subset}.json"
        meta = json.loads(meta_file.read_text()) if meta_file.exists() else {}
        correct = _correct(benchmark, subset)
        if not correct:
            raise SystemExit(f"The correct answers of {benchmark} are missing: for the demo set see COUNCIL_DEMO_SET.")
        texts = {cid: text for cid, text, _ in demo()} if benchmark == "demo" else None
        grade_3 = answers_grade_3(subset) if benchmark == "claudette" else None
        numbers = metrics.summary(subset_runs, correct, evidence(benchmark, subset), texts=texts, grade_3=grade_3)
        numbers["meta"] = meta
        everything[f"{benchmark}-{subset}"] = numbers
        parts += _section(benchmark, subset, numbers, meta)
        points = [
            (metrics.NAMES[c], r["tokens_generated"], r["f1"])
            for c, r in numbers["configurations"].items()
            if c in ("solo", "vote", "text", "telepathy")
        ]
        if points:
            title = f"{benchmark} ({subset}): quality against cost"
            (folder / f"chart-{benchmark}-{subset}.svg").write_text(metrics.svg_chart(points, title))
            parts += [f"![Quality against cost](chart-{benchmark}-{subset}.svg)", ""]
    test, replication = runs.get(("cuad", "test")), runs.get(("cuad", REPLICATION))
    if test and replication:
        everything[f"cuad-{TOTAL}"] = numbers = _total(test, replication)
        parts += _section("cuad", TOTAL, numbers, {})
        parts += _confirmation(everything["cuad-test"], everything[f"cuad-{REPLICATION}"])
    text = "\n".join(parts)
    (folder / "report.md").write_text(text)
    (folder / "numbers.json").write_text(json.dumps(everything, indent=2, ensure_ascii=False, default=list))
    return text


def _total(test: dict[str, list[dict]], replication: dict[str, list[dict]]) -> dict:
    """The CUAD numbers on test and replication together, for the replication's configurations: the paired
    bootstrap resamples the contracts of both."""
    runs = {c: test[c] + replication[c] for c in REPLICATION_CONFIGURATIONS if c in test and c in replication}
    correct = correct_answers("cuad", "test") | correct_answers("cuad", REPLICATION)
    return metrics.summary(runs, correct, evidence("cuad", "test") | evidence("cuad", REPLICATION))


def _confirmation(test: dict, replication: dict) -> list[str]:
    """The replication confirms G4 if its three conditions give the same outcome as the test, refutes it if not
."""
    if "telepathy_vs_text" not in test or "telepathy_vs_text" not in replication:
        return []
    test_passes, replication_passes = (all(n["telepathy_vs_text"]["g4"].values()) for n in (test, replication))
    outcome = "passed" if test_passes else "not passed"
    verb = "**confirms**" if test_passes == replication_passes else "**refutes**"
    return [
        f"**G4 and replication:** G4 stays decided on the test, where it is {outcome}. The replication {verb} it.",
        "",
    ]


def _section(benchmark: str, subset: str, numbers: dict, meta: dict) -> list[str]:
    configurations = numbers["configurations"]
    contracts = max(r["contracts"] for r in configurations.values())
    rows = [f"## {benchmark}, {subset} ({contracts} contracts)", ""]
    if meta:
        prereg = meta.get("preregistration") or {}
        rows += [
            f"Model {meta.get('model')} ({meta.get('dtype')}, {meta.get('device')}), latent steps "
            f"{meta.get('steps')}, realignment {'on' if meta.get('realign') else 'off'}, code "
            f"`{str(meta.get('code'))[:7]}`"
            + (f", pre-registration `{prereg['commit'][:7]}` of {prereg['commit_date'][:10]}" if prereg else "")
            + (f". **Deviation:** {meta['deviation']}" if meta.get("deviation") else "")
            + ".",
            "",
        ]
    rows += [
        (
            "| Configuration | F1 | P | R | MCC | Always yes | Strict F1 | Missed | False alarms "
            "| Valid verdicts | Tokens generated | Tokens read | Seconds |"
        ),
        "|---|---|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for c in metrics.CONFIGURATIONS:
        if c not in configurations:
            continue
        r = configurations[c]
        rows.append(
            f"| {metrics.NAMES[c]} | **{_n(r['f1'])}** | {_n(r['precision'])} | {_n(r['recall'])} | "
            f"{_n(r['mcc'], 2)} | {_n(r['always_yes'])} | {_n(r['strict_f1'])} | {r['missed']} | "
            f"{r['false_alarms']} | {r['valid_verdicts']}/{r['contracts']} | {_integer(r['tokens_generated'])} | "
            f"{_integer(r['tokens_read'])} | {_integer(r['seconds'])} |"
        )
    rows.append("")
    comparison = numbers.get("telepathy_vs_text")
    if comparison:
        tele, text = configurations["telepathy"], configurations["text"]
        saving = 1 - tele["tokens_generated"] / text["tokens_generated"] if text["tokens_generated"] else 0
        # The judgement is pre-registered only on CUAD, and G4 is decided on the test: replication and total confirm
        # or refute it. The other benchmarks are reported without a threshold.
        if benchmark == "cuad" and subset in (REPLICATION, TOTAL):
            judgement = " G4 stays decided on the test."
        elif benchmark == "cuad":
            judgement = "does not lose, shown" if comparison["shown"] else "compatible results"
            judgement = f" We say: *{judgement}*."
        else:
            judgement = " Without a threshold: on this benchmark no judgement is given."
        rows += [
            "### Telepathy against text",
            "",
            (
                f"- **Telepathy F1 minus text F1:** {_signed(comparison['difference'])} points (95% interval with a "
                f"paired bootstrap on the {comparison['contracts']} contracts: from {_n(comparison['low'])} to "
                f"{_n(comparison['high'])}).{judgement}"
            ),
            (
                f"- **Tokens generated:** {_n(100 * saving, 0)}% fewer. **Time:** {_integer(tele['seconds'])} s "
                f"against {_integer(text['seconds'])} s per contract."
            ),
        ]
        solo = numbers.get("telepathy_vs_solo")
        if solo:
            rows.append(
                f"- **Telepathy F1 minus solo agent F1:** {_signed(solo['difference'])} points (95% interval: from "
                f"{_n(solo['low'])} to {_n(solo['high'])}). It is the comparison that isolates the channel: in "
                "telepathy the rapporteur works on the memory of the reading of the whole contract, the solo agent "
                "reads the whole contract."
            )
        if text.get("analyses"):
            rows.append(
                f"- **Text analyses that hit the cap of {MAX_ANALYSIS_TOKENS} tokens:** "
                f"{text['truncated_analyses']} of {text['analyses']}."
            )
        if benchmark == "cuad" and subset != TOTAL:
            g4 = comparison["g4"]
            rows += [
                "",
                "**G4 on the replication** (it does not decide, it confirms or refutes the test):"
                if subset == REPLICATION
                else "**G4** (on CUAD):",
                "",
                f"- [{'x' if g4['f1'] else ' '}] telepathy F1 ≥ text F1 − 3 points",
                f"- [{'x' if g4['tokens'] else ' '}] tokens generated at least −50%",
                f"- [{'x' if g4['time'] else ' '}] telepathy is not slower than text",
            ]
        rows.append("")
    if numbers.get("sabotages"):
        rows += ["### Sabotage tests", "", "| Test | F1 difference from telepathy |", "|---|---|"]
        rows += [f"| {metrics.NAMES[c]} | {_signed(d)} |" for c, d in numbers["sabotages"].items()]
        if meta.get("steps") == 0:
            # 0 steps: no latent thoughts, so no tests on the thoughts and the fallback sentence.
            rows += [
                "",
                "With 0 latent steps there are no thoughts: the tests on the thoughts are not run.",
                f"Sentence for the jury: *{metrics.SENTENCE_MEMORY}* And then: *{metrics.SENTENCE_FALLBACK}*",
                "",
            ]
        else:
            help_ = numbers.get("thoughts_help")
            sentence = {
                True: metrics.SENTENCE_THOUGHTS,
                False: metrics.SENTENCE_FALLBACK,
                None: "the tests on the thoughts are missing to decide",
            }[help_]
            rows += ["", f"Sentence for the jury: *{metrics.SENTENCE_ALWAYS}* And then: *{sentence}*", ""]
        if "swapped-contract" in numbers["sabotages"]:
            rows += ["The swapped contract must collapse: if it does not, there is a bug in the code.", ""]
    without = numbers.get("without_threshold") or {}
    if without:
        rows += ["### Without a threshold", ""]
        for c, s in without.items():
            d, t = s["dissents"], s["calibration"]
            rows.append(
                f"- **{metrics.NAMES[c]}:** major dissents {d['major'][1]}, the expert right "
                f"{_fraction(d['major'])}; minor dissents {d['minor'][1]}, the rapporteur right "
                f"{_fraction(d['minor'])}. Agreement between notes and verdict {_fraction(s['notes_verdict_agreement'])}; "
                f"F1 of the notes taken as the verdict {_n(s['notes_as_verdict_f1'])}. Verdict calibration, "
                f"correct by confidence: high {_fraction(t['high'])}, medium {_fraction(t['medium'])}, low "
                f"{_fraction(t['low'])}."
            )
        rows.append("")
    if numbers.get("amounts_and_dates"):
        items = ", ".join(
            f"{metrics.NAMES[c]} {n} ({outside} not in the contract)"
            for c in metrics.CONFIGURATIONS
            if c in numbers["amounts_and_dates"]
            for n, outside in [numbers["amounts_and_dates"][c]]
        )
        rows += [f"**Amounts and dates in the verdict:** {items}. One not in the contract is always flagged.", ""]
    if numbers.get("grade_3"):
        items = ", ".join(f"{metrics.NAMES[c]} {_n(f)}" for c, f in numbers["grade_3"].items())
        rows += [f"**CLAUDETTE, grade 3 only:** F1 {items}.", ""]
    return rows


def main() -> None:
    parser = argparse.ArgumentParser(description="The council's eval.")
    commands = parser.add_subparsers(dest="command", required=True)
    go = commands.add_parser("run", help="runs the configurations")
    go.add_argument("--benchmark", choices=sorted(BENCHMARK), required=True)
    go.add_argument("--subset", choices=["dev", "test", REPLICATION], default="dev")
    go.add_argument("--steps", type=int, required=True, help="the latent steps chosen on the dev set")
    go.add_argument("--configurations", nargs="+", choices=ORDER, help="all by default, its three on the replication")
    go.add_argument("--model", default="Qwen/Qwen3-14B")
    go.add_argument("--revision", help="model revision on Hugging Face (by default the pinned one)")
    go.add_argument("--dtype", choices=["float32", "bfloat16", "float16"])
    go.add_argument("--no-realign", action="store_true")
    go.add_argument("--max-tokens", type=int, help="skips the longer contracts (only for trials on a Mac)")
    go.add_argument("--limit", type=int, help="only the first N contracts (only for trials)")
    go.add_argument("--translate", action="store_true", help="English translation of the quotes")
    go.add_argument("--deviation", help="reason for a second run on the test, to be written in the pre-registration")
    go.add_argument("--output", type=Path, default=Path("eval"))
    report = commands.add_parser("report", help="writes report, numbers and charts from a results folder")
    report.add_argument("folder", type=Path)
    args = parser.parse_args()
    if args.command == "run":
        if args.subset in PREREGISTERED and (args.max_tokens or args.limit):
            raise SystemExit("On the test all the contracts run: --max-tokens and --limit are only for trials.")
        if args.subset == REPLICATION and args.benchmark != "cuad":
            raise SystemExit("The replication exists only on CUAD.")
        args.configurations = args.configurations or list(
            REPLICATION_CONFIGURATIONS if args.subset == REPLICATION else ORDER
        )
        run(args)
    else:
        print(write_report(args.folder))


if __name__ == "__main__":
    main()
