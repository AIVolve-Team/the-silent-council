"""The contract's PDF, taken from the contracts mailbox: Evolus sends only the text of an attachment.

In Evolus an attachment reaches only «Leggi il documento» and «Chiama un estrattore dati»: an endpoint receives text,
never a file (checked on 17/10, also through «Esegui uno script»). The visual route needs the PDF itself, so the server
reads it from the same mailbox Evolus reads, over IMAP, and picks the attachment whose text is the one Evolus sent.
A scan has no text: then it takes the newest PDF, if it arrived in the last minutes.

The mailbox is read only (the folder is selected read-only, nothing is marked or moved). Its password is an app password
given in the environment, never in a file of the repo.
"""

from __future__ import annotations

import email
import imaplib
import io
import re
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from email.message import Message
from email.utils import parsedate_to_datetime

# Share of the words two texts have in common, over the words of either: the extractors of Evolus and of pypdf
# break lines and spaces differently, the words stay the same.
MIN_OVERLAP = 0.8
# Without a text (a scan) only a PDF that arrived this recently is taken: Evolus calls the server within minutes.
RECENT = timedelta(minutes=15)
# How far back the mailbox is searched: Evolus reads the mailbox every two minutes.
SINCE = timedelta(days=2)
MAX_MESSAGES = 30


@dataclass
class Attachment:
    received: datetime
    subject: str
    pdf: bytes


def words(text: str) -> set[str]:
    return set(re.findall(r"\w+", text.lower()))


def overlap(a: str, b: str) -> float:
    wa, wb = words(a), words(b)
    if not wa or not wb:
        return 0.0
    return len(wa & wb) / len(wa | wb)


def pdf_words(pdf: bytes) -> str:
    """The PDF's text as pypdf reads it, empty if it cannot be read: only to compare it with the text Evolus sent."""
    from pypdf import PdfReader

    try:
        return "\n".join(p.extract_text() or "" for p in PdfReader(io.BytesIO(pdf)).pages)
    except Exception:  # noqa: BLE001 - an unreadable attachment is simply not the one
        return ""


def pick(text: str, attachments: list[Attachment], now: datetime) -> Attachment | None:
    """The attachment Evolus read: the one whose text shares the most words with `text`, at least MIN_OVERLAP; with no
    text, the newest one of the last RECENT minutes."""
    if len(words(text)) < 5:
        recent = [a for a in attachments if now - a.received <= RECENT]
        return max(recent, key=lambda a: a.received, default=None)
    scored = [(overlap(text, pdf_words(a.pdf)), a.received, a) for a in attachments]
    best = max(scored, key=lambda s: (s[0], s[1]), default=None)
    return best[2] if best is not None and best[0] >= MIN_OVERLAP else None


def attachments_of(message: Message) -> list[Attachment]:
    try:
        received = parsedate_to_datetime(message.get("Date", "")).astimezone(UTC)
    except (TypeError, ValueError):
        received = datetime.now(UTC)
    found = []
    for part in message.walk():
        name = (part.get_filename() or "").lower()
        if part.get_content_type() == "application/pdf" or name.endswith(".pdf"):
            data = part.get_payload(decode=True)
            if data and data.startswith(b"%PDF"):
                found.append(Attachment(received, str(message.get("Subject", "")), data))
    return found


class Mailbox:
    def __init__(self, user: str, password: str, *, host: str = "imap.gmail.com", folder: str = "Contratti") -> None:
        self.user, self.password, self.host, self.folder = user, password, host, folder

    def attachments(self) -> list[Attachment]:
        """The PDFs of the last MAX_MESSAGES messages of the folder, from the last SINCE days."""
        since = (datetime.now(UTC) - SINCE).strftime("%d-%b-%Y")
        with imaplib.IMAP4_SSL(self.host) as imap:
            imap.login(self.user, self.password)
            status, _ = imap.select(f'"{self.folder}"', readonly=True)
            if status != "OK":
                raise RuntimeError(f"the folder {self.folder} cannot be opened")
            _, ids = imap.search(None, "SINCE", since)
            found = []
            for number in ids[0].split()[-MAX_MESSAGES:]:
                _, parts = imap.fetch(number, "(BODY.PEEK[])")  # PEEK: the message stays unread for Evolus
                raw = next((p[1] for p in parts if isinstance(p, tuple)), None)
                if raw:
                    found += attachments_of(email.message_from_bytes(raw))
            return found

    def find_pdf(self, text: str) -> bytes | None:
        """The PDF whose text Evolus sent, or None: then the contract goes the text way, as before."""
        chosen = pick(text, self.attachments(), datetime.now(UTC))
        return chosen.pdf if chosen is not None else None
