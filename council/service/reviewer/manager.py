"""The manager of the council's two tools for Evolus: the same for MCP and for HTTP.

    review_contract(contract, sender, subject, date, mode) → recommendation, dissents, seal, link, notice
    record_choices(case id, choices, who) → who is right on each dissent, in the case's log
    ask_council(case id, question, who) → the answer from the memory of that review, without the contract
    live_review(contract key, mode) → the verdict view, for the judges' live reviews

They hold for both transports, as for the Help Desk:
- one review at a time, because there is one GPU;
- the same email twice is the same case, and the council does not run again: it is Evolus retrying;
- without an intact seal there is no verdict, and the notice asks for a person;
- the contract's text is not saved: the case keeps the review, view, page and choices.

A contract in PDF is inspected first (`review.visual`): rules on the PDF, no model. A simple PDF goes the way
of a text contract. A complex one (scanned pages, signatures, stamps, drawings, hidden text) is read without its
hidden text and, when the visual mode is plugged in, goes to it with the pages that fired a signal and the sections
of the visual skill those signals call for. After it the council answers the fixed questions of those sections (who
signed, stamps, handwriting) from the memory of the review. The case says which signals fired, which way it went and
what the checks found (`visual.json`, the response's `visual`); the notice adds at most two lines of them.

The judges' live reviews do not wait: if the council is reviewing, they answer "busy" (409) right away.
"""

from __future__ import annotations

import hashlib
import hmac
import io
import json
import logging
import re
import threading
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from review import BENCHMARK
from review.live import listing as live_listing
from review.view import page, view

from .institution import Institution

log = logging.getLogger(__name__)

MODES = ("telepathy", "text")
MAX_PDF = 10 * 2**20
MAX_CONTRACT = 200_000  # characters: the longest of the CUAD sample has about 100,000
MAX_TEXT = 1000
CASE_ID = re.compile(r"council-[0-9a-f]{12}")
CHOICES = ("expert", "verdict")  # the two buttons of the verdict page
# The questions asked after a review in the visual route, per section of the visual skill. Scans and
# tables have none: their content is already in the clauses the council read.
VISUAL_QUESTIONS = {
    "signatures": "Who signed? Which signature blocks are empty?",
    "stamps": "Are there stamps or seals? What do they say?",
    "handwriting": "Are there handwritten corrections, notes or missing initials? What do they change?",
    "scans": None,
    "tables": None,
}
MAX_CHECK_LINES = 2  # the notice stays short: the rest is in the case


class Rejected(ValueError):
    """The request is not valid: 400 in HTTP, a tool error in MCP. The model has not been touched."""


class Busy(Exception):
    """A live review while the council is already reviewing: 409, try again shortly."""


def short_text(name: str, value, *, empty: bool = False) -> str:
    if not isinstance(value, str) or len(value) > MAX_TEXT or (not empty and not value.strip()):
        raise Rejected(f"{name}: a text of at most {MAX_TEXT} characters is required")
    return value.strip()


def check_pdf(pdf) -> None:
    if not isinstance(pdf, bytes) or not pdf.startswith(b"%PDF-") or len(pdf) > MAX_PDF:
        raise Rejected(f"contract: a PDF of at most {MAX_PDF // 2**20} MB is required")


def pdf_text(pdf: bytes) -> str:
    """The text of a contract in PDF. A PDF made only of images has no text: it needs OCR, which is not available."""
    check_pdf(pdf)
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


def check_lines(checks: list[dict]) -> list[str]:
    """The visual checks for the notice: the known answers, the signatures first, at most two lines."""
    lines = []
    for c in sorted(checks, key=lambda c: c.get("section") != "signatures"):
        answer = " ".join((c.get("answer") or "").split())
        if answer and c.get("known") is True:
            lines.append(f"Visual check: {answer}")
    return lines[:MAX_CHECK_LINES]


def notice(v: dict, link: str, checks: list[dict] | None = None) -> dict:
    """The email for the person: the service writes it and Evolus sends it as is. `checks` are the visual
    checks of a PDF in the visual route; a case without a verdict asks for a person and does not list them."""
    title = v["title"]
    if not v["seal"]["intact"] or v["recommendation"] is None:
        return {
            "subject": f"[Council] {title}: needs a person",
            "text": "\n".join(
                [
                    f"The council did not give a verdict on “{title}”.",
                    "The communication between the experts did not pass the check, or the verdict is not valid.",
                    "The contract must be reviewed by a person.",
                    f"Details: {link}",
                ]
            ),
        }
    recommendation = v["recommendation"]["value"]
    flagged = [r["key"] for r in v["rows"] if r["flag"]]
    highlighted = [r for r in v["rows"] if r["dissent"] and r["dissent"]["highlighted"]]
    lines = [
        f"The council reviewed “{title}”. Recommendation: {recommendation}.",
        f"Why: {v['recommendation']['rationale']}",
        "Flagged clauses: " + (", ".join(flagged) if flagged else "none") + ".",
    ]
    if highlighted:
        names = ", ".join(f"{r['key']} ({r['dissent']['role_name']})" for r in highlighted)
        lines.append(f"Warning: a confident expert disagrees with the verdict on {names}.")
    lines += check_lines(checks or [])
    lines.append(f"Open the verdict and choose who is right on the dissents: {link}")
    return {"subject": f"[Council] {title}: {recommendation}", "text": "\n".join(lines)}


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
        ask: Callable[..., dict] | None = None,
        inspect: Callable[[bytes], Any] | None = None,
        text_of: Callable[[bytes], str] | None = None,
        visual_review: Callable[..., dict] | None = None,
        skill_of: Callable[[list[dict]], tuple[list[str], str]] | None = None,
        institution: Institution | None = None,
        find_pdf: Callable[[str], bytes | None] | None = None,
    ) -> None:
        """`review(case id, text, mode, benchmark)` is the council and returns `Review.as_dict()`.

        `link` is the page's address, with `{id}` and `{key}`: for example
        `https://council.example.org/verdict/{id}?key={key}`.

        `catalog` (from `review.live.catalog`) turns on the judges' live reviews; without it they are off.

        `ask(case id, question, visual=False)` answers from the memory of a review (`memory.Memories.ask`); without
        it questions are off, and so are the visual checks.

        The visual skill only concerns contracts in PDF:
        - `inspect(pdf)` returns the inspection (`review.visual.inspect_pdf` by default, imported only when a PDF
          arrives, so text contracts do not need pypdfium2): `.complex`, `.visual_pages`, `.hidden_pages`, `.as_dict()`;
        - `text_of(pdf)` is the text of a complex PDF without its hidden text (`review.visual.visible_text` by default);
        - `skill_of(signals)` returns the sections of the visual skill the signals call for and the skill's text with
          those sections (`review.visual.skill_sections` and `skill_text` by default); `signals` are the records of
          `.as_dict()["signals"]`;
        - `visual_review(case id, text, pdf, pages, mode, benchmark, skill)` is the visual mode and returns
          `Review.as_dict()`, like `review`. `text` is the visible text, where the clauses are read: hidden text is
          already removed, so the PDF's text layer must not be read again. `pages` are the 1-based pages that fired a
          signal: they enter as images the memory of the first expert, with `skill`, the text of the skill's sections
          for this PDF's signals, which tells it what to look for. It must keep the memory of the review for `ask`
          (`memories.keep`), because right after it the rapporteur answers the fixed questions of those sections
          (`VISUAL_QUESTIONS`: who signed, stamps, handwriting) from that memory, with `ask(..., visual=True)`. It is
          called under the review lock, which also keeps pdfium, not thread-safe, to one thread. Without it complex
          PDFs go the text way and the case says that the visual mode is off.

        With `institution` the person's choices also become precedents of the council's institutional memory.

        `find_pdf(text)` (`mailbox.Mailbox.find_pdf`) returns the PDF a contract sent as text came from, or None: Evolus
        sends only the text of an attachment, and the visual route needs the PDF. A failure there is logged and the
        contract goes the text way, as without it.
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
        self.ask = ask
        self.inspect = inspect
        self.text_of = text_of
        self.visual_review = visual_review
        self.skill_of = skill_of
        self.institution = institution
        self.find_pdf = find_pdf
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
        from_mailbox = False
        if contract is None and self.find_pdf is not None and isinstance(text, str) and len(text) <= MAX_CONTRACT:
            try:
                found = self.find_pdf(text)
            except Exception:  # the mailbox is a bonus: without it the contract goes the text way
                log.exception("the contracts mailbox could not be read")
                found = None
            if found is not None:
                contract, text, from_mailbox = found, None, True
        if contract is not None:
            check_pdf(contract)
        elif not isinstance(text, str) or not text.strip() or len(text) > MAX_CONTRACT:
            raise Rejected(f"contract: a text of at most {MAX_CONTRACT} characters is required")
        sender = short_text("sender", sender)
        subject = short_text("subject", subject, empty=True)
        date = short_text("date", date)
        with self.lock:
            # The PDF is read under the lock: pdfium is not thread-safe, and the visual mode renders pages under it.
            visual = self.read_pdf(contract) if contract is not None else None
            if from_mailbox:
                visual["pdf_from"] = "mailbox"  # Evolus sent the text, the PDF came from the contracts mailbox
            skill = ""
            if visual is not None:
                text, skill = visual.pop("text"), visual.pop("skill")
            fingerprint = hashlib.sha256(text.encode("utf-8")).hexdigest()
            if visual is not None and visual["complex"]:
                # A complex PDF is not read as its text layer: the council gets the visible text, and in the visual
                # route the pages too. The route is in the fingerprint so that the same email, sent again once the
                # visual mode is on, is a new case and not the text-only one already written; in the visual route the
                # PDF is in it too, because its pages are part of what the council reads (two scans without text
                # would otherwise be the same case).
                parts = [fingerprint, visual["route"]]
                if visual["route"] == "visual":
                    parts.append(hashlib.sha256(contract).hexdigest())
                fingerprint = hashlib.sha256(json.dumps(parts).encode()).hexdigest()
            case_id = (
                "council-"
                + hashlib.sha256(json.dumps([fingerprint, sender, subject, date, mode]).encode()).hexdigest()[:12]
            )
            folder = self.cases / case_id
            if (folder / "response.json").exists():
                return json.loads((folder / "response.json").read_text())
            checks = None
            if visual is not None and visual["route"] == "visual":
                pages = list(visual["visual_pages"])
                review = self.visual_review(case_id, text, contract, pages, mode, self.benchmark_name, skill=skill)
                # Under the review lock already held: `ask` takes only the memories' own lock.
                checks = visual["checks"] = self.visual_checks(case_id, visual["skill_sections"])
            else:
                review = self.review(case_id, text, mode, self.benchmark_name)
            title = subject or next((r.strip() for r in text.splitlines() if r.strip()), case_id)[:120]
            v = view(review, self.benchmark, title)
            # The page, served by this server, sends the choices here with the key of its link.
            v["choices_url"] = f"/verdict/{case_id}/choices?key={case_key(self.secret, case_id)}"
            if visual is not None and visual["complex"]:
                # The verdict page shows why the PDF is complex and the visual checks; a simple PDF's view and
                # page stay as they were.
                v["visual"] = visual
            response = self.response(case_id, v, mode, review, checks)
            if visual is not None:
                response["visual"] = visual
            folder.mkdir(parents=True, exist_ok=True)
            (folder / "review.json").write_text(json.dumps(review, ensure_ascii=False))
            (folder / "view.json").write_text(json.dumps(v, ensure_ascii=False))
            (folder / "page.html").write_text(page(v))
            (folder / "email.json").write_text(
                json.dumps({"sender": sender, "subject": subject, "date": date, "contract_fingerprint": fingerprint})
            )
            if visual is not None:
                (folder / "visual.json").write_text(json.dumps(visual, ensure_ascii=False, indent=1))
            (folder / "response.json").write_text(json.dumps(response, ensure_ascii=False, indent=1))
        return response

    def read_pdf(self, pdf: bytes) -> dict:
        """The text the council reads and the route of a contract in PDF, with the reasons for the case.

        A simple PDF is read as today, so its case id does not change. A complex one is read without its hidden text
        (white, invisible, off the page or tiny): an instruction hidden in the text layer must not reach the agents.
        It goes the visual way when the visual mode is on and some page fired a signal for it; a complex PDF whose only
        signal is hidden text has nothing to look at, and goes the text way.
        """
        inspect = self.inspect
        if inspect is None:
            from review.visual import inspect_pdf as inspect  # pypdfium2 only when a PDF arrives
        try:
            inspection = inspect(pdf)
        except Exception as error:  # pdfium refuses a damaged or encrypted PDF with its own errors
            raise Rejected("contract: the PDF cannot be read") from error
        found = inspection.as_dict()
        on = self.visual_review is not None
        visual = {
            "complex": bool(inspection.complex),
            "signals": found["signals"],
            "visual_pages": found["visual_pages"],
            "route": "text",
            "hidden_text_removed": False,
            "visual_mode": "on" if on else "off",
            # The sections of the visual skill the signals call for: loaded in the visual route, and on the text
            # route what would have been, so the case says what the visual mode would have looked for.
            "skill_sections": [],
        }
        skill = ""
        if not inspection.complex:
            text = pdf_text(pdf)
        else:
            sections, skill = self.skill(found["signals"])
            visual["skill_sections"] = sections
            text_of = self.text_of
            if text_of is None:
                from review.visual import visible_text as text_of
            try:
                text = text_of(pdf)
            except Exception as error:
                raise Rejected("contract: the PDF cannot be read") from error
            if on and visual["visual_pages"]:
                visual["route"] = "visual"
            elif not text.strip():
                off = "" if on else ", which is off"
                raise Rejected(f"contract: the PDF has no text (is it a scan?): a scan needs the visual mode{off}")
            visual["hidden_text_removed"] = bool(inspection.hidden_pages)
        if not isinstance(text, str) or len(text) > MAX_CONTRACT:
            raise Rejected(f"contract: a text of at most {MAX_CONTRACT} characters is required")
        return visual | {"text": text, "skill": skill}

    def skill(self, signals: list[dict]) -> tuple[list[str], str]:
        """The sections of the visual skill for these signals and the skill's text with them."""
        if self.skill_of is not None:
            sections, text = self.skill_of(signals)
        else:
            from review.visual import skill_sections, skill_text

            sections = skill_sections(signals)
            text = skill_text(sections) if sections else ""
        return list(sections), text

    def visual_checks(self, case_id: str, sections: list[str]) -> list[dict]:
        """The fixed questions of the loaded sections, answered from the memory of the review just made.

        A question that fails (the memory is gone, it did not pass the checks, the answer is not valid JSON) is
        recorded with `known` false and the reason, and the others go on: the review stands without it.
        """
        if self.ask is None:
            return []
        checks = []
        for section in sections:
            question = VISUAL_QUESTIONS.get(section)
            if question is None:
                continue
            check = {"section": section, "question": question, "answer": None, "objects": [], "known": False}
            try:
                result = self.ask(case_id, question, visual=True)
            except Exception as error:  # noqa: BLE001 - a failure here must not lose the review already made
                reason = str(error) if isinstance(error, Rejected) else f"the question failed ({type(error).__name__})"
                checks.append(check | {"error": reason})
                continue
            data = result.get("answer") if isinstance(result, dict) else None
            if isinstance(result, dict) and result.get("stopped") is not None:
                check["error"] = "the memory of the review did not pass the checks"
            elif not isinstance(data, dict):
                check["error"] = "the answer is not a valid JSON"
            else:
                objects = data.get("objects")
                check |= {
                    "answer": data.get("answer") if isinstance(data.get("answer"), str) else None,
                    "objects": objects if isinstance(objects, list) else [],
                    "known": data.get("known") is True,
                }
            checks.append(check)
        return checks

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

    def response(self, case_id: str, v: dict, mode: str, review: dict, checks: list[dict] | None = None) -> dict:
        """What Evolus's main agent needs for the notice and the route. `checks`: the visual checks."""
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
            "notice": notice(v, link, checks),
            "mode": mode,
            # The model that reviewed the contract: with routing it depends on the length.
            "model": review.get("model"),
            # The institutional memory the review started from: version, precedents, base fingerprints.
            "institution": review.get("institution"),
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

    def record_choices(
        self,
        case_id: str,
        choices: dict | None,
        who: str,
        reasons: dict | None = None,
        corrections: dict | None = None,
        instruction: str | None = None,
    ) -> dict:
        """The person's choices on the dissents: for each category in dissent, "expert" or "verdict".

        With the institutional memory the person can also teach the council:
        - `reasons`: for some of the chosen or corrected categories, why, in the person's words;
        - `corrections`: on rows without a dissent, category → true if the clause should be flagged, false if not,
          where the verdict got it wrong;
        - `instruction`: a rule for the next contracts, not tied to a row.
        At least one choice, correction or instruction is required."""
        folder = self.folder_of(case_id)
        who = short_text("who", who)
        rows = {r["key"]: r for r in json.loads((folder / "view.json").read_text())["rows"]}
        choices = {} if choices is None else choices
        corrections = {} if corrections is None else corrections
        if not isinstance(choices, dict) or not isinstance(corrections, dict):
            raise Rejected("choices: an object category → expert or verdict is required")
        instruction = (
            short_text("instruction", instruction) if isinstance(instruction, str) and instruction.strip() else None
        )
        if not choices and not corrections and instruction is None:
            raise Rejected("choices: an object category → expert or verdict is required")
        if outside := sorted(k for k in choices if k not in rows or not rows[k]["dissent"]):
            raise Rejected(f"choices: these categories are not in dissent: {', '.join(outside)}")
        if any(v not in CHOICES for v in choices.values()):
            raise Rejected(f"choices: each value is {' or '.join(CHOICES)}")
        if outside := sorted(k for k in corrections if k not in rows or rows[k]["dissent"] or k in choices):
            raise Rejected(f"corrections: not rows of the verdict without a dissent: {', '.join(outside)}")
        if any(not isinstance(v, bool) for v in corrections.values()):
            raise Rejected("corrections: each value is true (flag it) or false (do not flag it)")
        if reasons is not None and not isinstance(reasons, dict):
            raise Rejected("reasons: an object category → reason is required")
        if outside := sorted(set(reasons or {}) - set(choices) - set(corrections)):
            raise Rejected(f"reasons: these categories have no choice: {', '.join(outside)}")
        reasons = {
            k: short_text(f"reasons.{k}", v) for k, v in (reasons or {}).items() if isinstance(v, str) and v.strip()
        }
        line = {"choices": choices, "who": who, "when": datetime.now(UTC).isoformat()}
        line |= {
            k: v for k, v in (("reasons", reasons), ("corrections", corrections), ("instruction", instruction)) if v
        }
        with self.choices_lock, (folder / "choices.jsonl").open("a") as f:
            f.write(json.dumps(line, ensure_ascii=False) + "\n")
        recorded = {"case_id": case_id, "recorded": len(choices) + len(corrections) + (instruction is not None), **line}
        if self.institution is not None:
            view = json.loads((folder / "view.json").read_text())
            recorded["precedents_added"] = self.institution.learn(
                case_id, view, choices, who, reasons, corrections, instruction
            )
        return recorded

    def ask_council(self, case_id: str, question: str, who: str) -> dict:
        """A question on a reviewed case, for example "who signed?": the council answers from the memory of that
        review, without the contract. Question, answer and who asked go in the case's log.

        On a case that went the visual way the question is asked on the pages too, and the answer has the objects
        seen on them: asked as text, the rapporteur does not look at what the visual expert saw."""
        folder = self.folder_of(case_id)
        question = short_text("question", question)
        who = short_text("who", who)
        if self.ask is None:
            raise Rejected("questions are off")
        seen = folder / "visual.json"
        visual = seen.exists() and json.loads(seen.read_text()).get("route") == "visual"
        with self.lock:  # the same GPU as the reviews
            result = self.ask(case_id, question, visual=True) if visual else self.ask(case_id, question)
        line = {"question": question, "who": who, "when": datetime.now(UTC).isoformat()} | result
        with self.choices_lock, (folder / "questions.jsonl").open("a") as f:
            f.write(json.dumps(line, ensure_ascii=False) + "\n")
        return {"case_id": case_id, **line}

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
