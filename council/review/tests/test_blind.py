"""The blind manual check, without a model."""

import csv
import json

from review.blind import count, prepare


def review(contract, recommendation):
    return {
        "benchmark": "demo",
        "contract": contract,
        "verdict": {
            "data": {
                "flag": {"Exclusivity": True, "Non-Compete": False},
                "details": [{"category": "Exclusivity", "quote": "solo dal Fornitore", "rationale": "binding"}],
                "recommendation": recommendation,
                "rationale": "because of the exclusivity",
                "objections": [],
            }
        },
        "dissents": [{"category": "Non-Compete", "role": "risk", "type": "major"}],
        "tokens_generated": 1234,
        "latent_positions": 30,
    }


def test_sheets_without_mode_and_counts_with_the_key(tmp_path):
    for configuration, recommendation in (("text", "negotiate"), ("telepathy", "sign")):
        rows = [review(c, recommendation) for c in ("one", "two")]
        (tmp_path / f"demo-dev-{configuration}.jsonl").write_text("\n".join(map(json.dumps, rows)))
    assert prepare(tmp_path, tmp_path / "blind") == 4
    sheets = sorted((tmp_path / "blind" / "for-the-checker").glob("verdict-*.md"))
    texts = [f.read_text() for f in sheets]
    assert len(sheets) == 4 and all("Exclusivity" in t and "Non-Compete" in t for t in texts)
    assert not any(word in t.lower() for t in texts for word in ("telepathy", "1234", "latent", "token"))
    key = json.loads((tmp_path / "blind" / "key.json").read_text())["verdicts"]
    sheet = tmp_path / "blind" / "for-the-checker" / "sheet.csv"
    rows = list(csv.DictReader(sheet.open()))
    for r in rows:  # the checker agrees only with the "negotiate" recommendations
        r |= {
            "right_recommendation": "yes"
            if "negotiate" in (tmp_path / "blind" / "for-the-checker" / f"{r['verdict']}.md").read_text()
            else "no"
        }
    with sheet.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)
    table = count(sheet, tmp_path / "blind" / "key.json")
    assert "| Council in text | 2/2 | 0/0 | 0/0 |" in table and "| Council in telepathy | 0/2 |" in table
    assert {v["configuration"] for v in key.values()} == {"text", "telepathy"}
