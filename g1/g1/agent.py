"""Check of the vLLM endpoint of the main agent: a real call to `examine_invoice`?

    python -m g1.agent --url http://127.0.0.1:8000 --key "$VLLM_API_KEY"

Sends a request the way Evolus would, with no sampling parameters and no `chat_template_kwargs` (Evolus does not pass
them), with the `examine_invoice` tool of the engine server, and checks that:
- the answer is a tool call read by the `qwen3_coder` parser, not raw XML in the text;
- the arguments are valid JSON;
- there is no reasoning: "thinking" is turned off on the server side (`--default-chat-template-kwargs`).
Exits with 1 if it finds a problem. No extra libraries: it works in any environment with Python.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.request

MODEL = "Qwen/Qwen3.6-35B-A3B"
# The same fields as the MCP tool of the engine server (help desk service).
TOOL = {
    "type": "function",
    "function": {
        "name": "examine_invoice",
        "description": "Examines the original PDF of an invoice received by email and returns the outcome: pay (a "
        "proposal awaiting approval), person or block.",
        "parameters": {
            "type": "object",
            "properties": {
                "sender": {"type": "string", "description": "the sender of the email"},
                "subject": {"type": "string", "description": "the subject of the email"},
                "date": {"type": "string", "description": "the date of the email"},
                "pdf_base64": {"type": "string", "description": "the PDF in base64"},
                "pdf_url": {"type": "string", "description": "a link to the PDF, if the file is too large"},
                "mode": {"type": "string", "enum": ["telepathy", "text"]},
            },
            "required": ["sender", "subject", "date"],
        },
    },
}
MESSAGES = [
    {
        "role": "system",
        "content": "You are the main agent of the help desk: for every email with an invoice you call examine_invoice, "
        "then you choose the path based on the outcome.",
    },
    {
        "role": "user",
        "content": "An email arrived from supplier@example.com, subject «Invoice 12», date 2026-10-12, with the "
        "invoice attached: https://example.org/invoice-12.pdf. Examine it.",
    },
]


def problems(response: dict) -> list[str]:
    """What is wrong with the /v1/chat/completions response; empty if the endpoint is ready for Evolus."""
    message = response["choices"][0]["message"]
    found = []
    text = message.get("content") or ""
    calls = message.get("tool_calls") or []
    if "<tool_call>" in text or "<function=" in text:
        found.append(
            "the call stayed in the text: --tool-call-parser qwen3_coder or --enable-auto-tool-choice is missing"
        )
    elif not calls:
        found.append("no tool call: the agent answered in words")
    for c in calls:
        name = c["function"]["name"]
        if name != "examine_invoice":
            found.append(f"it called {name} instead of examine_invoice")
        try:
            json.loads(c["function"]["arguments"])
        except json.JSONDecodeError:
            found.append(f"the arguments of {name} are not valid JSON")
    if message.get("reasoning_content") or message.get("reasoning"):
        found.append(
            "there is a thought before the answer: --default-chat-template-kwargs '{\"enable_thinking\": false}' "
            "is missing"
        )
    return found


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--url", default="http://127.0.0.1:8000")
    parser.add_argument("--key", required=True, help="the vLLM --api-key")
    parser.add_argument("--model", default=MODEL)
    a = parser.parse_args()
    body = {"model": a.model, "messages": MESSAGES, "tools": [TOOL], "tool_choice": "auto"}
    request = urllib.request.Request(
        f"{a.url.rstrip('/')}/v1/chat/completions",
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {a.key}"},
    )
    start = time.perf_counter()
    with urllib.request.urlopen(request, timeout=300) as r:
        response = json.load(r)
    seconds = time.perf_counter() - start
    found = problems(response)
    for c in response["choices"][0]["message"].get("tool_calls") or []:
        print(f"call: {c['function']['name']}({c['function']['arguments']})")
    print(f"{seconds:.1f} s, {response.get('usage', {}).get('completion_tokens', '?')} tokens written")
    if found:
        print("\n".join(f"✗ {p}" for p in found))
        sys.exit(1)
    print("✓ endpoint ready for Evolus: tool call, JSON arguments, no thinking")


if __name__ == "__main__":
    main()
