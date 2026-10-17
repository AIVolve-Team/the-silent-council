"""The council's server for Evolus: the tools via MCP and via plain HTTP, with the same manager.

The scheme is the one of the Help Desk's server: stateless MCP with JSON responses, the same routes in HTTP, the
secret in `Authorization: Bearer <secret>` or `X-Api-Key: <secret>`.

Routes with the secret (Evolus):
- `POST /mcp`: MCP with the tools `review_contract`, `record_choices` and `ask_council`;
- `POST /review_contract`, `POST /record_choices`, `POST /ask_council`: the same tools in HTTP. The contract arrives
  as text (`text`), in base64 (`pdf_base64`) or as a PDF file in a form (`multipart/form-data`): the MCP connector
  only carries the text the model writes, never the file;
- `GET /cases`, `GET /cases/{case_id}`: list of the cases, view and choices.

The person's routes, with the key of their link and without the secret:
- `GET /verdict/{case_id}?key=…`: the verdict page;
- `POST /verdict/{case_id}/choices?key=…`: the choices on the dissents, from the page.

Routes of the judges' live reviews, with the secret, only with the catalog on (`--live`):
- `GET /live/contracts`: the contracts the judge can choose;
- `POST /live/contract`: `{"contract": "<benchmark>:<id>", "mode": "telepathy"}`, reviewed now; 409 if the council is
  already busy.

`GET /health` is open: it says whether the council is reviewing a contract and whether live reviews are on.
"""

from __future__ import annotations

import base64
import binascii
import hmac
import inspect
import json
import logging
from datetime import UTC, datetime
from typing import Any

import anyio.to_thread
from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.server.transport_security import TransportSecuritySettings
from python_multipart.exceptions import MultipartParseError
from python_multipart.multipart import MultipartParser, parse_options_header
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import HTMLResponse, JSONResponse, Response

from .manager import Busy, Rejected, Reviewer

log = logging.getLogger("council.service")
MAX_BODY = 16 * 2**20  # a 10 MB PDF in base64, plus the fields
MAX_FILES = 5
EVOLUS_TEXT = (None, "body")  # where Evolus's «Chiama un endpoint» puts the text it receives
FAILURE = "Council: internal error. Try once more; if it still does not answer, hand the contract to a person."
INSTRUCTIONS = (
    "Silent Council: four agents (legal, finance, risk and a devil's advocate rapporteur) review a contract by handing "
    "each other their memory instead of text. Call review_contract with the contract attached to the email (the PDF in "
    "base64, or the text). It returns the recommendation (sign, negotiate or do not sign), the flagged clauses, the "
    "major dissents between experts and verdict, the link to the verdict page and the notice to send as is to the "
    "person. If verdict is false, the contract goes to a person. The person's choices on the dissents are recorded "
    "with record_choices. To ask something about a contract already reviewed (for example who signed, or the notice "
    "period), call ask_council with its case_id: the council answers from the memory of that review, without reading "
    "the contract again."
)
OPEN = ("/health",)
PERSON = "/verdict/"


class Secret:
    """ASGI middleware: without the secret only the open routes and the person's routes are reachable; the latter
    check the case key themselves."""

    def __init__(self, app, secret: str) -> None:
        if not secret:
            raise ValueError("a secret is required")
        self.app, self.secret = app, secret.encode()

    async def __call__(self, scope, receive, send) -> None:
        path = scope.get("path", "")
        if scope["type"] == "http" and path not in OPEN and not path.startswith(PERSON):
            headers = dict(scope["headers"])
            authorization = headers.get(b"authorization", b"")
            key = authorization[7:] if authorization[:7].lower() == b"bearer " else headers.get(b"x-api-key", b"")
            if not hmac.compare_digest(key.strip(), self.secret):
                await JSONResponse({"error": "the secret is required"}, status_code=401)(scope, receive, send)
                return
        await self.app(scope, receive, send)


def pdf_from_base64(pdf_base64: str) -> bytes:
    if len(pdf_base64) > MAX_BODY:
        raise Rejected("pdf_base64: the PDF is too large")
    try:
        return base64.b64decode(pdf_base64, validate=True)
    except (binascii.Error, ValueError) as error:
        raise Rejected("pdf_base64: not base64") from error


async def body(request: Request) -> bytes:
    read = b""
    async for chunk in request.stream():
        read += chunk
        if len(read) > MAX_BODY:
            raise Rejected("request too large")
    return read


def form_parts(content: bytes, content_type: str) -> list[tuple[str | None, str | None, bytes]]:
    """The parts of a `multipart/form-data` form: (name, file name, content). The name can be missing: Evolus's «Chiama
    un endpoint» sends the trigger's files without `name`, which Starlette's parser rejects."""
    _, options = parse_options_header(content_type)
    boundary = options.get(b"boundary")
    if not boundary:
        raise Rejected("form without boundary")
    parts: list[tuple[str | None, str | None, bytes]] = []
    state: dict = {}

    def begin() -> None:
        state.update(headers={}, field=b"", value=b"", data=[])

    def header_end() -> None:
        state["headers"][state["field"].lower()] = state["value"]
        state["field"], state["value"] = b"", b""

    def end() -> None:
        if len(parts) >= MAX_FILES + 20:
            raise Rejected("form with too many parts")
        _, disposition = parse_options_header(state["headers"].get(b"content-disposition", b""))
        name, file = disposition.get(b"name"), disposition.get(b"filename")
        parts.append(
            (
                name.decode("utf-8", "replace") if name is not None else None,
                file.decode("utf-8", "replace") if file is not None else None,
                b"".join(state["data"]),
            )
        )

    parser = MultipartParser(
        boundary,
        {
            "on_part_begin": begin,
            "on_header_field": lambda d, a, b: state.update(field=state["field"] + d[a:b]),
            "on_header_value": lambda d, a, b: state.update(value=state["value"] + d[a:b]),
            "on_header_end": header_end,
            "on_part_data": lambda d, a, b: state["data"].append(d[a:b]),
            "on_part_end": end,
        },
    )
    try:
        parser.write(content)
        parser.finalize()
    except MultipartParseError as error:
        raise Rejected("the form cannot be read") from error
    return parts


async def fields(request: Request) -> tuple[dict, bool]:
    """JSON, or a form with the contract as a PDF file (the `contract` field, or the first file that is a PDF, because
    Evolus's «Chiama un endpoint» does not document the names and sometimes leaves them out). Without a PDF, the
    contract is the text of the `body` part or of a part without a name: in Evolus an endpoint only receives text, and
    the PDF arrives there already read by «Leggi il documento». The second value says whether it was a form."""
    if int(request.headers.get("content-length") or 0) > MAX_BODY:
        raise Rejected("request too large")
    content_type = request.headers.get("content-type", "")
    if content_type.startswith("multipart/form-data"):
        parts = form_parts(await body(request), content_type)
        data = {name: v.decode("utf-8", "replace") for name, file, v in parts if name and file is None}
        pdf = [v for name, file, v in parts if name == "contract"] + [
            v for name, file, v in parts if name != "contract"
        ]
        if content := next((v for v in pdf if v.startswith(b"%PDF")), None):
            data["pdf_base64"] = base64.b64encode(content).decode()
        elif "text" not in data and (
            text := next((v for name, file, v in parts if name in EVOLUS_TEXT and file is None and v.strip()), None)
        ):
            data["text"] = text.decode("utf-8", "replace")
        return data, True
    try:
        data = json.loads(await body(request))
    except ValueError as error:
        raise Rejected("a JSON object is required") from error
    if not isinstance(data, dict):
        raise Rejected("a JSON object is required")
    return data, False


def create_app(reviewer: Reviewer, secret: str, *, public_hosts: tuple[str, ...] = ()) -> Starlette:
    """`public_hosts`: the names the server is reached by from outside; without them, MCP only accepts requests to
    127.0.0.1 and localhost (the SDK's DNS rebinding protection)."""
    mcp = MCPServer("council", instructions=INSTRUCTIONS)

    async def review(text=None, pdf_base64=None, sender=None, subject="", date=None, mode="telepathy") -> dict:
        contract = None
        if pdf_base64:
            contract = await anyio.to_thread.run_sync(pdf_from_base64, pdf_base64)
        return await anyio.to_thread.run_sync(
            reviewer.review_contract, contract, text or None, sender, subject, date, mode
        )

    async def choose(case_id=None, choices=None, who=None, reasons=None, corrections=None, instruction=None) -> dict:
        return await anyio.to_thread.run_sync(
            reviewer.record_choices, case_id, choices, who, reasons, corrections, instruction
        )

    async def ask(case_id=None, question=None, who="agent") -> dict:
        return await anyio.to_thread.run_sync(reviewer.ask_council, case_id, question, who)

    @mcp.tool(name="review_contract", structured_output=True)
    async def review_contract(
        sender: str, subject: str, date: str, text: str = "", pdf_base64: str = "", mode: str = "telepathy"
    ) -> dict[str, Any]:
        """Has the council review the contract attached to an email. pdf_base64 is the PDF in base64, or text is the
        contract's text (only one); sender, subject and date are those of the email; mode is telepathy or text.
        Returns case_id, verdict, recommendation, flagged, major_dissents, seal_intact, link to the verdict page and
        notice (subject and text of the email for the person, to send as is)."""
        try:
            return await review(text, pdf_base64, sender, subject, date, mode)
        except Rejected as error:
            raise ToolError(str(error)) from error

    @mcp.tool(name="record_choices", structured_output=True)
    async def record_choices(
        case_id: str,
        who: str,
        choices: dict[str, str] | None = None,
        reasons: dict[str, str] | None = None,
        corrections: dict[str, bool] | None = None,
        instruction: str = "",
    ) -> dict[str, Any]:
        """Records what the person decided on a case: choices maps a category in dissent to "expert" or "verdict";
        corrections maps a category without a dissent to true (flag it) or false (do not flag it) where the verdict is
        wrong; reasons maps some of those categories to why; instruction is a rule for the next contracts. who is the
        person. With the institutional memory on, the council learns all of it."""
        try:
            return await choose(case_id, choices, who, reasons, corrections, instruction or None)
        except Rejected as error:
            raise ToolError(str(error)) from error

    @mcp.tool(name="ask_council", structured_output=True)
    async def ask_council(case_id: str, question: str, who: str = "agent") -> dict[str, Any]:
        """Asks the council a question on a contract it already reviewed, for example "who signed?" or "is there a cap
        on liability?". It answers from the memory of that review, without reading the contract again: answer, the
        quote that supports it and known (false if the memory does not tell). If the memory of the case is no longer on
        the server, the contract must be reviewed again."""
        try:
            return await ask(case_id, question, who)
        except Rejected as error:
            raise ToolError(str(error)) from error

    def http(action, from_query: tuple[str, ...] = (), in_form: dict | None = None):
        expected = set(inspect.signature(action).parameters)

        async def route(request: Request) -> Response:
            try:
                data, from_form = await fields(request)
                if from_form:  # Evolus's extra fields are ignored, never used
                    data = {k: v for k, v in data.items() if k in expected}
                elif extra := sorted(set(data) - expected):
                    raise Rejected(f"unexpected fields: {', '.join(extra)}")
                data = {k: v for k, v in request.query_params.items() if k in from_query} | data
                if from_form and in_form:
                    data = {k: v() for k, v in in_form.items()} | {k: v for k, v in data.items() if v}
                return JSONResponse(await action(**data))
            except Rejected as error:
                return JSONResponse({"error": str(error)}, status_code=400)
            except Exception:
                log.exception("failure in %s", request.url.path)
                return JSONResponse({"error": FAILURE}, status_code=500)

        return route

    if_missing = {
        "sender": lambda: "(unknown)",
        "subject": str,
        "date": lambda: datetime.now(UTC).date().isoformat(),
    }
    mcp.custom_route("/review_contract", methods=["POST"])(
        http(review, ("sender", "subject", "date", "mode"), if_missing)
    )
    mcp.custom_route("/record_choices", methods=["POST"])(http(choose))
    mcp.custom_route("/ask_council", methods=["POST"])(http(ask))

    @mcp.custom_route("/cases", methods=["GET"])
    async def cases(request: Request) -> Response:
        return JSONResponse(await anyio.to_thread.run_sync(reviewer.listing))

    @mcp.custom_route("/cases/{case_id}", methods=["GET"])
    async def case(request: Request) -> Response:
        try:
            return JSONResponse(reviewer.case(request.path_params["case_id"]))
        except Rejected as error:
            return JSONResponse({"error": str(error)}, status_code=404)

    def of_the_person(request: Request) -> str:
        """The case id, if the link's key is right. Same answer for a missing case and a wrong key."""
        case_id = request.path_params["case_id"]
        if not reviewer.key_is_valid(case_id, request.query_params.get("key", "")):
            raise Rejected("invalid link")
        reviewer.folder_of(case_id)
        return case_id

    @mcp.custom_route("/verdict/{case_id}", methods=["GET"])
    async def verdict(request: Request) -> Response:
        try:
            return HTMLResponse(reviewer.page_of(of_the_person(request)))
        except Rejected:
            return JSONResponse({"error": "invalid link"}, status_code=404)

    @mcp.custom_route("/verdict/{case_id}/choices", methods=["POST"])
    async def choices_of_the_person(request: Request) -> Response:
        try:
            case_id = of_the_person(request)
        except Rejected:
            return JSONResponse({"error": "invalid link"}, status_code=404)
        try:
            data, _ = await fields(request)
            who = "person, from the verdict page"
            taught = [data.get(k) for k in ("reasons", "corrections", "instruction")]
            return JSONResponse(await choose(case_id, data.get("choices"), who, *taught))
        except Rejected as error:
            return JSONResponse({"error": str(error)}, status_code=400)

    if reviewer.catalog is not None:

        @mcp.custom_route("/live/contracts", methods=["GET"])
        async def live_contracts(request: Request) -> Response:
            return JSONResponse(reviewer.live_contracts())

        @mcp.custom_route("/live/contract", methods=["POST"])
        async def live_contract(request: Request) -> Response:
            try:
                data, _ = await fields(request)
                if extra := sorted(set(data) - {"contract", "mode"}):
                    raise Rejected(f"unexpected fields: {', '.join(extra)}")
                return JSONResponse(
                    await anyio.to_thread.run_sync(
                        reviewer.live_review, data.get("contract"), data.get("mode", "telepathy")
                    )
                )
            except Busy as error:
                return JSONResponse({"error": str(error)}, status_code=409)
            except Rejected as error:
                return JSONResponse({"error": str(error)}, status_code=400)
            except Exception:
                log.exception("failure in a live review")
                return JSONResponse({"error": FAILURE}, status_code=500)

    @mcp.custom_route("/health", methods=["GET"])
    async def health(request: Request) -> Response:
        return JSONResponse(
            {"ready": True, "review_in_progress": reviewer.lock.locked(), "live": reviewer.catalog is not None}
        )

    security = None
    if public_hosts:
        security = TransportSecuritySettings(
            allowed_hosts=[*public_hosts, *(f"{h}:*" for h in public_hosts), "127.0.0.1:*", "localhost:*"],
            allowed_origins=[f"https://{h}" for h in public_hosts],
        )
    app = mcp.streamable_http_app(
        stateless_http=True, json_response=True, max_request_body_size=MAX_BODY, transport_security=security
    )
    app.add_middleware(Secret, secret=secret)
    return app
