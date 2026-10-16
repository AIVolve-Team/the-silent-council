"""The manager of the council's two tools for Evolus: the same for MCP and for HTTP.

    review_contract(contract, sender, subject, date, mode) → recommendation, dissents, seal, link, notice
    record_choices(case id, choices, who) → who is right on each dissent, in the case's log
    live_review(contract key, mode) → the verdict view, for the judges' live reviews

They hold for both transports, as for the Help Desk:
- one review at a time, because there is one GPU;
- the same email twice is the same case, and the council does not run again: it is Evolus retrying;
- without an intact seal there is no verdict, and the notice asks for a person;
- the contract's text is not saved: the case keeps the review, view, page and choices.

The judges' live reviews do not wait: if the council is reviewing, they answer "busy" (409) right away.
"""

from __future__ import annotations

import hashlib
import hmac
import io
import json
import re
import threading
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

from review import BENCHMARK
from review.live import listing as live_listing
from review.view import page, view

MODES = ("telepathy", "text")
MAX_PDF = 10 * 2**20
MAX_CONTRACT = 200_000  # characters: the longest of the CUAD sample has about 100,000
MAX_TEXT = 1000
CASE_ID = re.compile(r"council-[0-9a-f]{12}")
CHOICES = ("expert", "verdict")  # the two buttons of the verdict page
# The notice is an email for an Italian business, in Italian like the client's verdict page.
RECOMMENDATION_IT = {"sign": "firmare", "negotiate": "negoziare", "do not sign": "non firmare"}
ROLE_IT = {"legal": "Legale", "finance": "Finanza", "risk": "Rischio"}


class Rejected(ValueError):
    """The request is not valid: 400 in HTTP, a tool error in MCP. The model has not been touched."""


class Busy(Exception):
    """A live review while the council is already reviewing: 409, try again shortly."""


def short_text(name: str, value, *, empty: bool = False) -> str:
    if not isinstance(value, str) or len(value) > MAX_TEXT or (not empty and not value.strip()):
        raise Rejected(f"{name}: a text of at most {MAX_TEXT} characters is required")
    return value.strip()


def pdf_text(pdf: bytes) -> str:
    """The text of a contract in PDF. A PDF made only of images has no text: it needs OCR, which is not available."""
    if not isinstance(pdf, bytes) or not pdf.startswith(b"%PDF-") or len(pdf) > MAX_PDF:
        raise Rejected(f"contract: a PDF of at most {MAX_PDF // 2**20} MB is required")
    from pypdf import PdfReader
    from pypdf.errors import PdfReadError

    try:
        pages = PdfReader(io.BytesIO(pdf)).pages
        text = "\n".join(p.extract_text() or "" for p in pages)
    except (PdfReadError, ValueError) as error:
        raise Rejected("contract: the PDF cannot be read") from error
    if not text.strip():
        raise Rejected("contract: the PDF has no text (is it a scan?)")
    return text


def case_key(secret: str, case_id: str) -> str:
    """The key of a case's personal link: whoever has the link opens the page and sends the choices of that case,
    without knowing the server's secret."""
    return hmac.new(secret.encode(), case_id.encode(), hashlib.sha256).hexdigest()[:32]


def notice(v: dict, link: str) -> dict:
    """The email for the person, in Italian like the page: the service writes it and Evolus sends it as is."""
    title = v["title"]
    if not v["seal"]["intact"] or v["recommendation"] is None:
        return {
            "subject": f"[Consiglio] {title}: serve una persona",
            "text": "\n".join(
                [
                    f"Il Consiglio non ha dato un verdetto su «{title}».",
                    "La comunicazione fra gli esperti non ha superato il controllo, oppure il verdetto non è valido.",
                    "Il contratto va rivisto da una persona.",
                    f"Dettagli: {link}",
                ]
            ),
        }
    recommendation = RECOMMENDATION_IT.get(v["recommendation"]["value"], v["recommendation"]["value"])
    flagged = [r["name_it"] for r in v["rows"] if r["flag"]]
    highlighted = [r for r in v["rows"] if r["dissent"] and r["dissent"]["highlighted"]]
    lines = [
        f"Il Consiglio ha rivisto «{title}». Raccomandazione: {recommendation}.",
        f"Perché: {v['recommendation']['rationale']}",
        "Clausole segnalate: " + (", ".join(flagged) if flagged else "nessuna") + ".",
    ]
    if highlighted:
        names = ", ".join(
            f"{r['name_it']} ({ROLE_IT.get(r['dissent']['role'], r['dissent']['role_name'])})" for r in highlighted
        )
        lines.append(f"Attenzione: un esperto sicuro non è d'accordo con il verdetto su {names}.")
    lines.append(f"Apri il verdetto e scegli chi ha ragione sui dissensi: {link}")
    return {"subject": f"[Consiglio] {title}: {recommendation}", "text": "\n".join(lines)}


class Reviewer:
    def __init__(
        self,
        review: Callable[[str, str, str], dict],
        cases: Path,
        *,
        secret: str,
        link: str,
        benchmark: str = "demo",
        catalog: dict[str, dict] | None = None,
    ) -> None:
        """`review(case id, text, mode, benchmark)` is the council and returns `Review.as_dict()`.

        `link` is the page's address, with `{id}` and `{key}`: for example
        `https://council.example.org/verdict/{id}?key={key}`.

        `catalog` (from `review.live.catalog`) turns on the judges' live reviews; without it they are off.
        """
        if "{id}" not in link or "{key}" not in link:
            raise ValueError("the link must contain {id} and {key}")
        self.review = review
        self.cases = cases
        self.secret = secret
        self.link = link
        self.benchmark_name = benchmark
        self.benchmark = BENCHMARK[benchmark]
        self.catalog = catalog
        self.lock = threading.Lock()  # one review at a time
        self.choices_lock = threading.Lock()  # choices do not wait for a review in progress

    def link_of(self, case_id: str) -> str:
        return self.link.format(id=case_id, key=case_key(self.secret, case_id))

    def key_is_valid(self, case_id: str, key: str) -> bool:
        return isinstance(key, str) and hmac.compare_digest(key, case_key(self.secret, case_id))

    def review_contract(
        self,
        contract: bytes | None,
        text: str | None,
        sender: str,
        subject: str,
        date: str,
        mode: str = "telepathy",
    ) -> dict:
        if (contract is None) == (text is None):
            raise Rejected("the contract is required: as a PDF or as text, only one")
        if mode not in MODES:
            raise Rejected(f"mode: {' or '.join(MODES)}")
        text = pdf_text(contract) if contract is not None else text
        if not isinstance(text, str) or not text.strip() or len(text) > MAX_CONTRACT:
            raise Rejected(f"contract: a text of at most {MAX_CONTRACT} characters is required")
        sender = short_text("sender", sender)
        subject = short_text("subject", subject, empty=True)
        date = short_text("date", date)
        fingerprint = hashlib.sha256(text.encode("utf-8")).hexdigest()
        case_id = (
            "council-"
            + hashlib.sha256(json.dumps([fingerprint, sender, subject, date, mode]).encode()).hexdigest()[:12]
        )
        with self.lock:
            folder = self.cases / case_id
            if (folder / "response.json").exists():
                return json.loads((folder / "response.json").read_text())
            review = self.review(case_id, text, mode, self.benchmark_name)
            title = subject or next((r.strip() for r in text.splitlines() if r.strip()), case_id)[:120]
            v = view(review, self.benchmark, title)
            # The page, served by this server, sends the choices here with the key of its link.
            v["choices_url"] = f"/verdict/{case_id}/choices?key={case_key(self.secret, case_id)}"
            response = self.response(case_id, v, mode, review)
            folder.mkdir(parents=True, exist_ok=True)
            (folder / "review.json").write_text(json.dumps(review, ensure_ascii=False))
            (folder / "view.json").write_text(json.dumps(v, ensure_ascii=False))
            (folder / "page.html").write_text(page(v))
            (folder / "email.json").write_text(
                json.dumps({"sender": sender, "subject": subject, "date": date, "contract_fingerprint": fingerprint})
            )
            (folder / "response.json").write_text(json.dumps(response, ensure_ascii=False, indent=1))
        return response

    def live_contracts(self) -> list[dict]:
        """The contracts the judge can choose, without the text."""
        if self.catalog is None:
            raise Rejected("live reviews are off")
        return live_listing(self.catalog)

    def live_review(self, key: str, mode: str = "telepathy") -> dict:
        """A live review: a contract of the catalog, reviewed now. Returns the response, as for Evolus, with the
        verdict view (in English, with the comparison with the experts) for the judge's page.
        Each live review is a new case, even on the same contract: the judge sees the council at work."""
        if self.catalog is None:
            raise Rejected("live reviews are off")
        item = self.catalog.get(key) if isinstance(key, str) else None
        if item is None:
            raise Rejected("contract: not one of the live review contracts")
        if mode not in MODES:
            raise Rejected(f"mode: {' or '.join(MODES)}")
        if not self.lock.acquire(blocking=False):
            raise Busy("the council is already reviewing a contract: try again in a minute")
        try:
            when = datetime.now(UTC).isoformat()
            case_id = "council-" + hashlib.sha256(json.dumps(["live", key, mode, when]).encode()).hexdigest()[:12]
            review = self.review(case_id, item["text"], mode, item["benchmark"])
            experts = item.get("experts")
            v = view(
                review,
                BENCHMARK[item["benchmark"]],
                item["title"],
                experts=experts,
                source=item["source"] if experts else None,
            )
            v |= {"language": "en", "live": when}
            response = self.response(case_id, v, mode, review) | {"live": True, "contract": key}
            folder = self.cases / case_id
            folder.mkdir(parents=True, exist_ok=True)
            (folder / "review.json").write_text(json.dumps(review, ensure_ascii=False))
            (folder / "view.json").write_text(json.dumps(v, ensure_ascii=False))
            (folder / "page.html").write_text(page(v))
            (folder / "response.json").write_text(json.dumps(response, ensure_ascii=False, indent=1))
        finally:
            self.lock.release()
        return response | {"view": v}

    def response(self, case_id: str, v: dict, mode: str, review: dict) -> dict:
        """What Evolus's main agent needs for the notice and the route."""
        link = self.link_of(case_id)
        dissents = [r for r in v["rows"] if r["dissent"]]
        return {
            "case_id": case_id,
            "verdict": v["recommendation"] is not None and v["seal"]["intact"],
            "recommendation": v["recommendation"],
            "seal_intact": v["seal"]["intact"],
            "flagged": [
                {"category": r["name_it"], "quote": r["quote"], "quote_found": r["quote_found"]}
                for r in v["rows"]
                if r["flag"]
            ],
            "major_dissents": [
                {
                    "category": r["name_it"],
                    "expert": r["dissent"]["role_name"],
                    "expert_confidence": r["dissent"]["expert_confidence"],
                    "highlighted": r["dissent"]["highlighted"],
                }
                for r in dissents
                if r["dissent"]["type"] == "major"
            ],
            "other_dissents": sum(r["dissent"]["type"] != "major" for r in dissents),
            "link": link,
            "notice": notice(v, link),
            "mode": mode,
            # The model that reviewed the contract: with routing it depends on the length.
            "model": review.get("model"),
            "tokens_generated": review.get("tokens_generated"),
            "seconds": round(review.get("seconds") or 0, 1),
        }

    def folder_of(self, case_id) -> Path:
        """The folder of a case that exists. The id is checked before it becomes a path."""
        if not isinstance(case_id, str) or not CASE_ID.fullmatch(case_id):
            raise Rejected("case_id: not the id of a council case")
        folder = self.cases / case_id
        if not (folder / "response.json").exists():
            raise Rejected(f"case_id: the case {case_id} does not exist")
        return folder

    def record_choices(self, case_id: str, choices: dict, who: str) -> dict:
        """The person's choices on the dissents: for each category in dissent, "expert" or "verdict"."""
        folder = self.folder_of(case_id)
        who = short_text("who", who)
        in_dissent = {r["key"] for r in json.loads((folder / "view.json").read_text())["rows"] if r["dissent"]}
        if not isinstance(choices, dict) or not choices:
            raise Rejected("choices: an object category → expert or verdict is required")
        if outside := sorted(set(choices) - in_dissent):
            raise Rejected(f"choices: these categories are not in dissent: {', '.join(outside)}")
        if any(v not in CHOICES for v in choices.values()):
            raise Rejected(f"choices: each value is {' or '.join(CHOICES)}")
        line = {"choices": choices, "who": who, "when": datetime.now(UTC).isoformat()}
        with self.choices_lock, (folder / "choices.jsonl").open("a") as f:
            f.write(json.dumps(line, ensure_ascii=False) + "\n")
        return {"case_id": case_id, "recorded": len(choices), **line}

    def case(self, case_id: str) -> dict:
        """The case's view and the recorded choices, the most recent last."""
        folder = self.folder_of(case_id)
        choices = folder / "choices.jsonl"
        return {
            "view": json.loads((folder / "view.json").read_text()),
            "choices": [json.loads(r) for r in choices.read_text().splitlines()] if choices.exists() else [],
        }

    def page_of(self, case_id: str) -> str:
        return (self.folder_of(case_id) / "page.html").read_text()

    def listing(self) -> list[dict]:
        """The cases, oldest first, with recommendation, major dissents and how many times the person chose."""
        cases = []
        for response in sorted(self.cases.glob("council-*/response.json"), key=lambda f: f.stat().st_mtime):
            r = json.loads(response.read_text())
            choices = response.parent / "choices.jsonl"
            cases.append(
                {
                    "case_id": r["case_id"],
                    "title": json.loads((response.parent / "view.json").read_text())["title"],
                    "recommendation": (r["recommendation"] or {}).get("value"),
                    "major_dissents": len(r["major_dissents"]),
                    "choices": len(choices.read_text().splitlines()) if choices.exists() else 0,
                }
            )
        return cases
