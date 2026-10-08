import httpx2
import pytest

from servizio.chiama import prova_completa
from servizio.server import crea_app

SEGRETO = "segreto-di-prova"


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.mark.anyio
async def test_il_cliente_chiama_il_motore_come_l_agente_e_trova_lo_stesso_caso(
    sportello, pipeline, pdf_pulita, pulita
):
    app = crea_app(sportello, SEGRETO)
    async with app.router.lifespan_context(app):
        trasporto = httpx2.ASGITransport(app=app)
        async with httpx2.AsyncClient(transport=trasporto, base_url="http://127.0.0.1:8000") as http:
            esito = await prova_completa("http://127.0.0.1:8000", pdf_pulita, pulita.email, SEGRETO, http=http)

    assert esito["uguali"] is True
    assert esito["mcp"]["esito"] == "pagare"
    assert esito["decisione"]["registrata"] is True
    assert len(pipeline.chiamate) == 1  # la seconda chiamata trova il caso già esaminato
