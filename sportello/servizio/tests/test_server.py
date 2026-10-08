import base64

import httpx2
import pytest
from mcp import Client
from mcp.client.streamable_http import streamable_http_client
from starlette.testclient import TestClient

from servizio.server import crea_app

SEGRETO = "segreto-di-prova"


@pytest.fixture
def app(sportello):
    return crea_app(sportello, SEGRETO)


@pytest.fixture
def anyio_backend():
    return "asyncio"


def argomenti(pdf, caso):
    e = caso.email
    return {
        "pdf_base64": base64.b64encode(pdf).decode(),
        "mittente": e["mittente"],
        "oggetto": e["oggetto"],
        "data": e["data"],
    }


def test_senza_il_segreto_si_entra_solo_nella_salute(app, pdf_pulita, pulita):
    with TestClient(app) as http:
        assert http.get("/salute").status_code == 200
        assert http.post("/esamina_fattura", json=argomenti(pdf_pulita, pulita)).status_code == 401
        assert http.post("/mcp", json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"}).status_code == 401
        sbagliato = {"Authorization": "Bearer non-sono-io"}
        assert http.post("/esamina_fattura", json=argomenti(pdf_pulita, pulita), headers=sbagliato).status_code == 401


@pytest.mark.anyio
async def test_mcp_e_http_danno_lo_stesso_caso(app, pipeline, pdf_pulita, pulita):
    chiave = {"Authorization": f"Bearer {SEGRETO}"}
    async with app.router.lifespan_context(app):
        trasporto = httpx2.ASGITransport(app=app)
        async with httpx2.AsyncClient(transport=trasporto, base_url="http://127.0.0.1:8000", headers=chiave) as http:
            via_http = (await http.post("/esamina_fattura", json=argomenti(pdf_pulita, pulita))).json()
            async with Client(streamable_http_client("http://127.0.0.1:8000/mcp", http_client=http)) as mcp:
                strumenti = {t.name for t in (await mcp.list_tools()).tools}
                via_mcp = (await mcp.call_tool("esamina_fattura", argomenti(pdf_pulita, pulita))).structured_content

    assert strumenti == {"esamina_fattura", "registra_decisione"}
    assert via_mcp == via_http
    assert via_http["esito"] == "pagare"
    assert len(pipeline.chiamate) == 1


def test_una_decisione_contro_le_regole_torna_400_con_il_motivo(app, pdf_frode, frode):
    chiave = {"Authorization": f"Bearer {SEGRETO}"}
    with TestClient(app) as http:
        id_caso = http.post("/esamina_fattura", json=argomenti(pdf_frode, frode), headers=chiave).json()["id_caso"]
        r = http.post(
            "/registra_decisione", json={"id_caso": id_caso, "decisione": "approvato", "chi": "giudice"}, headers=chiave
        )

    assert r.status_code == 400
    assert "anagrafica" in r.json()["errore"]


def test_un_guasto_del_motore_e_un_500_senza_dettagli_e_un_campo_in_piu_e_un_400(app, pipeline, pdf_pulita, pulita):
    chiave = {"Authorization": f"Bearer {SEGRETO}"}
    with TestClient(app) as http:
        in_piu = http.post("/esamina_fattura", json=argomenti(pdf_pulita, pulita) | {"livello2": False}, headers=chiave)
        pipeline.guasto = TypeError("dettaglio interno")
        guasto = http.post("/esamina_fattura", json=argomenti(pdf_pulita, pulita), headers=chiave)

    assert in_piu.status_code == 400
    assert guasto.status_code == 500
    assert "dettaglio" not in guasto.text
    assert "persona" in guasto.json()["errore"]


@pytest.mark.parametrize(
    "url", ["https://169.254.169.254/latest/meta-data", "http://file.evolus.example/f.pdf", "file:///etc/passwd"]
)
def test_il_pdf_si_scarica_solo_in_https_dagli_host_ammessi(sportello, pipeline, pulita, url):
    app = crea_app(sportello, SEGRETO, host_pdf=("file.evolus.example",))
    campi = argomenti(b"", pulita) | {"pdf_base64": "", "pdf_url": url}
    with TestClient(app) as http:
        r = http.post("/esamina_fattura", json=campi, headers={"Authorization": f"Bearer {SEGRETO}"})

    assert r.status_code == 400
    assert "non ammesso" in r.json()["errore"]
    assert pipeline.chiamate == []
