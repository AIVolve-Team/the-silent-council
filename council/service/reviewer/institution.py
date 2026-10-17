"""The council's institutional memory: the company's playbook and the precedents its people decided.

The playbook is a text file given at start-up. A precedent is born from a person's choice on a dissent of the verdict
page (`record_choices`): on that category of that contract the clause should, or should not, be flagged. Precedents
are append-only lines of `precedents.jsonl`, with who decided and when; removing a line removes the precedent.

The version is the hash of the playbook and of the precedents: each version is read once per model, sealed as base
messages and put at the head of every telepathy review (`Council.review(..., base=...)`), so no review rereads it.
"""

from __future__ import annotations

import hashlib
import json
import threading
from datetime import UTC, datetime
from pathlib import Path


class Institution:
    def __init__(self, playbook: Path, folder: Path) -> None:
        self.playbook = playbook.read_text().strip()
        if not self.playbook:
            raise ValueError(f"the playbook {playbook} is empty")
        self.folder = folder
        self.folder.mkdir(parents=True, exist_ok=True)
        self.file = folder / "precedents.jsonl"
        self.lock = threading.Lock()

    def precedents(self) -> list[dict]:
        return [json.loads(r) for r in self.file.read_text().splitlines()] if self.file.exists() else []

    def texts(self) -> list[str]:
        """What the memory reads, in order: the playbook, then the precedents in one text if there are any."""
        precedents = self.precedents()
        if not precedents:
            return [self.playbook]
        return [self.playbook, lessons_text(precedents)]

    def version(self) -> str:
        return hashlib.sha256(json.dumps(self.texts()).encode()).hexdigest()[:12]

    def learn(
        self,
        case_id: str,
        view: dict,
        choices: dict[str, str],
        who: str,
        reasons: dict[str, str] | None = None,
        corrections: dict[str, bool] | None = None,
        instruction: str | None = None,
    ) -> int:
        """The person's teaching becomes precedents: one per chosen or corrected category (a category already taught
        on that case is not repeated) and one per instruction (the same text is not repeated). A precedent keeps
        what the verdict said, the expert's side when there was a dissent, and the person's why when they wrote one:
        the next contracts need the why, not only the outcome. Returns how many precedents were added."""
        rows = {r["key"]: r for r in view["rows"]}
        reasons = reasons or {}
        now = datetime.now(UTC).isoformat()
        with self.lock:
            known = self.precedents()
            taught = {(p["case_id"], p.get("category")) for p in known}
            instructions = {p["text"] for p in known if p.get("kind") == "instruction"}
            added = []

            def case(category: str) -> dict:
                row = rows[category]
                return {
                    "case_id": case_id,
                    "title": view["title"],
                    "category": category,
                    "verdict_quote": row["quote"],
                    "verdict_rationale": row.get("rationale"),
                    "reason": reasons.get(category),
                    "who": who,
                    "when": now,
                }

            for category, choice in choices.items():
                row = rows[category]
                if (case_id, category) in taught or not row["dissent"]:
                    continue
                expert_says = row["dissent"]["expert_says"]
                added.append(
                    case(category)
                    | {
                        "flag": expert_says if choice == "expert" else not expert_says,
                        "sided_with": choice,
                        "expert": row["dissent"]["role_name"],
                        "expert_quote": row["dissent"]["expert_quote"],
                    }
                )
            for category, flag in (corrections or {}).items():
                if (case_id, category) in taught:
                    continue
                added.append(case(category) | {"kind": "correction", "flag": flag, "sided_with": "person"})
            if instruction and instruction not in instructions:
                added.append({"kind": "instruction", "case_id": case_id, "text": instruction, "who": who, "when": now})
            with self.file.open("a") as f:
                for precedent in added:
                    f.write(json.dumps(precedent, ensure_ascii=False) + "\n")
        return len(added)


def lessons_text(precedents: list[dict]) -> str:
    """The people's instructions first, then the precedents grouped by category, in the order the categories were
    first taught: what the company has learned about each category in one place."""
    instructions = [p for p in precedents if p.get("kind") == "instruction"]
    by_category: dict[str, list[dict]] = {}
    for p in precedents:
        if p.get("kind") != "instruction":
            by_category.setdefault(p["category"], []).append(p)
    sections = []
    if instructions:
        lines = [f"- {p['text']} (written by {p['who']} on {p['when'][:10]})" for p in instructions]
        sections.append("INSTRUCTIONS from the company's people, for every contract\n" + "\n".join(lines))
    sections += [
        f'LESSONS ON "{category}"\n' + "\n".join(lesson_text(p) for p in items)
        for category, items in by_category.items()
    ]
    return (
        "LESSONS the company's people taught the council by correcting its verdicts. Apply them to the clauses of the "
        "next contracts that look like these, not only to the same contracts.\n\n" + "\n\n".join(sections)
    )


def lesson_text(p: dict) -> str:
    """One precedent: what the verdict said and on which words, what the expert said, who was right and why."""

    def said(flag: bool, quote: str | None) -> str:
        return ("flag it" if flag else "do not flag it") + (f', on "{quote}"' if quote else "")

    lines = [
        f'- Contract "{p["title"]}", decided by {p["who"]} on {p["when"][:10]}: the clause '
        + ("should be flagged." if p["flag"] else "should not be flagged.")
    ]
    if p["sided_with"] == "person":
        verdict = said(not p["flag"], p.get("verdict_quote"))
        if p.get("verdict_rationale"):
            verdict += f" ({p['verdict_rationale']})"
        lines += [f"  The verdict said: {verdict}.", "  The person corrected it."]
    else:
        expert_said = p["flag"] if p["sided_with"] == "expert" else not p["flag"]
        verdict = said(not expert_said, p.get("verdict_quote"))
        if p.get("verdict_rationale"):
            verdict += f" ({p['verdict_rationale']})"
        right = f"the {p['expert']} expert" if p["sided_with"] == "expert" else "the verdict"
        lines += [
            f"  The verdict said: {verdict}.",
            f"  The {p['expert']} expert said: {said(expert_said, p.get('expert_quote'))}.",
            f"  The person sided with {right}.",
        ]
    if p.get("reason"):
        lines.append(f"  Why: {p['reason']}")
    return "\n".join(lines)


KEEPER = "You are the memory of the company: its contract playbook and the precedents decided by its people."


class Memory:
    """The institutional memory read by one model: built once per version, the latest version only."""

    def __init__(self, institution: Institution, engine) -> None:
        self.institution = institution
        self.engine = engine
        self.built: dict[str, list] = {}

    def current(self) -> tuple[str, list]:
        """The version and its base messages, ready for `Council.review(..., base=...)`."""
        version = self.institution.version()
        if version not in self.built:
            self.built = {version: self.build(version)}
        return version, self.built[version]

    def build(self, version: str) -> list:
        from engine import Agent

        keeper = Agent("playbook", KEEPER)
        chain: list = []
        for text in self.institution.texts():
            chain.append(
                self.engine.think(keeper, text, chain, session=f"institution/{version}", latent_steps=0, base=True)
            )
        return chain
