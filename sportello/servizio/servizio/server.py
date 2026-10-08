"""Il server del motore: i due tool dello Sportello via MCP e via HTTP semplice, con lo stesso gestore.

Rotte:
- `POST /mcp`: MCP (Streamable HTTP, senza stato, risposte JSON) con i tool `esamina_fattura` e `registra_decisione`;
- `POST /esamina_fattura`, `POST /registra_decisione`: gli stessi tool in HTTP semplice, per il blocco "Call an endpoint"
  di Evolus se il connettore MCP nostro non c'è nella workspace dell'evento;
- `GET /casi`, `GET /casi/{id}`, `GET /casi/{id}/fattura.pdf`: elenco, vista e PDF dei casi, per la casa dei giudici;
- `GET /salute`: l'unica aperta, dice se il motore è pronto e se sta esaminando.

Tutte le altre chiedono il segreto, in `Authorization: Bearer <segreto>` oppure in `X-Api-Key: <segreto>`.
Il PDF arriva in base64 (`pdf_base64`), come file (`multipart/form-data`, campo `pdf`) oppure come link (`pdf_url`),
solo se il server è partito con l'elenco degli host da cui può scaricarlo.
"""

from __future__ import annotations

import base64
import binascii
import hmac
import inspect
import json
import logging
from typing import Any
from urllib.parse import urlsplit

import anyio.to_thread
import httpx2
from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.server.transport_security import TransportSecuritySettings
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from .gestore import MAX_PDF, Rifiuto, Sportello

log = logging.getLogger("sportello.servizio")
MAX_CORPO = 16 * 2**20  # un PDF di 10 MB in base64, più i campi
GUASTO = "motore: errore interno. Riprova una volta; se non risponde ancora, passa il caso a una persona."
ISTRUZIONI = (
    "Sportello telepatico: esamina le fatture in arrivo con agenti che si passano la memoria, controllati da una "
    "macchina della verità. Chiama esamina_fattura con il PDF originale dell'email. L'esito è pagare (una proposta in "
    "attesa di approvazione, mai un pagamento), persona o bloccare. Se frode_sospetta è vero non rispondere mai al "
    "mittente: la persona verifica con i contatti in anagrafica. Gli IBAN arrivano abbreviati e così vanno scritti."
)


class Segreto:
    """Middleware ASGI: senza il segreto si entra solo nelle rotte aperte."""

    def __init__(self, app, segreto: str, aperte: tuple[str, ...] = ("/salute",)) -> None:
        if not segreto:
            raise ValueError("serve un segreto")
        self.app, self.segreto, self.aperte = app, segreto.encode(), aperte

    async def __call__(self, scope, receive, send) -> None:
        if scope["type"] == "http" and scope["path"] not in self.aperte:
            intestazioni = dict(scope["headers"])
            autorizzazione = intestazioni.get(b"authorization", b"")
            chiave = (
                autorizzazione[7:] if autorizzazione[:7].lower() == b"bearer " else intestazioni.get(b"x-api-key", b"")
            )
            if not hmac.compare_digest(chiave.strip(), self.segreto):
                await JSONResponse({"errore": "serve il segreto"}, status_code=401)(scope, receive, send)
                return
        await self.app(scope, receive, send)


def scarica_pdf(url: str, host_pdf: frozenset[str]) -> bytes:
    """Il PDF da un link, solo https e solo dagli host ammessi, senza redirect e con un limite di dimensione."""
    parti = urlsplit(url)
    if parti.scheme != "https" or parti.hostname not in host_pdf:
        raise Rifiuto("pdf_url: link non ammesso")
    with httpx2.stream("GET", url, timeout=20, follow_redirects=False) as r:
        if r.status_code != 200:
            raise Rifiuto(f"pdf_url: il link risponde {r.status_code}")
        pdf = b""
        for pezzo in r.iter_bytes():
            pdf += pezzo
            if len(pdf) > MAX_PDF:
                raise Rifiuto("pdf_url: il PDF è troppo grande")
    return pdf


def pdf_da(pdf_base64: str | None, pdf_url: str | None, host_pdf: frozenset[str]) -> bytes:
    if bool(pdf_base64) == bool(pdf_url):
        raise Rifiuto("serve il PDF: pdf_base64 oppure pdf_url, uno solo")
    if pdf_url:
        return scarica_pdf(pdf_url, host_pdf)
    if len(pdf_base64) > MAX_CORPO:
        raise Rifiuto("pdf_base64: il PDF è troppo grande")
    try:
        return base64.b64decode(pdf_base64, validate=True)
    except (binascii.Error, ValueError) as errore:
        raise Rifiuto("pdf_base64: non è base64") from errore


async def corpo(request: Request) -> bytes:
    letto = b""
    async for pezzo in request.stream():
        letto += pezzo
        if len(letto) > MAX_CORPO:
            raise Rifiuto("richiesta troppo grande")
    return letto


async def campi(request: Request) -> dict:
    """JSON, oppure un modulo con il PDF come file nel campo `pdf`."""
    if int(request.headers.get("content-length") or 0) > MAX_CORPO:
        raise Rifiuto("richiesta troppo grande")
    if request.headers.get("content-type", "").startswith("multipart/form-data"):
        async with request.form(max_files=1, max_fields=10, max_part_size=MAX_CORPO) as modulo:
            dati = {k: v for k, v in modulo.items() if isinstance(v, str)}
            if (file := modulo.get("pdf")) is not None and not isinstance(file, str):
                dati["pdf_base64"] = base64.b64encode(await file.read()).decode()
            return dati
    try:
        dati = json.loads(await corpo(request))
    except ValueError as errore:
        raise Rifiuto("serve un oggetto JSON") from errore
    if not isinstance(dati, dict):
        raise Rifiuto("serve un oggetto JSON")
    return dati


def crea_app(
    sportello: Sportello, segreto: str, *, host_pubblici: tuple[str, ...] = (), host_pdf: tuple[str, ...] = ()
) -> Starlette:
    """`host_pubblici`: i nomi con cui il server si raggiunge da fuori (per esempio dietro Caddy con TLS); senza, MCP
    accetta solo richieste a 127.0.0.1 e localhost (protezione dal DNS rebinding dell'SDK)."""
    ammessi_pdf = frozenset(h.lower() for h in host_pdf)
    mcp = MCPServer("sportello", instructions=ISTRUZIONI)

    async def esamina(
        pdf_base64=None, pdf_url=None, mittente=None, oggetto="", data=None, modalita="telepatia"
    ) -> dict:
        pdf = await anyio.to_thread.run_sync(pdf_da, pdf_base64, pdf_url, ammessi_pdf)
        return await anyio.to_thread.run_sync(sportello.esamina_fattura, pdf, mittente, oggetto, data, modalita)

    async def decidi(id_caso=None, decisione=None, chi=None, nota="") -> dict:
        return await anyio.to_thread.run_sync(sportello.registra_decisione, id_caso, decisione, chi, nota)

    @mcp.tool(name="esamina_fattura", structured_output=True)
    async def esamina_fattura(
        mittente: str, oggetto: str, data: str, pdf_base64: str = "", pdf_url: str = "", modalita: str = "telepatia"
    ) -> dict[str, Any]:
        """Esamina il PDF originale di una fattura arrivata per email. pdf_base64 è il file in base64 (oppure pdf_url,
        un link al file); mittente, oggetto e data sono quelli dell'email; modalita è telepatia oppure testo. Restituisce
        id_caso, esito (pagare, persona o bloccare), motivo e motivi, proposta (solo se pagare), discordanze, sigillo,
        contatti_anagrafica, non_rispondere_al_mittente e link alla pagina del caso."""
        try:
            return await esamina(pdf_base64 or None, pdf_url or None, mittente, oggetto, data, modalita)
        except Rifiuto as errore:
            raise ToolError(str(errore)) from errore

    @mcp.tool(name="registra_decisione", structured_output=True)
    async def registra_decisione(id_caso: str, decisione: str, chi: str, nota: str = "") -> dict[str, Any]:
        """Registra la decisione della persona su un caso: decisione è approvato, rifiutato o segnalato; chi è la
        persona; nota è obbligatoria per rifiutare e per approvare un caso bloccato."""
        try:
            return await decidi(id_caso, decisione, chi, nota)
        except Rifiuto as errore:
            raise ToolError(str(errore)) from errore

    def http(azione):
        previsti = set(inspect.signature(azione).parameters)

        async def rotta(request: Request) -> Response:
            try:
                dati = await campi(request)
                if in_piu := sorted(set(dati) - previsti):
                    raise Rifiuto(f"campi non previsti: {', '.join(in_piu)}")
                return JSONResponse(await azione(**dati))
            except Rifiuto as errore:
                return JSONResponse({"errore": str(errore)}, status_code=400)
            except Exception:
                log.exception("guasto in %s", request.url.path)
                return JSONResponse({"errore": GUASTO}, status_code=500)

        return rotta

    mcp.custom_route("/esamina_fattura", methods=["POST"])(http(esamina))
    mcp.custom_route("/registra_decisione", methods=["POST"])(http(decidi))

    @mcp.custom_route("/casi", methods=["GET"])
    async def casi(request: Request) -> Response:
        return JSONResponse(await anyio.to_thread.run_sync(sportello.elenco))

    @mcp.custom_route("/casi/{id_caso}", methods=["GET"])
    async def caso(request: Request) -> Response:
        try:
            return JSONResponse(sportello.caso(request.path_params["id_caso"]))
        except Rifiuto as errore:
            return JSONResponse({"errore": str(errore)}, status_code=404)

    @mcp.custom_route("/casi/{id_caso}/fattura.pdf", methods=["GET"])
    async def fattura(request: Request) -> Response:
        try:
            cartella = sportello.cartella_di(request.path_params["id_caso"])
        except Rifiuto as errore:
            return JSONResponse({"errore": str(errore)}, status_code=404)
        return Response((cartella / "fattura.pdf").read_bytes(), media_type="application/pdf")

    @mcp.custom_route("/salute", methods=["GET"])
    async def salute(request: Request) -> Response:
        return JSONResponse({"pronto": True, "esame_in_corso": sportello.lucchetto.locked()})

    sicurezza = None
    if host_pubblici:
        sicurezza = TransportSecuritySettings(
            allowed_hosts=[*host_pubblici, *(f"{h}:*" for h in host_pubblici), "127.0.0.1:*", "localhost:*"],
            allowed_origins=[f"https://{h}" for h in host_pubblici],
        )
    app = mcp.streamable_http_app(
        stateless_http=True, json_response=True, max_request_body_size=MAX_CORPO, transport_security=sicurezza
    )
    app.add_middleware(Segreto, segreto=segreto)
    return app
