"""Probe of the vision skill on Gemma 4: does the first agent see signatures, stamps and handwriting on the pages?

Standalone: it uses neither the engine nor the council, only the PDF inspector in visual.py, the skill text and
transformers 5. For each PDF of the ground truth the inspector decides whether the skill is invoked; the control
document (plain text) must stop there. Otherwise the visual pages go to the model as images, before the skill text,
and the JSON it writes is scored against the ground truth, once per visual token budget.

The skill holds only the sections the document's signals call for (visual.skill_text), as in the service; --skill all
loads every section, to see what the short skill costs or saves. Each row records the sections it loaded.

    python review/vision_probe.py --dry-run          # inputs and token counts only, no model weights
    python review/vision_probe.py --budget 560 1120  # on the MI300X
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import math
import re
import sys
import time
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]

MODEL = "google/gemma-4-31B-it"
REVISION = "842da3794eaa0b77d5f08bae87a17459d91ff475"
BUDGETS = (70, 140, 280, 560, 1120)
TYPES = (
    "signature",
    "unsigned_signature_block",
    "initials",
    "missing_initials",
    "stamp",
    "handwritten_correction",
    "handwritten_note",
    "checkbox",
    "table",
    "logo",
)
# These describe something absent: there is nothing to box, so page and type are enough.
PAGE_ONLY = {"unsigned_signature_block", "missing_initials"}
MIN_IOU = 0.3
TASK = (
    "The images above are the pages of the contract that carry pictures or scans, each after its page number. "
    "Inspect them following the instructions and return the JSON object."
)


def load_visual():
    """visual.py without the package __init__, which imports torch and the engine."""
    spec = importlib.util.spec_from_file_location("council_visual", HERE / "visual.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module  # dataclasses look the module up while building the classes
    spec.loader.exec_module(module)
    return module


# --- ground truth ---------------------------------------------------------------------------------------------------


def _first(d: dict, *keys, default=None):
    for k in keys:
        if k in d and d[k] is not None:
            return d[k]
    return default


def _object(o: dict) -> dict:
    box = _first(o, "box_2d", "box", "bbox")
    return {
        "page": int(_first(o, "page", "page_number", default=0)),
        "type": str(_first(o, "type", "label", default="")).strip().lower(),
        "box_2d": [float(v) for v in box] if isinstance(box, (list, tuple)) and len(box) == 4 else None,
    }


def _document(name: str | None, d) -> dict:
    if isinstance(d, list):
        d = {"objects": d}
    name = name or _first(d, "file", "pdf", "filename", "name", "path")
    # "visual": false marks what no one sees on the page (hidden text): the detector's business, not the model's.
    listed = _first(d, "objects", "expected", "ground_truth", "items", default=[])
    objects = [_object(o) for o in listed if o.get("visual", True) is not False]
    complex_ = _first(d, "complex", "expected_complex", "skill_invoked", "invoke_skill")
    if complex_ is None and "control" in d:
        complex_ = not d["control"]
    if complex_ is None:
        complex_ = bool(objects)
    return {"file": Path(str(name)).name, "complex": bool(complex_), "objects": objects}


def load_ground_truth(path: Path) -> list[dict]:
    """The documents of ground-truth.json: a list, a dict with a list under "documents" (or similar), or a dict from
    file name to document. Each document has its file, whether the skill should run and the expected objects."""
    data = json.loads(path.read_text())
    if isinstance(data, dict):
        for key in ("documents", "pdfs", "files", "contracts"):
            if key in data:
                data = data[key]
                break
    if isinstance(data, dict):
        return [_document(name, d) for name, d in data.items() if str(name).lower().endswith(".pdf")]
    return [_document(None, d) for d in data]


def find_ground_truth(pages_dir: Path) -> Path:
    for candidate in (pages_dir / "ground-truth.json", pages_dir.parent / "ground-truth.json"):
        if candidate.exists():
            return candidate
    raise SystemExit(f"ground-truth.json not found in {pages_dir} or {pages_dir.parent}")


# --- parsing and scoring --------------------------------------------------------------------------------------------


def first_json_object(text: str) -> dict | None:
    """The first balanced {...} in the model's text that parses as JSON, code fences and prose around it ignored."""
    text = re.sub(r"```(?:json)?", "", text)
    start = text.find("{")
    while start != -1:
        depth, in_string, escaped = 0, False, False
        for i in range(start, len(text)):
            c = text[i]
            if in_string:
                if escaped:
                    escaped = False
                elif c == "\\":
                    escaped = True
                elif c == '"':
                    in_string = False
            elif c == '"':
                in_string = True
            elif c == "{":
                depth += 1
            elif c == "}":
                depth -= 1
                if depth == 0:
                    try:
                        value = json.loads(text[start : i + 1])
                    except json.JSONDecodeError:
                        break
                    if isinstance(value, dict):
                        return value
                    break
        start = text.find("{", start + 1)
    return None


def predicted_objects(parsed: dict | None) -> list[dict]:
    out = []
    for o in (parsed or {}).get("objects") or []:
        if not isinstance(o, dict):
            continue
        try:
            out.append(_object(o))
        except (TypeError, ValueError):
            continue  # an unreadable page or box: the object cannot be placed, so it is dropped
    return out


def iou(a: list[float], b: list[float]) -> float:
    ay0, ax0, ay1, ax1 = min(a[0], a[2]), min(a[1], a[3]), max(a[0], a[2]), max(a[1], a[3])
    by0, bx0, by1, bx1 = min(b[0], b[2]), min(b[1], b[3]), max(b[0], b[2]), max(b[1], b[3])
    h, w = min(ay1, by1) - max(ay0, by0), min(ax1, bx1) - max(ax0, bx0)
    if h <= 0 or w <= 0:
        return 0.0
    inter = h * w
    union = (ay1 - ay0) * (ax1 - ax0) + (by1 - by0) * (bx1 - bx0) - inter
    return inter / union if union > 0 else 0.0


def _matches(pred: dict, truth: dict) -> float | None:
    """How well a prediction fits an expected object (higher is better), None when it does not match."""
    if pred["page"] != truth["page"] or pred["type"] != truth["type"]:
        return None
    if truth["type"] in PAGE_ONLY or pred["box_2d"] is None or truth["box_2d"] is None:
        return 0.0
    overlap = iou(pred["box_2d"], truth["box_2d"])
    return overlap if overlap >= MIN_IOU else None


def score(predicted: list[dict], expected: list[dict]) -> dict[str, Counter]:
    """Per type: found, missed and invented. Greedy one-to-one matching, best overlap first."""
    pairs = []
    for i, p in enumerate(predicted):
        for j, t in enumerate(expected):
            fit = _matches(p, t)
            if fit is not None:
                pairs.append((fit, i, j))
    used_p, used_t = set(), set()
    for _, i, j in sorted(pairs, reverse=True):
        if i not in used_p and j not in used_t:
            used_p.add(i)
            used_t.add(j)
    counts: dict[str, Counter] = {}
    for j, t in enumerate(expected):
        counts.setdefault(t["type"], Counter())["found" if j in used_t else "missed"] += 1
    for i, p in enumerate(predicted):
        if i not in used_p:
            counts.setdefault(p["type"] or "?", Counter())["invented"] += 1
    return counts


def rates(c: Counter) -> dict:
    found, missed, invented = c["found"], c["missed"], c["invented"]
    return {
        "found": found,
        "missed": missed,
        "invented": invented,
        "precision": round(found / (found + invented), 3) if found + invented else None,
        "recall": round(found / (found + missed), 3) if found + missed else None,
    }


# --- model ----------------------------------------------------------------------------------------------------------


def render_side(budget: int, max_side: int) -> int:
    """The longest side of the render: at least what the budget can use, so the processor does not upscale a small
    render. 9 patches of 16 px per soft token; 1.5 covers the aspect ratio of A4 and Letter."""
    if max_side:
        return max_side
    return max(1536, math.ceil(math.sqrt(budget * 9 * 16 * 16 * 1.5)))


def build_messages(images, pages: list[int], skill: str) -> list[dict]:
    """One user message: every page image first, each after its page number, then the skill and the task."""
    content = []
    for number, image in zip(pages, images):
        content.append({"type": "text", "text": f"Page {number}"})
        content.append({"type": "image", "image": image})
    content.append({"type": "text", "text": f"{skill}\n\n{TASK}"})
    return [{"role": "user", "content": content}]


def image_token_runs(input_ids: list[int], image_token_id: int) -> list[int]:
    """The length of each run of image soft tokens: one per image, in order."""
    runs, n = [], 0
    for t in input_ids:
        if t == image_token_id:
            n += 1
        elif n:
            runs.append(n)
            n = 0
    if n:
        runs.append(n)
    return runs


def load_model(name: str, revision: str):
    import torch
    import transformers

    cls = getattr(transformers, "AutoModelForMultimodalLM", None) or transformers.AutoModelForImageTextToText
    # Loaded like the engine does, without device_map: in transformers 5 that needs accelerate, which the venv may lack.
    model = cls.from_pretrained(name, revision=revision, dtype=torch.bfloat16)
    model.to("cuda" if torch.cuda.is_available() else "cpu").eval()
    return model


def run_document(doc, pdf: Path, budget: int, args, visual, processor, model) -> dict:
    row = {"file": doc["file"], "budget": budget, "expected_complex": doc["complex"]}
    data = pdf.read_bytes()
    inspection = visual.inspect_pdf(data)
    row["complex"] = inspection.complex
    row["visual_pages"] = inspection.visual_pages
    row["pages"] = len(inspection.pages)
    row["signals"] = sorted({s.kind for s in inspection.signals})
    if not inspection.complex:
        print(f"  {doc['file']}: skill not invoked")
        row["skill_invoked"] = False
        row["score"] = {t: dict(c) for t, c in score([], doc["objects"]).items()}
        return row
    row["skill_invoked"] = True
    # The sections the signals call for, as the service loads them; "all" for the whole skill.
    sections = list(visual.SECTIONS) if args.skill == "all" else visual.skill_sections(inspection.signals)
    skill = visual.skill_text(sections)
    row["skill_sections"] = sections or list(visual.SECTIONS)  # skill_text loads all when nothing is called for
    # The inspector sends only the visual pages; "all" measures what the model would see with every page.
    sent = list(range(1, len(inspection.pages) + 1)) if args.pages == "all" else inspection.visual_pages
    row["sent_pages"] = sent
    row["unreachable"] = sum(1 for o in doc["objects"] if o["page"] not in sent)
    side = render_side(budget, args.max_side)
    images = visual.render_pages(data, sent, max_side=side)
    row["render_sizes"] = [list(im.size) for im in images]
    inputs = processor.apply_chat_template(
        build_messages(images, sent, skill),
        tokenize=True,
        return_dict=True,
        return_tensors="pt",
        add_generation_prompt=True,
        processor_kwargs={"images_kwargs": {"max_soft_tokens": budget}},
    )
    ids = inputs["input_ids"][0].tolist()
    row["input_tokens"] = len(ids)
    row["image_tokens_per_page"] = image_token_runs(ids, processor.image_token_id)
    # A transformers that ignores max_soft_tokens would give its default budget every time, and the comparison is void.
    runs = row["image_tokens_per_page"]
    if len(runs) != len(sent) or not all(budget // 2 < n <= budget for n in runs):
        raise SystemExit(f"{doc['file']}: image tokens per page {runs} do not follow budget {budget} for pages {sent}")
    print(
        f"  {doc['file']}: pages {sent}, render {side}px, input {len(ids)} tokens, "
        f"image tokens per page {row['image_tokens_per_page']}, expected objects on pages not sent {row['unreachable']}, "
        f"skill sections {', '.join(row['skill_sections'])}"
    )
    if args.dry_run:
        return row
    import torch

    inputs = inputs.to(model.device)
    start = time.perf_counter()
    with torch.inference_mode():
        out = model.generate(**inputs, max_new_tokens=args.max_new_tokens, do_sample=False)
    row["seconds"] = round(time.perf_counter() - start, 2)
    generated = out[0][len(ids) :]
    row["generated_tokens"] = len(generated)
    row["raw"] = processor.decode(generated, skip_special_tokens=True)
    parsed = first_json_object(row["raw"])
    row["parsed"] = parsed
    row["parse_ok"] = parsed is not None
    row["score"] = {t: dict(c) for t, c in score(predicted_objects(parsed), doc["objects"]).items()}
    total = sum((Counter(c) for c in row["score"].values()), Counter())
    print(
        f"    {row['seconds']}s, {row['generated_tokens']} tokens generated, json {'ok' if parsed else 'NOT FOUND'}, "
        f"found {total['found']} missed {total['missed']} invented {total['invented']}"
    )
    return row


def summarize(rows: list[dict]) -> dict:
    per_type: dict[str, Counter] = {}
    for row in rows:
        for t, c in (row.get("score") or {}).items():
            per_type.setdefault(t, Counter()).update(c)
    overall = sum(per_type.values(), Counter())
    controls = [r for r in rows if not r["expected_complex"]]
    timed = [r["seconds"] for r in rows if "seconds" in r]
    return {
        "documents": len(rows),
        "skill_invoked": sum(1 for r in rows if r["skill_invoked"]),
        "inspector_agrees": sum(1 for r in rows if r["complex"] == r["expected_complex"]),
        "control_skipped": all(not r["skill_invoked"] for r in controls) if controls else None,
        "json_ok": sum(1 for r in rows if r.get("parse_ok")),
        "unreachable": sum(r.get("unreachable", 0) for r in rows),
        "seconds_total": round(sum(timed), 1) if timed else None,
        "image_tokens_per_page": sorted({n for r in rows for n in r.get("image_tokens_per_page", [])}),
        "overall": rates(overall),
        "per_type": {t: rates(per_type[t]) for t in sorted(per_type, key=lambda t: (t not in TYPES, t))},
    }


def print_table(summary: dict) -> None:
    print()
    print(f"{'budget':>6} {'type':<26} {'found':>5} {'missed':>6} {'invent':>6} {'prec':>5} {'recall':>6}")

    def fmt(v):
        return "-" if v is None else f"{v:.2f}"

    for budget, s in summary["budgets"].items():
        for t, r in [*s["per_type"].items(), ("OVERALL", s["overall"])]:
            print(
                f"{budget:>6} {t:<26} {r['found']:>5} {r['missed']:>6} {r['invented']:>6} "
                f"{fmt(r['precision']):>5} {fmt(r['recall']):>6}"
            )
        print(
            f"{budget:>6} control skipped: {s['control_skipped']}, json ok {s['json_ok']}/{s['skill_invoked']}, "
            f"image tokens per page {s['image_tokens_per_page']}, objects on pages not sent {s['unreachable']}, "
            f"seconds {s['seconds_total']}"
        )


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--model", default=MODEL)
    parser.add_argument("--revision", default=REVISION)
    parser.add_argument("--pages-dir", type=Path, default=Path("council/data/vision/pages"))
    parser.add_argument("--ground-truth", type=Path, help="default: ground-truth.json in --pages-dir or its parent")
    parser.add_argument("--budget", type=int, nargs="+", choices=BUDGETS, default=[560, 1120])
    parser.add_argument("--pages", choices=["visual", "all"], default="visual", help="pages of a complex PDF to send")
    parser.add_argument(
        "--skill",
        choices=["signals", "all"],
        default="signals",
        help="skill sections: those the signals call for, or all",
    )
    parser.add_argument("--max-new-tokens", type=int, default=1500)
    parser.add_argument("--max-side", type=int, default=0, help="longest side of the render; 0 = from the budget")
    parser.add_argument("--output", type=Path, default=Path("results-vision"))
    parser.add_argument("--dry-run", action="store_true", help="build the inputs and count tokens, no model weights")
    args = parser.parse_args(argv)

    # The default paths are from the repo root: from anywhere else, fall back to the repo this file is in.
    pages_dir = args.pages_dir if args.pages_dir.exists() else REPO / args.pages_dir
    if not pages_dir.exists():
        raise SystemExit(f"pages directory not found: {args.pages_dir}")
    documents = load_ground_truth(args.ground_truth or find_ground_truth(pages_dir))
    visual = load_visual()

    from transformers import AutoProcessor

    processor = AutoProcessor.from_pretrained(args.model, revision=args.revision)
    model = None if args.dry_run else load_model(args.model, args.revision)

    args.output.mkdir(parents=True, exist_ok=True)
    summary = {
        "model": args.model,
        "revision": args.revision,
        "pages": args.pages,
        "skill": args.skill,
        "dry_run": args.dry_run,
        "budgets": {},
    }
    for budget in args.budget:
        print(f"budget {budget}")
        rows = []
        for doc in documents:
            pdf = pages_dir / doc["file"]
            if not pdf.exists():
                print(f"  {doc['file']}: MISSING, skipped")
                continue
            rows.append(run_document(doc, pdf, budget, args, visual, processor, model))
        with open(args.output / f"vision-{budget}.jsonl", "w") as f:
            f.writelines(json.dumps(row, ensure_ascii=False) + "\n" for row in rows)
        summary["budgets"][str(budget)] = summarize(rows)
    (args.output / "summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n")
    print_table(summary)


if __name__ == "__main__":
    main()
