import base64

import httpx2
import pytest
from mcp import Client
from mcp.client.streamable_http import streamable_http_client
from starlette.testclient import TestClient

from reviewer.manager import case_key
from reviewer.server import create_app

from .conftest import CATALOG, CONTRACT, EXAMPLE, SECRET, email, pdf_with_text

AUTH = {"Authorization": f"Bearer {SECRET}"}


@pytest.fixture
def app(reviewer):
    return create_app(reviewer, SECRET)


@pytest.fixture
def anyio_backend():
    return "asyncio"


def test_without_the_secret_only_health_is_open(app):
    with TestClient(app) as http:
        assert http.get("/health").json() == {"ready": True, "review_in_progress": False, "live": False}
        assert http.post("/review_contract", json=email(text=CONTRACT)).status_code == 401
        assert http.get("/cases").status_code == 401
        assert http.post("/mcp", json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"}).status_code == 401
        wrong = {"X-Api-Key": "not-me"}
        assert http.post("/review_contract", json=email(text=CONTRACT), headers=wrong).status_code == 401


@pytest.mark.anyio
async def test_mcp_and_http_give_the_same_case(app, council):
    async with app.router.lifespan_context(app):
        transport = httpx2.ASGITransport(app=app)
        async with httpx2.AsyncClient(transport=transport, base_url="http://127.0.0.1:8001", headers=AUTH) as http:
            via_http = (await http.post("/review_contract", json=email(text=CONTRACT))).json()
            async with Client(streamable_http_client("http://127.0.0.1:8001/mcp", http_client=http)) as mcp:
                tools = {t.name for t in (await mcp.list_tools()).tools}
                via_mcp = (await mcp.call_tool("review_contract", email(text=CONTRACT))).structured_content
                category = EXAMPLE["dissents"][0]["category"]
                choices = {"case_id": via_http["case_id"], "choices": {category: "verdict"}, "who": "Evolus"}
                recorded = (await mcp.call_tool("record_choices", choices)).structured_content

    assert tools == {"review_contract", "record_choices"}
    assert via_mcp == via_http and len(council.calls) == 1
    assert recorded["recorded"] == 1


def test_the_pdf_in_a_form_and_the_extra_fields(app, council):
    with TestClient(app) as http:
        form = http.post(
            "/review_contract?sender=a%40example.org&date=2026-10-09",
            files={"attachment": ("contract.pdf", pdf_with_text("Il Fornitore fornisce"), "application/pdf")},
            data={"evolus_field": "ignored"},
            headers=AUTH,
        )
        b64 = http.post(
            "/review_contract", json=email(pdf_base64=base64.b64encode(b"%PDF-broken").decode()), headers=AUTH
        )
        extra = http.post("/review_contract", json=email(text=CONTRACT, steps=40), headers=AUTH)
    assert form.status_code == 200 and "Il Fornitore fornisce" in council.calls[0][1]
    assert b64.status_code == 400 and extra.status_code == 400 and "steps" in extra.json()["error"]


def test_the_evolus_pdf_without_a_field_name(app, council):
    # Evolus's «Chiama un endpoint» sends the trigger's files without `name` in the Content-Disposition.
    boundary = "evolus-boundary"
    body = b"".join(
        [
            f'--{boundary}\r\nContent-Disposition: form-data; name="input"\r\n\r\nthe email text\r\n'.encode(),
            f'--{boundary}\r\nContent-Disposition: form-data; filename="contract.pdf"\r\n'.encode(),
            b"Content-Type: application/pdf\r\n\r\n" + pdf_with_text("Il Fornitore fornisce") + b"\r\n",
            f"--{boundary}--\r\n".encode(),
        ]
    )
    with TestClient(app) as http:
        r = http.post(
            "/review_contract",
            content=body,
            headers=AUTH | {"Content-Type": f"multipart/form-data; boundary={boundary}"},
        )
    assert r.status_code == 200 and "Il Fornitore fornisce" in council.calls[0][1]


def test_the_evolus_text_in_the_body_part_or_without_a_name(app, council):
    # In Evolus an endpoint only receives text: the PDF goes through «Leggi il documento», which sends its text in the
    # `body` part or in a part without a name. An empty part is still a missing contract.
    def form(text: str, header: str = "") -> dict:
        boundary = "evolus-boundary"
        body = f"--{boundary}\r\n{header}\r\n{text}\r\n--{boundary}--\r\n".encode()
        return {"content": body, "headers": AUTH | {"Content-Type": f'multipart/form-data; boundary="{boundary}"'}}

    with TestClient(app) as http:
        read = http.post("/review_contract", **form(CONTRACT))
        in_body = http.post(
            "/review_contract", **form(CONTRACT + "Art. 2", 'Content-Disposition: form-data; name="body"\r\n')
        )
        empty = http.post("/review_contract", **form(""))
    assert read.status_code == 200 and council.calls[0][1] == CONTRACT
    assert in_body.status_code == 200 and council.calls[1][1] == CONTRACT + "Art. 2"
    assert empty.status_code == 400 and "the contract is required" in empty.json()["error"]


def test_a_council_failure_is_a_500_without_details(app, council):
    council.failure = TypeError("internal detail")
    with TestClient(app) as http:
        r = http.post("/review_contract", json=email(text=CONTRACT), headers=AUTH)
    assert r.status_code == 500 and "detail" not in r.text and "person" in r.json()["error"]


def test_the_person_opens_the_verdict_and_sends_the_choices_with_their_link(app, reviewer):
    with TestClient(app) as http:
        case_id = http.post("/review_contract", json=email(text=CONTRACT), headers=AUTH).json()["case_id"]
        key = case_key(SECRET, case_id)
        page = http.get(f"/verdict/{case_id}?key={key}")
        wrong = http.get(f"/verdict/{case_id}?key={'0' * 32}")
        missing = http.get(f"/verdict/council-000000000000?key={key}")
        category = EXAMPLE["dissents"][0]["category"]
        choices = http.post(f"/verdict/{case_id}/choices?key={key}", json={"choices": {category: "expert"}})
        without_key = http.post(f"/verdict/{case_id}/choices", json={"choices": {category: "expert"}})
        case = http.get(f"/cases/{case_id}", headers=AUTH).json()
    assert page.status_code == 200 and page.headers["content-type"].startswith("text/html")
    assert wrong.status_code == missing.status_code == without_key.status_code == 404
    assert choices.status_code == 200 and case["choices"][0]["who"] == "person, from the verdict page"


def test_live_reviews_only_with_the_catalog_and_with_the_secret(reviewer, live):
    with TestClient(create_app(reviewer, SECRET)) as http:
        assert http.get("/live/contracts", headers=AUTH).status_code == 404
    with TestClient(create_app(live, SECRET)) as http:
        assert http.get("/health").json()["live"] is True
        assert http.get("/live/contracts").status_code == 401
        listing = http.get("/live/contracts", headers=AUTH).json()
        assert [c["key"] for c in listing] == list(CATALOG) and "text" not in listing[0]
        assert http.post("/live/contract", json={"contract": "cuad:other"}, headers=AUTH).status_code == 400
        extra = http.post("/live/contract", json={"contract": next(iter(CATALOG)), "text": "x"}, headers=AUTH)
        assert extra.status_code == 400 and "unexpected fields" in extra.json()["error"]
        r = http.post("/live/contract", json={"contract": next(iter(CATALOG)), "mode": "text"}, headers=AUTH)
        assert r.status_code == 200 and r.json()["view"]["comparison"]["name"] == "CUAD"


def test_one_live_review_at_a_time(live):
    with TestClient(create_app(live, SECRET)) as http:
        with live.lock:
            r = http.post("/live/contract", json={"contract": next(iter(CATALOG))}, headers=AUTH)
        assert r.status_code == 409 and "try again" in r.json()["error"]
