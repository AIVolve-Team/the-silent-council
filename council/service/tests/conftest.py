import copy
import json
from pathlib import Path

import pytest

from reviewer.manager import Reviewer

EXAMPLE = json.loads((Path(__file__).parents[2] / "review" / "page" / "example-review.json").read_text())
SECRET = "test-secret-at-least-thirty-two-characters-long"
LINK = "https://council.example.org/verdict/{id}?key={key}"
CONTRACT = "CONTRATTO DI FORNITURA\n\nArt. 1 – Oggetto\nIl Fornitore fornisce componenti meccanici al Cliente.\n"


def pdf_with_text(text: str) -> bytes:
    """A one-page PDF with one line of text, written by hand: enough for pypdf to extract it."""
    stream = f"BT /F1 12 Tf 72 720 Td ({text}) Tj ET".encode()
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        (
            b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R "
            b"/Resources << /Font << /F1 5 0 R >> >> >>"
        ),
        b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    pdf, offsets = b"%PDF-1.4\n", []
    for i, obj in enumerate(objects, 1):
        offsets.append(len(pdf))
        pdf += f"{i} 0 obj\n".encode() + obj + b"\nendobj\n"
    start = len(pdf)
    pdf += f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode()
    pdf += b"".join(f"{p:010d} 00000 n \n".encode() for p in offsets)
    pdf += f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{start}\n%%EOF\n".encode()
    return pdf


class FakeCouncil:
    """Returns the page's example review and counts the calls."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, str, str, str]] = []
        self.stopped = None
        self.failure: Exception | None = None

    def __call__(self, case_id: str, text: str, mode: str, benchmark: str = "demo") -> dict:
        if self.failure:
            raise self.failure
        self.calls.append((case_id, text, mode, benchmark))
        review = copy.deepcopy(EXAMPLE) | {"contract": case_id, "mode": mode}
        if self.stopped:
            review |= {"stopped": self.stopped, "verdict": None, "dissents": []}
        return review


@pytest.fixture
def council():
    return FakeCouncil()


@pytest.fixture
def reviewer(council, tmp_path):
    return Reviewer(council, tmp_path / "cases", secret=SECRET, link=LINK)


# A live review catalog like the one of review.live, with a CUAD contract and its answers.
CUAD = "TRANSPHORM,INC_02_14_2020-EX-10.12(1)-JOINT VENTURE AGREEMENT"
CATALOG = {
    f"cuad:{CUAD}": {
        "benchmark": "cuad",
        "contract": CUAD,
        "subset": "dev",
        "text": "JOINT VENTURE AGREEMENT\n1. The parties agree.",
        "title": "TRANSPHORM, INC: joint venture agreement",
        "experts": {"Cap On Liability": {"should_flag": True, "evidence": ["liability shall not exceed"]}},
        "source": {
            "name": "CUAD",
            "link": "https://github.com/TheAtticusProject/cuad",
            "who": {"en": "the CUAD experts"},
        },
    }
}


@pytest.fixture
def live(council, tmp_path):
    return Reviewer(council, tmp_path / "cases", secret=SECRET, link=LINK, catalog=CATALOG)


def email(**other) -> dict:
    return {"sender": "supplier@example.org", "subject": "Contratto di fornitura", "date": "2026-10-09"} | other
