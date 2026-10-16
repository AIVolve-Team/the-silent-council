"""Prepare the council's measurement set.

Downloads CUAD, ContractNLI and CLAUDETTE's Italian ToS from the official sources, counts the Qwen3 tokens of each
contract, draws the sample with a fixed seed among the contracts under the token cap and writes the correct answers:
for each (contract, category) pair, whether it should be flagged yes or no, with the pieces of text that prove it.
The CUAD replication goes in separate files: the test ones are pinned by hash in the pre-registration.

Decisions: "Benchmarks and trial contracts", "Council setup".
"""

import argparse
import csv
import hashlib
import json
import random
import re
import statistics
import tarfile
import urllib.request
import zipfile
from pathlib import Path

from categories import CLAUDETTE_CATEGORIES, CONTRACTNLI_HYPOTHESES, CUAD_CATEGORIES

HERE = Path(__file__).resolve().parent
CACHE = HERE / "cache"

SEED = 60
TOKEN_CAP = 24_000
N_DEV = 5
N_TEST = 20

# Subsets of the measurement set, and the split name of a dataset without an official split (CLAUDETTE).
DEV = "dev"
TEST = "test"
REPLICATION = "replication"
ALL = "all"

# name: (file in the cache, url, sha256 of the file)
SOURCES = {
    "cuad": (
        "cuad.zip",
        "https://github.com/TheAtticusProject/cuad/raw/67faa0e6023b04fcaae6cc09497ab00e5d63a2a2/data.zip",
        "f8161d18bea4e9c05e78fa6dda61c19c846fb8087ea969c172753bc2f45b999a",
    ),
    "contractnli": (
        "contractnli.zip",
        "https://stanfordnlp.github.io/contract-nli/resources/contract-nli.zip",
        "e03fc77bbf8b53e2976a250e81d8a294bc3d5e5fb014521e477dee9340d6287b",
    ),
    # The GitHub archive has no stable hash: the content of the Italian files is checked instead (CLAUDETTE_SHA256).
    "claudette": (
        "claudette.tar.gz",
        (
            "https://codeload.github.com/lt-nlp-lab-unibo/Multilingual-Unfair-Clause-Detection/tar.gz/"
            "04d9878bfca0e1e17e7dd1cf7bd17fc4ce5fcd12"
        ),
        None,
    ),
    "tokenizer": (
        "qwen3-tokenizer.json",
        "https://huggingface.co/Qwen/Qwen3-14B/resolve/40c069824f4251a91eefaf281ebe4c544efd3e18/tokenizer.json",
        "aeb13307a71acd8fe81861d94ad54ab689df773318809eed3cbe794b4492dae4",
    ),
}
CLAUDETTE_SHA256 = "21e62635064832320843e6a067fb38a55ec47f3f935c406fe2b4c613a774a173"

# Two annotation errors in the Italian ToS, fixed as in the English version of the same ToS.
# (ToS, original text, fixed text): the original text must appear exactly once.
CLAUDETTE_FIXES = [
    ("Weebly", "le vostre informazioni finanziarie.</ter2>", "le vostre informazioni finanziarie.</ch2>"),
    ("Yelp", "legalmente perseguibile.</ter3></ch3>", "legalmente perseguibile.</ter3></ch2>"),
]

CLAUDETTE_TAG = re.compile(r"<(/?)(" + "|".join(CLAUDETTE_CATEGORIES) + r")([123])>")
IGNORED_TAGS = re.compile(r"</?countryM>")


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def download(name: str) -> Path:
    file, url, expected = SOURCES[name]
    path = CACHE / file
    if not path.exists():
        CACHE.mkdir(exist_ok=True)
        print(f"Downloading {name} from {url}")
        with urllib.request.urlopen(url) as response:
            path.write_bytes(response.read())
    if expected is not None and sha256(path.read_bytes()) != expected:
        raise SystemExit(
            f"{path.name}: the hash does not match the pinned one. The source has changed: "
            "check what changed before updating the hash in SOURCES."
        )
    return path


# --- CUAD -----------------------------------------------------------------------------------------------


def cuad_answers(qas: list[dict]) -> dict[str, list[str]]:
    """For each of the 19 categories, the annotated pieces of text (an empty list if the category is absent)."""
    answers = {category: [] for category in CUAD_CATEGORIES}
    for qa in qas:
        category = qa["id"].rsplit("__", 1)[1]
        if category in answers:
            assert not answers[category], f"repeated category: {qa['id']}"
            for answer in qa["answers"]:
                if answer["text"] not in answers[category]:
                    answers[category].append(answer["text"])
    return answers


def read_cuad(archive: Path) -> dict[str, list[dict]]:
    """Texts and answers from CUADv1.json, one question per category. The official split files are only used to
    know which split each contract is in: in train_separate_questions.json the ids have a "_<n>" suffix for each
    answer and must not be read as categories."""
    with zipfile.ZipFile(archive) as z:
        everything = {d["title"]: d for d in json.loads(z.read("CUADv1.json"))["data"]}
        split = {
            "train": [d["title"] for d in json.loads(z.read("train_separate_questions.json"))["data"]],
            "test": [d["title"] for d in json.loads(z.read("test.json"))["data"]],
        }
    assert sorted(split["train"] + split["test"]) == sorted(everything), (
        "the CUAD split does not cover the 510 contracts"
    )
    contracts = {}
    for subset, titles in split.items():
        contracts[subset] = []
        for title in titles:
            (paragraph,) = everything[title]["paragraphs"]
            contracts[subset].append(
                {"id": title, "text": paragraph["context"], "answers": cuad_answers(paragraph["qas"])}
            )
    return contracts


# --- ContractNLI ----------------------------------------------------------------------------------------


def contractnli_answers(document: dict) -> dict[str, tuple[str, list[str]]]:
    """For each hypothesis, the original label and the pieces of text of the evidence."""
    (annotations,) = document["annotation_sets"]
    answers = {}
    for hypothesis, annotation in annotations["annotations"].items():
        pieces = [document["text"][start:end] for start, end in (document["spans"][i] for i in annotation["spans"])]
        answers[hypothesis] = (annotation["choice"], pieces)
    return answers


def read_contractnli(archive: Path) -> dict[str, list[dict]]:
    contracts = {}
    with zipfile.ZipFile(archive) as z:
        for subset in ("train", "test"):
            data = json.loads(z.read(f"contract-nli/{subset}.json"))
            assert {k: v["short_description"] for k, v in data["labels"].items()} == {
                k: v[0] for k, v in CONTRACTNLI_HYPOTHESES.items()
            }, "the ContractNLI hypotheses do not match categories.py"
            contracts[subset] = [
                {"id": d["file_name"], "text": d["text"], "answers": contractnli_answers(d)} for d in data["documents"]
            ]
    return contracts


# --- CLAUDETTE ------------------------------------------------------------------------------------------


def extract_clauses(xml: str) -> list[tuple[str, int, str]]:
    """The clauses marked in a CLAUDETTE ToS, as (category, grade, text without tags).

    Category tags can nest (a sentence with two categories). Text containing "<a>" without a grade is HTML quoted
    in the ToS, not a tag, and stays in the text.
    """
    xml = IGNORED_TAGS.sub("", xml)
    plain, opened, clauses, last = [], [], [], 0
    length = 0
    for tag in CLAUDETTE_TAG.finditer(xml):
        piece = xml[last : tag.start()]
        plain.append(piece)
        length += len(piece)
        last = tag.end()
        closing, category, grade = tag.group(1) == "/", tag.group(2), int(tag.group(3))
        if not closing:
            opened.append((category, grade, length))
            continue
        for i in range(len(opened) - 1, -1, -1):
            if opened[i][:2] == (category, grade):
                _, _, start = opened.pop(i)
                clauses.append((category, grade, start, length))
                break
        else:
            raise ValueError(f"closing tag without an opening one: {tag.group(0)}")
    if opened:
        raise ValueError(f"unclosed tags: {opened}")
    plain.append(xml[last:])
    text = "".join(plain)
    return [(category, grade, text[start:end].strip()) for category, grade, start, end in clauses]


def claudette_answers(xml: str) -> dict[str, list[tuple[int, str]]]:
    answers = {category: [] for category in CLAUDETTE_CATEGORIES}
    for category, grade, text in extract_clauses(xml):
        answers[category].append((grade, text))
    return answers


def read_claudette(archive: Path) -> dict[str, list[dict]]:
    with tarfile.open(archive) as tar:
        files = {
            Path(m.name).relative_to(Path(m.name).parts[0]).as_posix(): tar.extractfile(m).read()
            for m in tar.getmembers()
            if m.isfile() and re.search(r"corpus/original_(xml|text)/it/[^/]+\.(xml|txt)$", m.name)
        }
    content = sha256(b"".join(name.encode() + b"\0" + data for name, data in sorted(files.items())))
    if content != CLAUDETTE_SHA256:
        raise SystemExit(
            f"CLAUDETTE: the content of the Italian files has hash {content}, expected {CLAUDETTE_SHA256}."
        )
    contracts = []
    for name in sorted(n for n in files if n.endswith(".xml")):
        tos = Path(name).stem
        text = files[f"corpus/original_text/it/{tos}.txt"].decode("utf-8")
        xml = files[name].decode("utf-8")
        for to_fix, original, fixed in CLAUDETTE_FIXES:
            if to_fix == tos:
                if xml.count(original) != 1:
                    raise SystemExit(f"CLAUDETTE {tos}: the fix does not find the expected text.")
                xml = xml.replace(original, fixed)
        contracts.append({"id": tos, "text": text, "answers": claudette_answers(xml)})
    return {ALL: contracts}


# --- Sample and correct answers -------------------------------------------------------------------------


def draw_sample(ids: list[str], n: int, key: str) -> list[str]:
    """n ids drawn with a fixed seed. The seed also depends on benchmark and subset, so the draws are independent
    and reproducible (a string seed does not depend on PYTHONHASHSEED)."""
    if len(ids) < n:
        raise SystemExit(f"{key}: only {len(ids)} contracts under the token cap, {n} are needed. See --token-cap.")
    return random.Random(f"{SEED}-{key}").sample(sorted(ids), n)


def replication(under_cap: list[str], test: list[str]) -> list[str]:
    """The CUAD replication: all test contracts under the cap that the test did not use, with no draw."""
    return sorted(set(under_cap) - set(test))


def cuad_rows(contract: dict, subset: str) -> list[dict]:
    return [
        {
            "benchmark": "cuad",
            "subset": subset,
            "contract": contract["id"],
            "category": category,
            "role": role,
            "should_flag": bool(contract["answers"][category]),
            "evidence": contract["answers"][category],
        }
        for category, role in CUAD_CATEGORIES.items()
    ]


def contractnli_rows(contract: dict, subset: str) -> list[dict]:
    rows = []
    for hypothesis, (description, role) in CONTRACTNLI_HYPOTHESES.items():
        label, pieces = contract["answers"][hypothesis]
        rows.append(
            {
                "benchmark": "contractnli",
                "subset": subset,
                "contract": contract["id"],
                "category": description,
                "hypothesis": hypothesis,
                "role": role,
                "should_flag": label == "Contradiction",
                "original_label": label,
                "evidence": pieces,
            }
        )
    return rows


def claudette_rows(contract: dict, subset: str) -> list[dict]:
    rows = []
    for tag, (name, role) in CLAUDETTE_CATEGORIES.items():
        clauses = contract["answers"][tag]
        grades = [grade for grade, _ in clauses]
        rows.append(
            {
                "benchmark": "claudette",
                "subset": subset,
                "contract": contract["id"],
                "category": name,
                "tag": tag,
                "role": role,
                "should_flag": any(grade >= 2 for grade in grades),
                "should_flag_grade_3": 3 in grades,
                "max_grade": max(grades, default=None),
                "evidence": [text for grade, text in clauses if grade >= 2],
            }
        )
    return rows


def statistics_of(tokens: list[int], token_cap: int) -> dict:
    ordered = sorted(tokens)
    return {
        "total": len(tokens),
        "under_cap": sum(t <= token_cap for t in tokens),
        "median": int(statistics.median(ordered)),
        "p90": ordered[int(0.9 * (len(ordered) - 1))],
        "max": ordered[-1],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--token-cap", type=int, default=TOKEN_CAP, help="cap in Qwen3 tokens (agreed fallback: 12000)")
    parser.add_argument("--output", type=Path, default=HERE / "measurement-set")
    args = parser.parse_args()

    from tokenizers import Tokenizer

    tokenizer = Tokenizer.from_file(str(download("tokenizer")))
    benchmarks = {
        "cuad": (read_cuad(download("cuad")), cuad_rows),
        "contractnli": (read_contractnli(download("contractnli")), contractnli_rows),
        "claudette": (read_claudette(download("claudette")), claudette_rows),
    }

    args.output.mkdir(parents=True, exist_ok=True)
    counts, sample, rows, token_csv = {"token_cap": args.token_cap}, {"seed": SEED, "token_cap": args.token_cap}, [], []
    replication_sample, replication_rows = {"token_cap": args.token_cap}, []
    for name, (splits, rows_of) in benchmarks.items():
        counts[name] = {}
        under = {}
        for split, contracts in splits.items():
            encodings = tokenizer.encode_batch([c["text"] for c in contracts], add_special_tokens=False)
            tokens = [len(encoding.ids) for encoding in encodings]
            counts[name][split] = statistics_of(tokens, args.token_cap)
            under[split] = [c["id"] for c, t in zip(contracts, tokens) if t <= args.token_cap]
            token_csv += [(name, split, c["id"], t) for c, t in zip(contracts, tokens)]
        if name == "claudette":
            test = draw_sample(under[ALL], N_TEST, f"{name}-test")
            dev = sorted(set(under[ALL]) - set(test))
            origin = {DEV: ALL, TEST: ALL}
        else:
            # The seed keys keep the original Italian subset name ("sviluppo"): changing it would change the draw.
            dev = draw_sample(under["train"], N_DEV, f"{name}-sviluppo")
            test = draw_sample(under["test"], N_TEST, f"{name}-test")
            origin = {DEV: "train", TEST: "test"}
        sample[name] = {DEV: dev, TEST: test}
        by_id = {c["id"]: c for contracts in splits.values() for c in contracts}
        for subset in (DEV, TEST):
            assert all(i in {c["id"] for c in splits[origin[subset]]} for i in sample[name][subset])
            new = [row for i in sample[name][subset] for row in rows_of(by_id[i], subset)]
            if not any(row["should_flag"] for row in new):
                raise SystemExit(f"{name} {subset}: no pair to flag, the answers are being read wrongly.")
            rows += new
        if name == "cuad":
            replication_sample[name] = {REPLICATION: replication(under["test"], test)}
            replication_rows += [
                row for i in replication_sample[name][REPLICATION] for row in rows_of(by_id[i], REPLICATION)
            ]

    (args.output / "counts.json").write_text(json.dumps(counts, indent=2, ensure_ascii=False) + "\n")
    (args.output / "sample.json").write_text(json.dumps(sample, indent=2, ensure_ascii=False) + "\n")
    with (args.output / "correct-answers.jsonl").open("w") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    (args.output / "sample-replication.json").write_text(
        json.dumps(replication_sample, indent=2, ensure_ascii=False) + "\n"
    )
    with (args.output / "correct-answers-replication.jsonl").open("w") as f:
        for row in replication_rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    with (args.output / "tokens-per-contract.csv").open("w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["benchmark", "original_split", "contract", "qwen3_tokens"])
        writer.writerows(token_csv)

    for name in benchmarks:
        detail = ", ".join(f"{split} {s['under_cap']}/{s['total']}" for split, s in counts[name].items())
        positives = sum(r["should_flag"] for r in rows if r["benchmark"] == name and r["subset"] == TEST)
        pairs = sum(1 for r in rows if r["benchmark"] == name and r["subset"] == TEST)
        print(f"{name}: under the cap {detail}; test {pairs} pairs, {positives} to flag")
    positives = sum(r["should_flag"] for r in replication_rows)
    print(
        f"cuad replication: {len(replication_sample['cuad'][REPLICATION])} contracts, "
        f"{len(replication_rows)} pairs, {positives} to flag"
    )
    print(f"Written to {args.output}")


if __name__ == "__main__":
    main()
