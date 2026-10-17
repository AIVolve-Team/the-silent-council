"""The contract's PDF from the contracts mailbox: which attachment is the one Evolus read, and the route it takes."""

from datetime import UTC, datetime, timedelta
from email.message import EmailMessage
from pathlib import Path

from reviewer.mailbox import Attachment, attachments_of, pdf_words, pick
from reviewer.manager import Reviewer

from .conftest import CONTRACT, LINK, SECRET, email, pdf_with_text
from .test_visual_routing import SIGNED, VISIBLE, FakeVisual

PAGES = Path(__file__).resolve().parents[2] / "data" / "vision" / "pages"
NOW = datetime(2026, 10, 17, 18, 0, tzinfo=UTC)


def attachment(name: str, minutes_ago: int = 1) -> Attachment:
    return Attachment(NOW - timedelta(minutes=minutes_ago), name, (PAGES / name).read_bytes())


def as_evolus_reads(pdf: bytes) -> str:
    """Another extractor: the same words, lines and spaces broken differently."""
    return " ".join(pdf_words(pdf).split()).replace(". ", ".\n")


def test_the_attachment_with_the_same_words_is_picked():
    a, c, d = attachment("a-embedded-images.pdf", 30), attachment("c-text-only.pdf", 5), attachment("d-signals.pdf", 2)
    assert pick(as_evolus_reads(a.pdf), [a, c, d], NOW) is a
    assert pick(as_evolus_reads(d.pdf), [a, c, d], NOW) is d


def test_a_text_that_matches_no_attachment_picks_none():
    assert pick(CONTRACT, [attachment("a-embedded-images.pdf"), attachment("d-signals.pdf")], NOW) is None


def test_without_text_only_the_newest_recent_pdf_is_taken():
    """A scan: Evolus's reader finds no text, so the newest PDF of the last minutes is the one."""
    old, new = attachment("a-embedded-images.pdf", 40), attachment("b-scanned.pdf", 3)
    assert pick("", [old, new], NOW) is new
    assert pick("", [old], NOW) is None


def test_the_pdfs_of_a_message_are_found():
    message = EmailMessage()
    message["Subject"], message["Date"] = "Contract to sign", "Sat, 17 Oct 2026 17:58:00 +0000"
    message.set_content("Hi, the contract is attached.")
    pdf = (PAGES / "d-signals.pdf").read_bytes()
    message.add_attachment(pdf, maintype="application", subtype="pdf", filename="contract.pdf")
    message.add_attachment(b"not a pdf", maintype="application", subtype="octet-stream", filename="notes.bin")
    found = attachments_of(message)
    assert [(a.subject, a.pdf) for a in found] == [("Contract to sign", pdf)]
    assert found[0].received == datetime(2026, 10, 17, 17, 58, tzinfo=UTC)


def test_a_text_from_evolus_goes_the_visual_way_with_the_pdf_of_the_mailbox(council, tmp_path):
    pdf = pdf_with_text(VISIBLE)
    asked = []

    def find_pdf(text):
        asked.append(text)
        return pdf

    visual = FakeVisual()
    reviewer = Reviewer(
        council, tmp_path / "cases", secret=SECRET, link=LINK, inspect=lambda b: SIGNED,
        text_of=lambda b: VISIBLE, visual_review=visual, skill_of=lambda s: (["signatures"], "skill"),
        find_pdf=find_pdf,
    )  # fmt: skip
    r = reviewer.review_contract(None, VISIBLE, **email())
    assert asked == [VISIBLE] and r["visual"]["route"] == "visual" and r["visual"]["pdf_from"] == "mailbox"
    assert visual.calls[0][2] == pdf


def test_without_the_pdf_or_with_the_mailbox_down_the_text_goes_the_text_way(council, tmp_path):
    def down(text):
        raise OSError("imap.gmail.com unreachable")

    for find_pdf in (lambda text: None, down):
        reviewer = Reviewer(council, tmp_path / "cases", secret=SECRET, link=LINK, find_pdf=find_pdf)
        r = reviewer.review_contract(None, CONTRACT, **email())
        assert "visual" not in r and r["case_id"].startswith("council-")
