"""The JSON schemas of note and verdict, for constrained decoding.

Note and verdict have the same schema for the categories: `flag`, with true or false for each one. The boolean is a
single token, so its probability gives the confidence. Quotes and rationales are in lists with a maximum number of
items and of characters: this way note and verdict always fit in their token limit and the JSON gets closed.
The field order is enforced: in the verdict first the objections, then the rows, at the end the recommendation.
"""

from __future__ import annotations

from .categories import Category

RECOMMENDATIONS = ["sign", "negotiate", "do not sign"]
MAX_NOTE_QUOTES = 3
MAX_VERDICT_DETAILS = 8
# What the council can point at on a page it saw as an image.
VISUAL_OBJECTS = [
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
]
MAX_VISUAL_OBJECTS = 8
MAX_PAGE = 999
BOX = 1000  # box_2d coordinates are normalized to 0-1000, as Gemma's detection format


def _flag(keys: list[str]) -> dict:
    return {
        "type": "object",
        "properties": {k: {"type": "boolean"} for k in keys},
        "required": list(keys),
        "additionalProperties": False,
    }


def _list(keys: list[str], fields: dict[str, int], maximum: int) -> dict:
    """A list of objects {category, fields...}, with `maximum` items and text fields with a maximum of characters."""
    properties = {"category": {"enum": keys}} | {f: {"type": "string", "maxLength": n} for f, n in fields.items()}
    return {
        "type": "array",
        "maxItems": maximum,
        "items": {
            "type": "object",
            "properties": properties,
            "required": list(properties),
            "additionalProperties": False,
        },
    }


def note_schema(categories: tuple[Category, ...]) -> dict:
    keys = [c.key for c in categories]
    return {
        "type": "object",
        "properties": {
            "flag": _flag(keys),
            "quotes": _list(keys, {"text": 120}, MAX_NOTE_QUOTES),
            "amounts_dates_parties": {"type": "array", "maxItems": 4, "items": {"type": "string", "maxLength": 40}},
        },
        "required": ["flag", "quotes", "amounts_dates_parties"],
        "additionalProperties": False,
    }


def verdict_schema(categories: tuple[Category, ...], *, objections: bool = True) -> dict:
    """Without `objections` it is the verdict of whoever works alone (solo agent and vote among 4 in the eval):
    they have no colleagues to object to."""
    keys = [c.key for c in categories]
    properties = {
        "objections": _list(keys, {"objection": 150}, 3),
        "flag": _flag(keys),
        "details": _list(keys, {"quote": 120, "rationale": 100}, MAX_VERDICT_DETAILS),
        "recommendation": {"enum": RECOMMENDATIONS},
        "rationale": {"type": "string", "maxLength": 250},
    }
    if not objections:
        del properties["objections"]
    return {
        "type": "object",
        "properties": properties,
        "required": list(properties),
        "additionalProperties": False,
    }


def answer_schema() -> dict:
    """The answer to a question on a reviewed contract: the answer, the quote that supports it and whether the
    council's memory tells it at all."""
    properties = {
        "answer": {"type": "string", "maxLength": 300},
        "quote": {"type": "string", "maxLength": 240},
        "known": {"type": "boolean"},
    }
    return {
        "type": "object",
        "properties": properties,
        "required": list(properties),
        "additionalProperties": False,
    }


def _integer(minimum: int, maximum: int) -> dict:
    """An integer between two bounds.

    The decoder (lm-format-enforcer 0.11.3) keeps it an integer but ignores the bounds, and its numeric enums lose
    count of the items of an array after a value like 760 or 1000. So the bounds are checked after decoding
    (`visual_objects`), and a model stuck on digits runs into `max_tokens`: the JSON is then not valid, which the caller
    treats as no answer.
    """
    return {"type": "integer", "minimum": minimum, "maximum": maximum}


def visual_answer_schema() -> dict:
    """The answer to a visual question on a reviewed contract: the answer, the objects the colleagues
    saw on the pages with their page and box, and whether the council's memory tells it at all."""
    item = {
        "page": _integer(1, MAX_PAGE),
        "type": {"enum": VISUAL_OBJECTS},
        # [ymin, xmin, ymax, xmax]
        "box_2d": {"type": "array", "minItems": 4, "maxItems": 4, "items": _integer(0, BOX)},
        "text": {"type": "string", "maxLength": 120},
    }
    properties = {
        "answer": {"type": "string", "maxLength": 300},
        "objects": {
            "type": "array",
            "maxItems": MAX_VISUAL_OBJECTS,
            "items": {"type": "object", "properties": item, "required": list(item), "additionalProperties": False},
        },
        "known": {"type": "boolean"},
    }
    return {
        "type": "object",
        "properties": properties,
        "required": list(properties),
        "additionalProperties": False,
    }


def visual_objects(objects) -> list[dict]:
    """The objects of a visual answer whose page and box are within the schema's bounds, which the decoder does not
    enforce: an object out of them is dropped, not guessed back into the page."""

    def within(value, low: int, high: int) -> bool:
        return isinstance(value, int) and not isinstance(value, bool) and low <= value <= high

    kept = []
    for o in objects if isinstance(objects, list) else []:
        box = o.get("box_2d") if isinstance(o, dict) else None
        if (
            isinstance(box, list)
            and len(box) == 4
            and all(within(v, 0, BOX) for v in box)
            and box[0] <= box[2]
            and box[1] <= box[3]
            and within(o.get("page"), 1, MAX_PAGE)
            and o.get("type") in VISUAL_OBJECTS
            and isinstance(o.get("text"), str)
        ):
            kept.append(o)
    return kept[:MAX_VISUAL_OBJECTS]


def max_tokens(schema: dict) -> int:
    """How many tokens are needed, at most, to write a valid JSON for the schema.

    It counts one token per character: the worst case, that of a model stuck repeating short tokens. With this
    limit note and verdict always get closed.
    """
    if "enum" in schema:
        return max(len(str(v)) for v in schema["enum"]) + 2
    kind = schema.get("type")
    if kind == "boolean":
        return 5
    if kind == "string":
        return schema["maxLength"] + 2
    if kind == "integer":
        # One token per digit and the sign: both bounds are needed, or the number has no limit.
        return max(len(str(schema["minimum"])), len(str(schema["maximum"])))
    if kind == "array":
        return schema["maxItems"] * (max_tokens(schema["items"]) + 1) + 2
    if kind == "object":
        return 2 + sum(len(k) + 4 + max_tokens(v) for k, v in schema["properties"].items())
    raise ValueError(f"schema without a limit: {schema}")
