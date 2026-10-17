"""Telepathy against text on the visual mode: what the council reports about the marks of the synthetic PDFs.

For each PDF of council/data/vision/pages/ground-truth.json and each mode, the PDF goes to a running server's
`POST /review_contract` (pdf_base64, as Evolus sends it). With the visual mode on, the response carries
`visual.checks`: the questions the council answered on the pages, each with the objects it saw
(`{page, type, box_2d, text}`). Those objects are scored against the ground truth with the probe's matching
(vision_probe.score: same page and type, boxes overlapping at least vision_probe.MIN_IOU), and the script prints, per
mode and per type, found / missed / invented and the seconds per document.

Standalone: only the standard library and vision_probe.py, loaded by path like the probe loads visual.py, so it runs
from any Python without the engine, torch or the service.

    export COUNCIL_SECRET=...   # the server's secret
    python council/review/review/visual_trial.py --url http://localhost:8000 --output results-visual-trial.jsonl
"""

from __future__ import annotations

import argparse
import base64
import importlib.util
import json
import os
import sys
import time
import urllib.error
import urllib.request
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
MODES = ("telepathy", "text")


def load_probe():
    """vision_probe.py without the package __init__, which imports torch and the engine."""
    spec = importlib.util.spec_from_file_location("council_vision_probe", HERE / "vision_probe.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


probe = load_probe()


# --- scoring --------------------------------------------------------------------------------------------------------


def _same(a: dict, b: dict) -> bool:
    """The same object reported twice: same page and type, and boxes that overlap like a match (or no box at all)."""
    if a["page"] != b["page"] or a["type"] != b["type"]:
        return False
    if a["box_2d"] is None or b["box_2d"] is None:
        return a["box_2d"] is None and b["box_2d"] is None
    return probe.iou(a["box_2d"], b["box_2d"]) >= probe.MIN_IOU


def objects_of(response: dict) -> tuple[list[dict], int]:
    """The objects of every check of the response, once each, and how many repeats were dropped.

    Two questions can point at the same mark ("who signed?", "is every party signed?"): it is one object seen, not
    one found and one invented."""
    checks = (response.get("visual") or {}).get("checks") or []
    reported = [o for check in checks if isinstance(check, dict) for o in check.get("objects") or []]
    unique: list[dict] = []
    for o in probe.predicted_objects({"objects": reported}):
        if not any(_same(o, u) for u in unique):
            unique.append(o)
    return unique, len(reported) - len(unique)


def score_response(response: dict, doc: dict) -> dict:
    """The score of one review: per type found / missed / invented, plus what the response says of the visual route."""
    visual = response.get("visual") or {}
    predicted, repeats = objects_of(response)
    counts = probe.score(predicted, doc["objects"])
    return {
        "checks": len(visual.get("checks") or []),
        "objects": predicted,
        "repeats_dropped": repeats,
        "visual_mode": visual.get("visual_mode"),
        "route": visual.get("route"),
        "score": {t: dict(c) for t, c in counts.items()},
    }


def summarize(rows: list[dict]) -> dict:
    """Per mode: documents, errors, rates per type and overall, seconds per document."""
    out = {}
    for mode in dict.fromkeys(r["mode"] for r in rows):
        mine = [r for r in rows if r["mode"] == mode]
        per_type: dict[str, Counter] = {}
        for row in mine:
            for t, c in (row.get("score") or {}).items():
                per_type.setdefault(t, Counter()).update(c)
        timed = [r["seconds"] for r in mine if r.get("seconds") is not None and not r.get("error")]
        out[mode] = {
            "documents": len(mine),
            "errors": sum(1 for r in mine if r.get("error")),
            "without_checks": [
                r["file"] for r in mine if not r.get("error") and r["expected_complex"] and not r["checks"]
            ],
            "seconds_per_document": {r["file"]: r["seconds"] for r in mine if r.get("seconds") is not None},
            "seconds_mean": round(sum(timed) / len(timed), 1) if timed else None,
            "overall": probe.rates(sum(per_type.values(), Counter())),
            "per_type": {
                t: probe.rates(per_type[t]) for t in sorted(per_type, key=lambda t: (t not in probe.TYPES, t))
            },
        }
    return out


def print_summary(summary: dict) -> None:
    def fmt(v):
        return "-" if v is None else f"{v:.2f}"

    print()
    print(f"{'mode':<10} {'type':<26} {'found':>5} {'missed':>6} {'invent':>6} {'prec':>5} {'recall':>6}")
    for mode, s in summary.items():
        for t, r in [*s["per_type"].items(), ("OVERALL", s["overall"])]:
            print(
                f"{mode:<10} {t:<26} {r['found']:>5} {r['missed']:>6} {r['invented']:>6} "
                f"{fmt(r['precision']):>5} {fmt(r['recall']):>6}"
            )
        seconds = ", ".join(f"{f} {v}s" for f, v in s["seconds_per_document"].items())
        print(f"{mode:<10} seconds per document: {seconds or '-'}; mean {s['seconds_mean']}")
        if s["errors"] or s["without_checks"]:
            print(f"{mode:<10} errors {s['errors']}, complex PDFs without checks {s['without_checks'] or 'none'}")


# --- server ---------------------------------------------------------------------------------------------------------


def post_review(url: str, secret: str, pdf: bytes, *, mode: str, subject: str, timeout: float) -> dict:
    """One review through `POST /review_contract`, as Evolus sends it: the PDF in base64 and the email's fields."""
    body = {
        "pdf_base64": base64.b64encode(pdf).decode("ascii"),
        "sender": "visual-trial@example.com",
        "subject": subject,
        "date": datetime.now(UTC).date().isoformat(),
        "mode": mode,
    }
    request = urllib.request.Request(
        url.rstrip("/") + "/review_contract",
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {secret}"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=timeout) as reply:
        return json.loads(reply.read())


def run(doc: dict, pdf: Path, mode: str, args, secret: str) -> dict:
    row = {"file": doc["file"], "mode": mode, "expected_complex": doc["complex"], "checks": 0}
    start = time.perf_counter()
    try:
        response = post_review(
            args.url, secret, pdf.read_bytes(), mode=mode, subject=f"Visual trial: {doc['file']}", timeout=args.timeout
        )
    except urllib.error.HTTPError as error:
        row["error"] = f"HTTP {error.code}: {error.read().decode(errors='replace')[:300]}"
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as error:
        row["error"] = str(error)
    row["seconds"] = round(time.perf_counter() - start, 1)
    if row.get("error"):
        print(f"  {mode:<9} {doc['file']}: ERROR {row['error']}")
        return row
    row["case_id"] = response.get("case_id")
    row["visual"] = response.get("visual")
    row.update(score_response(response, doc))
    total = sum((Counter(c) for c in row["score"].values()), Counter())
    print(
        f"  {mode:<9} {doc['file']}: {row['seconds']}s, route {row['route']}, visual mode {row['visual_mode']}, "
        f"{row['checks']} checks, found {total['found']} missed {total['missed']} invented {total['invented']}"
    )
    return row


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--url", required=True, help="the server, for example http://localhost:8000")
    parser.add_argument("--modes", nargs="+", choices=MODES, default=list(MODES))
    parser.add_argument("--pages-dir", type=Path, default=Path("council/data/vision/pages"))
    parser.add_argument("--ground-truth", type=Path, help="default: ground-truth.json in --pages-dir or its parent")
    parser.add_argument("--timeout", type=float, default=3600, help="seconds for one review")
    parser.add_argument("--output", type=Path, default=Path("results-visual-trial.jsonl"))
    args = parser.parse_args(argv)

    secret = os.environ.get("COUNCIL_SECRET", "")
    if not secret:
        raise SystemExit("COUNCIL_SECRET is not set: export the server's secret")
    # The default paths are from the repo root: from anywhere else, fall back to the repo this file is in.
    pages_dir = args.pages_dir if args.pages_dir.exists() else REPO / args.pages_dir
    if not pages_dir.exists():
        raise SystemExit(f"pages directory not found: {args.pages_dir}")
    documents = probe.load_ground_truth(args.ground_truth or probe.find_ground_truth(pages_dir))

    rows = []
    # Mode by mode: the server keeps one council per mode, so each is set up once and the times compare.
    for mode in args.modes:
        for doc in documents:
            pdf = pages_dir / doc["file"]
            if not pdf.exists():
                print(f"  {doc['file']}: MISSING, skipped")
                continue
            rows.append(run(doc, pdf, mode, args, secret))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with open(args.output, "w") as f:
        f.writelines(json.dumps(row, ensure_ascii=False) + "\n" for row in rows)
    summary = summarize(rows)
    args.output.with_suffix(".summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n")
    print_summary(summary)


if __name__ == "__main__":
    main()
