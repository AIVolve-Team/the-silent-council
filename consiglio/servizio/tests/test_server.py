import base64

import httpx2
import pytest
from mcp import Client
from mcp.client.streamable_http import streamable_http_client
from starlette.testclient import TestClient

from revisore.gestore import chiave_del_caso
from revisore.server import crea_app

from .conftest import CONTRATTO, ESEMPIO, SEGRETO, email, pdf_con_testo

CHIAVE = {"Authorization": f"Bearer {SEGRETO}"}


@pytest.fixture
def app(revisore):
    return crea_app(revisore, SEGRETO)


@pytest.fixture
def anyio_backend():
    return "asyncio"


def test_senza_il_segreto_si_entra_solo_nella_salute(app):
    with TestClient(app) as http:
        assert http.get("/salute").json() == {"pronto": True, "esame_in_corso": False}
        assert http.post("/revisiona_contratto", json=email(testo=CONTRATTO)).status_code == 401
        assert http.get("/casi").status_code == 401
        assert http.post("/mcp", json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"}).status_code == 401
        sbagliato = {"X-Api-Key": "non-sono-io"}
        assert http.post("/revisiona_contratto", json=email(testo=CONTRATTO), headers=sbagliato).status_code == 401


@pytest.mark.anyio
async def test_mcp_e_http_danno_lo_stesso_caso(app, consiglio):
    async with app.router.lifespan_context(app):
        trasporto = httpx2.ASGITransport(app=app)
        async with httpx2.AsyncClient(transport=trasporto, base_url="http://127.0.0.1:8001", headers=CHIAVE) as http:
            via_http = (await http.post("/revisiona_contratto", json=email(testo=CONTRATTO))).json()
            async with Client(streamable_http_client("http://127.0.0.1:8001/mcp", http_client=http)) as mcp:
                strumenti = {t.name for t in (await mcp.list_tools()).tools}
                via_mcp = (await mcp.call_tool("revisiona_contratto", email(testo=CONTRATTO))).structured_content
                categoria = ESEMPIO["dissensi"][0]["categoria"]
                scelte = {"id_caso": via_http["id_caso"], "scelte": {categoria: "verdetto"}, "chi": "Evolus"}
                registrata = (await mcp.call_tool("registra_scelte", scelte)).structured_content

    assert strumenti == {"revisiona_contratto", "registra_scelte"}
    assert via_mcp == via_http and len(consiglio.chiamate) == 1
    assert registrata["registrate"] == 1


def test_il_pdf_in_un_modulo_e_i_campi_in_piu(app, consiglio):
    with TestClient(app) as http:
        modulo = http.post(
            "/revisiona_contratto?mittente=a%40example.org&data=2026-10-09",
            files={"allegato": ("contratto.pdf", pdf_con_testo("Il Fornitore fornisce"), "application/pdf")},
            data={"campo_di_evolus": "ignorato"},
            headers=CHIAVE,
        )
        base = http.post(
            "/revisiona_contratto", json=email(pdf_base64=base64.b64encode(b"%PDF-rotto").decode()), headers=CHIAVE
        )
        in_piu = http.post("/revisiona_contratto", json=email(testo=CONTRATTO, passi=40), headers=CHIAVE)
    assert modulo.status_code == 200 and "Il Fornitore fornisce" in consiglio.chiamate[0][1]
    assert base.status_code == 400 and in_piu.status_code == 400 and "passi" in in_piu.json()["errore"]


def test_un_guasto_del_consiglio_e_un_500_senza_dettagli(app, consiglio):
    consiglio.guasto = TypeError("dettaglio interno")
    with TestClient(app) as http:
        r = http.post("/revisiona_contratto", json=email(testo=CONTRATTO), headers=CHIAVE)
    assert r.status_code == 500 and "dettaglio" not in r.text and "persona" in r.json()["errore"]


def test_la_persona_apre_il_verdetto_e_manda_le_scelte_con_il_suo_link(app, revisore):
    with TestClient(app) as http:
        id_caso = http.post("/revisiona_contratto", json=email(testo=CONTRATTO), headers=CHIAVE).json()["id_caso"]
        chiave = chiave_del_caso(SEGRETO, id_caso)
        pagina = http.get(f"/verdetto/{id_caso}?chiave={chiave}")
        sbagliata = http.get(f"/verdetto/{id_caso}?chiave={'0' * 32}")
        inesistente = http.get(f"/verdetto/consiglio-000000000000?chiave={chiave}")
        categoria = ESEMPIO["dissensi"][0]["categoria"]
        scelte = http.post(f"/verdetto/{id_caso}/scelte?chiave={chiave}", json={"scelte": {categoria: "esperto"}})
        senza_chiave = http.post(f"/verdetto/{id_caso}/scelte", json={"scelte": {categoria: "esperto"}})
        caso = http.get(f"/casi/{id_caso}", headers=CHIAVE).json()
    assert pagina.status_code == 200 and pagina.headers["content-type"].startswith("text/html")
    assert sbagliata.status_code == inesistente.status_code == senza_chiave.status_code == 404
    assert scelte.status_code == 200 and caso["scelte"][0]["chi"] == "persona, dalla pagina del verdetto"
