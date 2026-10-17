"""The council's prompts, in English. The same in telepathy and in text: only the channel changes.

In telepathy the expert reads its part and "thinks" the analysis in the latent steps; in text it writes it. The
rapporteur does not read the contract: it knows it only from what it receives from its colleagues.
"""

from __future__ import annotations

from .categories import FINANCE, LEGAL, RISK, ROLE_NAMES, Benchmark, Category
from .schemas import BOX, MAX_VISUAL_OBJECTS, VISUAL_OBJECTS

CLIENT = "a small Italian business, the client of the contract"


def _list(categories: tuple[Category, ...]) -> str:
    return "\n".join(f'- "{c.key}": {c.description}' for c in categories)


def expert_instructions(role: str, benchmark: Benchmark) -> str:
    colleagues = ", ".join(r for r in benchmark.readers if r != role)
    return (
        f"You are the {ROLE_NAMES[role]} expert of a council that reviews a contract on behalf of {CLIENT}. "
        f"You read only your part of the contract: your colleagues ({colleagues}) read the others, and the rapporteur "
        "receives everyone's memory.\n\n"
        f"The categories you are responsible for. For each one, {benchmark.rule}.\n{_list(benchmark.of_role(role))}"
    )


def reading(section: str) -> str:
    part = section.strip() or "(This contract has no clauses in your part.)"
    return (
        f"Your part of the contract:\n\n{part}\n\n"
        "Write a short analysis for your colleagues: for each category you are responsible for, whether there is a "
        "clause to flag and with which exact words of the contract; then the amounts, dates and parties that matter."
    )


def note(section: str | None = None) -> str:
    """The note for the person. In text mode the expert does not have its part in memory, so it rereads it."""
    start = "" if section is None else f"Your part of the contract:\n\n{section.strip()}\n\n"
    return start + (
        "Now write your note in JSON.\n"
        '- "flag": for each category you are responsible for, true if it should be flagged, false otherwise.\n'
        '- "quotes": at most 3, for the most important categories set to true: the exact words of the contract, '
        "copied without changing them, at most 20 words.\n"
        '- "amounts_dates_parties": at most 4 among the amounts, dates and parties that matter.'
    )


def rapporteur_instructions(benchmark: Benchmark) -> str:
    colleagues = ", ".join(benchmark.readers)
    return (
        f"You are the rapporteur, the devil's advocate of a council that reviews a contract on behalf of {CLIENT}. "
        f"You have not read the contract: you know it only from what you receive from your colleagues ({colleagues}), "
        "who have each read a part of it. You judge all the categories, with balance: flag what is there, not what "
        "is missing.\n\n"
        f"The categories. For each one, {benchmark.rule}.\n{_list(benchmark.categories)}"
    )


def verdict(*, translate: bool = False, objections: bool = True) -> str:
    """Without `objections` it is the request for whoever works alone, with `verdict_schema(..., objections=False)`
."""
    translation = " If a quote is not in English, add the English translation in parentheses." if translate else ""
    points = [
        (
            '"objections": before deciding, the objections to your colleagues\' opinion: where they might be wrong or '
            "what they might have missed, with the category. If there are none, leave the list empty."
        ),
        '"flag": for each category, true if it should be flagged, false otherwise.',
        (
            '"details": at most 8, for the categories set to true: the "quote", that is the exact words of the '
            'contract copied without changing them (at most 20 words), and the "rationale", one line in English on why it '
            f"matters for the client.{translation}"
        ),
        '"recommendation": "sign", "negotiate" or "do not sign", for the client.',
        '"rationale": the reason for the recommendation, with the categories that weigh the most.',
    ]
    points = points if objections else points[1:]
    return "Write the verdict in JSON, in this order.\n" + "\n".join(f"{i}. {p}" for i, p in enumerate(points, 1))


# --- The eval's comparison configurations: whoever works alone reads the whole contract ---------------------

ADVOCATE = "advocate"
# The 4 independent agents of the vote: the same points of view as the council, each with the whole contract.
INDEPENDENT = (LEGAL, FINANCE, RISK, ADVOCATE)


def solo_instructions(benchmark: Benchmark) -> str:
    return (
        f"You review a contract on behalf of {CLIENT}. You read the whole contract and judge all the categories, "
        "with balance: flag what is there, not what is missing.\n\n"
        f"The categories. For each one, {benchmark.rule}.\n{_list(benchmark.categories)}"
    )


def independent_instructions(role: str, benchmark: Benchmark) -> str:
    who = "the devil's advocate" if role == ADVOCATE else f"the {ROLE_NAMES[role]} expert"
    return (
        f"You are {who} and you review a contract alone on behalf of {CLIENT}, from your point of view. You read the "
        "whole contract and judge all the categories, with balance: flag what is there, not what is missing.\n\n"
        f"The categories. For each one, {benchmark.rule}.\n{_list(benchmark.categories)}"
    )


def whole_contract(text: str, *, translate: bool = False) -> str:
    return f"The contract:\n\n{text.strip()}\n\n" + verdict(translate=translate, objections=False)


# --- Questions on a reviewed contract: the rapporteur answers from the council's memory ---------------------


def question_instructions() -> str:
    return (
        f"You are the rapporteur of a council that reviewed a contract on behalf of {CLIENT}. You have not read the "
        "contract: you know it only from what you received from your colleagues, who each read a part of it. Answer "
        "the question from that knowledge alone, and say so when it does not tell you the answer."
    )


def question(text: str) -> str:
    return (
        f"The question: {text.strip()}\n\n"
        "Answer in JSON, in this order.\n"
        '1. "answer": the answer in at most 2 sentences, in the language of the question.\n'
        '2. "quote": the exact words of the contract that support it, copied without changing them, at most 30 '
        "words; empty if there are none.\n"
        '3. "known": true if what you received tells you the answer, false if it does not.'
    )


def visual_question(text: str) -> str:
    """A question on what the pages look like: in the visual route the first expert saw the pages that
    fired a signal as images, and the others got that memory in telepathy. The rapporteur points at what they saw,
    with the page and the box, and invents nothing it did not receive."""
    return (
        f"The question: {text.strip()}\n\n"
        "It is about what is drawn, signed, stamped or handwritten on the pages that your colleagues saw as images.\n"
        "Answer in JSON, in this order.\n"
        '1. "answer": the answer in at most 2 sentences, in the language of the question.\n'
        f'2. "objects": at most {MAX_VISUAL_OBJECTS} of the things your colleagues saw on those pages that answer the '
        'question, each with its "page" (the page number, from 1), its "type" (one of: '
        + ", ".join(VISUAL_OBJECTS)
        + f'), its "box_2d" [ymin, xmin, ymax, xmax] with the coordinates normalized from 0 to {BOX} (0, 0 is the '
        'top left corner of the page) and its "text": the name or the words written in it or next to it, at most 120 '
        "characters, empty if there are none. Only what your colleagues saw: if they did not see it, leave it out; "
        "empty if there is nothing.\n"
        '3. "known": true if what you received tells you the answer, false if it does not.'
    )


def visual_reading(pages: list[int], placeholder: str) -> str:
    """The visual expert's text: the images of the pages that fired a signal, each after its number, as in
    the probe. What to look for and how to report it are its instructions, the visual skill."""
    images = "\n\n".join(f"[Page {page}]\n{placeholder}" for page in pages)
    return (
        f"{images}\n\nThe images above are the pages of the contract that carry pictures or scans, each after its page "
        "number. Inspect them following the instructions and return the JSON object."
    )
