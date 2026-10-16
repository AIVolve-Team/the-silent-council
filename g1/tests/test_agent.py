import json

import pytest

from g1.agent import problems

ARGUMENTS = {
    "sender": "supplier@example.com",
    "subject": "Invoice 12",
    "date": "2026-10-12",
    "pdf_url": "https://example.org/f.pdf",
}
CALL = {"type": "function", "function": {"name": "examine_invoice", "arguments": json.dumps(ARGUMENTS)}}


def response(**message):
    return {"choices": [{"message": {"role": "assistant", "content": None, "tool_calls": [], **message}}]}


def test_a_real_call_to_examine_invoice_is_fine():
    assert problems(response(tool_calls=[CALL])) == []


@pytest.mark.parametrize(
    ("defect", "word"),
    [
        ({"content": "<tool_call>\n<function=examine_invoice>\n</function>\n</tool_call>"}, "parser"),
        ({"content": "Sure, here is the analysis of the invoice."}, "no tool call"),
        ({"tool_calls": [CALL], "reasoning_content": "The user wants me to examine…"}, "thought"),
        ({"tool_calls": [CALL], "reasoning": "The user wants me to examine…"}, "thought"),
        (
            {"tool_calls": [{"type": "function", "function": {"name": "examine_invoice", "arguments": "{not json"}}]},
            "arguments",
        ),
        (
            {"tool_calls": [{"type": "function", "function": {"name": "pay_now", "arguments": "{}"}}]},
            "examine_invoice",
        ),
    ],
)
def test_the_endpoint_defects_are_recognized(defect, word):
    found = problems(response(**defect))

    assert any(word in p for p in found), found
