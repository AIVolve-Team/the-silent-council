"""Access to the data in `council/data`: categories, sample contracts, correct answers, demo set."""

from __future__ import annotations

import importlib.util
import json
import os
import sys
from functools import cache
from pathlib import Path
from types import ModuleType

DATA = Path(__file__).resolve().parents[2] / "data"
MEASUREMENT_SET = DATA / "measurement-set"
# The CUAD replication is in separate files: the test ones are pinned by hash in the pre-registration.
REPLICATION = "replication"


def _file(name: str, extension: str, subset: str) -> Path:
    return MEASUREMENT_SET / (f"{name}-replication.{extension}" if subset == REPLICATION else f"{name}.{extension}")


def _module(name: str) -> ModuleType:
    """Loads a script of `council/data` as a module, without copying its code."""
    if str(DATA) not in sys.path:
        sys.path.insert(0, str(DATA))
    spec = importlib.util.spec_from_file_location(f"data_{name}", DATA / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@cache
def data_categories() -> ModuleType:
    return _module("categories")


@cache
def _texts(benchmark: str) -> dict[str, str]:
    prepare = _module("prepare")
    readers = {
        "cuad": lambda: prepare.read_cuad(DATA / "cache" / "cuad.zip"),
        "contractnli": lambda: prepare.read_contractnli(DATA / "cache" / "contractnli.zip"),
        "claudette": lambda: prepare.read_claudette(DATA / "cache" / "claudette.tar.gz"),
    }
    return {c["id"]: c["text"] for subset in readers[benchmark]().values() for c in subset}


def contracts(benchmark: str, subset: str) -> list[tuple[str, str]]:
    """(id, text) of the sample contracts, in the order of `sample.json` (`sample-replication.json` for the
    replication). They need the files in `data/cache`, which `prepare.py` downloads."""
    sample = json.loads(_file("sample", "json", subset).read_text())
    if subset not in sample.get(benchmark, {}):
        raise SystemExit(f"{benchmark} has no {subset} subset: the replication exists only on CUAD.")
    texts = _texts(benchmark)
    return [(cid, texts[cid]) for cid in sample[benchmark][subset]]


def _rows(benchmark: str, subset: str):
    for r in _file("correct-answers", "jsonl", subset).open():
        row = json.loads(r)
        if row["benchmark"] == benchmark and row["subset"] == subset:
            yield row


def correct_answers(benchmark: str, subset: str) -> dict[tuple[str, str], bool]:
    """(contract, category) → should flag."""
    return {(r["contract"], r["category"]): r["should_flag"] for r in _rows(benchmark, subset)}


def evidence(benchmark: str, subset: str) -> dict[tuple[str, str], list[str]]:
    """(contract, category) → the annotated text spans, for the strict version of the score. For the demo set
    they are the quotes of the expected answers."""
    if benchmark == "demo":
        return {
            (cid, r["category"]): [r["quote"]] if r.get("quote") else []
            for cid, _, expected in demo()
            for r in expected["rows"]
        }
    return {(r["contract"], r["category"]): r["evidence"] for r in _rows(benchmark, subset)}


def answers_grade_3(subset: str) -> dict[tuple[str, str], bool]:
    """CLAUDETTE with grade 3 only (clearly unfair): the separate view asked for in “Trial contracts and correct answers”."""
    return {(r["contract"], r["category"]): r["should_flag_grade_3"] for r in _rows("claudette", subset)}


@cache
def expert_answers(benchmark: str) -> dict[str, dict[str, dict]]:
    """contract → category → {"should_flag", "evidence"}: the dataset answers, with the annotated spans, of all
    subsets. The judges' site needs them to show next to the verdict what the experts said."""
    experts: dict[str, dict[str, dict]] = {}
    for r in map(json.loads, (MEASUREMENT_SET / "correct-answers.jsonl").open()):
        if r["benchmark"] == benchmark:
            experts.setdefault(r["contract"], {})[r["category"]] = {
                "should_flag": r["should_flag"],
                "evidence": r["evidence"],
            }
    return experts


def demo_folder() -> Path:
    """The demo set stays out of the repo: by default `data/demo-set`, or `COUNCIL_DEMO_SET`."""
    return Path(os.environ.get("COUNCIL_DEMO_SET", DATA / "demo-set"))


def demo() -> list[tuple[str, str, dict]]:
    """(id, text, expected answer) of the demo set contracts."""
    folder = demo_folder()
    return [
        (f.stem, f.read_text(), json.loads(f.with_suffix(".json").read_text())) for f in sorted(folder.glob("*.txt"))
    ]
