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
    if kind == "array":
        return schema["maxItems"] * (max_tokens(schema["items"]) + 1) + 2
    if kind == "object":
        return 2 + sum(len(k) + 4 + max_tokens(v) for k, v in schema["properties"].items())
    raise ValueError(f"schema without a limit: {schema}")
