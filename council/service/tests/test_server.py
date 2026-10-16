import base64

import httpx2
import pytest
from mcp import Client
from mcp.client.streamable_http import streamable_http_client
from starlette.testclient import TestClient

from revisore.gestore import chiave_del_caso
from revisore.server import crea_app

from .conftest import CATALOGO, CONTRATTO, ESEMPIO, SEGRETO, email, pdf_con_testo

CHIAVE = {"Authorization": f"Bearer {SEGRETO}"}


@pytest.fixture
def app(revisore):
    return crea_app(revisore, SEGRETO)


@pytest.fixture
def anyio_backend():
    return "asyncio"


def test_senza_il_segreto_si_entra_solo_nella_salute(app):
    with TestClient(app) as http:
        assert http.get("/salute").json() == {"pronto": True, "esame_in_corso": False, "prove": False}
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


def test_il_pdf_di_evolus_senza_nome_del_campo(app, consiglio):
    # «Chiama un endpoint» di Evolus manda i file della partenza senza `name` nel Content-Disposition.
    confine = "confine-di-evolus"
    corpo = b"".join(
        [
            f'--{confine}\r\nContent-Disposition: form-data; name="input"\r\n\r\ntesto dell\'email\r\n'.encode(),
            f'--{confine}\r\nContent-Disposition: form-data; filename="contratto.pdf"\r\n'.encode(),
            b"Content-Type: application/pdf\r\n\r\n" + pdf_con_testo("Il Fornitore fornisce") + b"\r\n",
            f"--{confine}--\r\n".encode(),
        ]
    )
    with TestClient(app) as http:
        r = http.post(
            "/revisiona_contratto",
            content=corpo,
            headers=CHIAVE | {"Content-Type": f"multipart/form-data; boundary={confine}"},
        )
    assert r.status_code == 200 and "Il Fornitore fornisce" in consiglio.chiamate[0][1]


def test_il_testo_di_evolus_nella_parte_body_o_senza_nome(app, consiglio):
    # In Evolus un endpoint riceve solo testo: il PDF passa da «Leggi il documento», che ne manda il testo nella parte
    # `body` o in una parte senza nome. Una parte vuota resta un contratto che manca.
    def modulo(testo: str, intestazione: str = "") -> dict:
        confine = "confine-di-evolus"
        corpo = f"--{confine}\r\n{intestazione}\r\n{testo}\r\n--{confine}--\r\n".encode()
        return {"content": corpo, "headers": CHIAVE | {"Content-Type": f'multipart/form-data; boundary="{confine}"'}}

    with TestClient(app) as http:
        letto = http.post("/revisiona_contratto", **modulo(CONTRATTO))
        nel_body = http.post(
            "/revisiona_contratto", **modulo(CONTRATTO + "Art. 2", 'Content-Disposition: form-data; name="body"\r\n')
        )
        vuoto = http.post("/revisiona_contratto", **modulo(""))
    assert letto.status_code == 200 and consiglio.chiamate[0][1] == CONTRATTO
    assert nel_body.status_code == 200 and consiglio.chiamate[1][1] == CONTRATTO + "Art. 2"
    assert vuoto.status_code == 400 and "serve il contratto" in vuoto.json()["errore"]


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


def test_prove_dal_vivo_solo_con_il_catalogo_e_con_il_segreto(revisore, dal_vivo):
    with TestClient(crea_app(revisore, SEGRETO)) as http:
        assert http.get("/prove/contratti", headers=CHIAVE).status_code == 404
    with TestClient(crea_app(dal_vivo, SEGRETO)) as http:
        assert http.get("/salute").json()["prove"] is True
        assert http.get("/prove/contratti").status_code == 401
        elenco = http.get("/prove/contratti", headers=CHIAVE).json()
        assert [c["chiave"] for c in elenco] == list(CATALOGO) and "testo" not in elenco[0]
        assert http.post("/prove/contratto", json={"contratto": "cuad:altro"}, headers=CHIAVE).status_code == 400
        inpiu = http.post("/prove/contratto", json={"contratto": next(iter(CATALOGO)), "testo": "x"}, headers=CHIAVE)
        assert inpiu.status_code == 400 and "campi non previsti" in inpiu.json()["errore"]
        r = http.post("/prove/contratto", json={"contratto": next(iter(CATALOGO)), "modalita": "testo"}, headers=CHIAVE)
        assert r.status_code == 200 and r.json()["vista"]["confronto"]["nome"] == "CUAD"


def test_una_prova_dal_vivo_alla_volta(dal_vivo):
    with TestClient(crea_app(dal_vivo, SEGRETO)) as http:
        with dal_vivo.lucchetto:
            r = http.post("/prove/contratto", json={"contratto": next(iter(CATALOGO))}, headers=CHIAVE)
        assert r.status_code == 409 and "riprova" in r.json()["errore"]
