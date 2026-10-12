"""Il server del Consiglio per Evolus: i due tool via MCP e via HTTP semplice, con lo stesso gestore.

Lo schema è quello del server dello Sportello: MCP senza stato con risposte JSON, le stesse rotte in HTTP, il
segreto in `Authorization: Bearer <segreto>` oppure `X-Api-Key: <segreto>`.

Rotte con il segreto (Evolus):
- `POST /mcp`: MCP con i tool `revisiona_contratto` e `registra_scelte`;
- `POST /revisiona_contratto`, `POST /registra_scelte`: gli stessi tool in HTTP. Il contratto arriva come testo
  (`testo`), in base64 (`pdf_base64`) oppure come file PDF in un modulo (`multipart/form-data`): il connettore MCP porta
  solo il testo che scrive il modello, mai il file;
- `GET /casi`, `GET /casi/{id}`: elenco dei casi, vista e scelte.

Rotte della persona, con la chiave del suo link e senza segreto:
- `GET /verdetto/{id}?chiave=…`: la pagina del verdetto;
- `POST /verdetto/{id}/scelte?chiave=…`: le scelte sui dissensi, dalla pagina.

Rotte delle prove dal vivo dei giudici, con il segreto, solo con il catalogo acceso (`--dal-vivo`):
- `GET /prove/contratti`: i contratti che il giudice può scegliere;
- `POST /prove/contratto`: `{"contratto": "<benchmark>:<id>", "modalita": "telepatia"}`, esaminato adesso; 409 se il
  Consiglio è già occupato.

`GET /salute` è aperta: dice se il Consiglio sta esaminando un contratto e se le prove dal vivo sono accese.
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
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import HTMLResponse, JSONResponse, Response

from .gestore import Occupato, Revisore, Rifiuto

log = logging.getLogger("consiglio.servizio")
MAX_CORPO = 16 * 2**20  # un PDF di 10 MB in base64, più i campi
MAX_FILE = 5
GUASTO = "Consiglio: errore interno. Riprova una volta; se non risponde ancora, passa il contratto a una persona."
ISTRUZIONI = (
    "Consiglio silenzioso: quattro agenti (legale, finanza, rischio e un relatore avvocato del diavolo) rivedono un "
    "contratto passandosi la memoria invece del testo. Chiama revisiona_contratto con il contratto allegato all'email "
    "(il PDF in base64, oppure il testo). Restituisce la raccomandazione (firmare, negoziare o non firmare), le clausole "
    "segnalate, i dissensi gravi fra esperti e verdetto, il link alla pagina del verdetto e l'avviso da mandare così "
    "com'è alla persona. Se verdetto è falso, il contratto va a una persona. Le scelte della persona sui dissensi si "
    "registrano con registra_scelte."
)
APERTE = ("/salute",)
DELLA_PERSONA = "/verdetto/"


class Segreto:
    """Middleware ASGI: senza il segreto si entra solo nelle rotte aperte e in quelle della persona, che controllano
    da sole la chiave del caso."""

    def __init__(self, app, segreto: str) -> None:
        if not segreto:
            raise ValueError("serve un segreto")
        self.app, self.segreto = app, segreto.encode()

    async def __call__(self, scope, receive, send) -> None:
        percorso = scope.get("path", "")
        if scope["type"] == "http" and percorso not in APERTE and not percorso.startswith(DELLA_PERSONA):
            intestazioni = dict(scope["headers"])
            autorizzazione = intestazioni.get(b"authorization", b"")
            chiave = (
                autorizzazione[7:] if autorizzazione[:7].lower() == b"bearer " else intestazioni.get(b"x-api-key", b"")
            )
            if not hmac.compare_digest(chiave.strip(), self.segreto):
                await JSONResponse({"errore": "serve il segreto"}, status_code=401)(scope, receive, send)
                return
        await self.app(scope, receive, send)


def pdf_da_base64(pdf_base64: str) -> bytes:
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


async def campi(request: Request) -> tuple[dict, bool]:
    """JSON, oppure un modulo con il contratto come file PDF (il campo `contratto`, oppure il primo file che è un PDF,
    perché «Call an endpoint» di Evolus non documenta i nomi). Il secondo valore dice se era un modulo."""
    if int(request.headers.get("content-length") or 0) > MAX_CORPO:
        raise Rifiuto("richiesta troppo grande")
    if request.headers.get("content-type", "").startswith("multipart/form-data"):
        async with request.form(max_files=MAX_FILE, max_fields=20, max_part_size=MAX_CORPO) as modulo:
            dati = {k: v for k, v in modulo.items() if isinstance(v, str)}
            file = [modulo.get("contratto")] + [v for k, v in modulo.multi_items() if k != "contratto"]
            for f in file:
                if f is not None and not isinstance(f, str) and (contenuto := await f.read()).startswith(b"%PDF"):
                    dati["pdf_base64"] = base64.b64encode(contenuto).decode()
                    break
            return dati, True
    try:
        dati = json.loads(await corpo(request))
    except ValueError as errore:
        raise Rifiuto("serve un oggetto JSON") from errore
    if not isinstance(dati, dict):
        raise Rifiuto("serve un oggetto JSON")
    return dati, False


def crea_app(revisore: Revisore, segreto: str, *, host_pubblici: tuple[str, ...] = ()) -> Starlette:
    """`host_pubblici`: i nomi con cui il server si raggiunge da fuori; senza, MCP accetta solo richieste a
    127.0.0.1 e localhost (protezione dal DNS rebinding dell'SDK)."""
    mcp = MCPServer("consiglio", instructions=ISTRUZIONI)

    async def revisiona(
        testo=None, pdf_base64=None, mittente=None, oggetto="", data=None, modalita="telepatia"
    ) -> dict:
        contratto = None
        if pdf_base64:
            contratto = await anyio.to_thread.run_sync(pdf_da_base64, pdf_base64)
        return await anyio.to_thread.run_sync(
            revisore.revisiona_contratto, contratto, testo or None, mittente, oggetto, data, modalita
        )

    async def scegli(id_caso=None, scelte=None, chi=None) -> dict:
        return await anyio.to_thread.run_sync(revisore.registra_scelte, id_caso, scelte, chi)

    @mcp.tool(name="revisiona_contratto", structured_output=True)
    async def revisiona_contratto(
        mittente: str, oggetto: str, data: str, testo: str = "", pdf_base64: str = "", modalita: str = "telepatia"
    ) -> dict[str, Any]:
        """Fa rivedere al Consiglio il contratto allegato a un'email. pdf_base64 è il PDF in base64, oppure testo è il
        testo del contratto (uno solo); mittente, oggetto e data sono quelli dell'email; modalita è telepatia oppure
        testo. Restituisce id_caso, verdetto, raccomandazione, segnalate, dissensi_gravi, sigillo_integro, link alla
        pagina del verdetto e avviso (oggetto e testo dell'email per la persona, da mandare così com'è)."""
        try:
            return await revisiona(testo, pdf_base64, mittente, oggetto, data, modalita)
        except Rifiuto as errore:
            raise ToolError(str(errore)) from errore

    @mcp.tool(name="registra_scelte", structured_output=True)
    async def registra_scelte(id_caso: str, scelte: dict[str, str], chi: str) -> dict[str, Any]:
        """Registra le scelte della persona sui dissensi di un caso: scelte va da categoria a "esperto" oppure
        "verdetto", solo per le categorie in dissenso; chi è la persona."""
        try:
            return await scegli(id_caso, scelte, chi)
        except Rifiuto as errore:
            raise ToolError(str(errore)) from errore

    def http(azione, dall_indirizzo: tuple[str, ...] = (), nel_modulo: dict | None = None):
        previsti = set(inspect.signature(azione).parameters)

        async def rotta(request: Request) -> Response:
            try:
                dati, da_modulo = await campi(request)
                if da_modulo:  # i campi in più di Evolus si ignorano, mai si usano
                    dati = {k: v for k, v in dati.items() if k in previsti}
                elif in_piu := sorted(set(dati) - previsti):
                    raise Rifiuto(f"campi non previsti: {', '.join(in_piu)}")
                dati = {k: v for k, v in request.query_params.items() if k in dall_indirizzo} | dati
                if da_modulo and nel_modulo:
                    dati = {k: v() for k, v in nel_modulo.items()} | {k: v for k, v in dati.items() if v}
                return JSONResponse(await azione(**dati))
            except Rifiuto as errore:
                return JSONResponse({"errore": str(errore)}, status_code=400)
            except Exception:
                log.exception("guasto in %s", request.url.path)
                return JSONResponse({"errore": GUASTO}, status_code=500)

        return rotta

    se_mancano = {
        "mittente": lambda: "(sconosciuto)",
        "oggetto": str,
        "data": lambda: datetime.now(UTC).date().isoformat(),
    }
    mcp.custom_route("/revisiona_contratto", methods=["POST"])(
        http(revisiona, ("mittente", "oggetto", "data", "modalita"), se_mancano)
    )
    mcp.custom_route("/registra_scelte", methods=["POST"])(http(scegli))

    @mcp.custom_route("/casi", methods=["GET"])
    async def casi(request: Request) -> Response:
        return JSONResponse(await anyio.to_thread.run_sync(revisore.elenco))

    @mcp.custom_route("/casi/{id_caso}", methods=["GET"])
    async def caso(request: Request) -> Response:
        try:
            return JSONResponse(revisore.caso(request.path_params["id_caso"]))
        except Rifiuto as errore:
            return JSONResponse({"errore": str(errore)}, status_code=404)

    def della_persona(request: Request) -> str:
        """L'id del caso, se la chiave del link è giusta. Stessa risposta per caso inesistente e chiave sbagliata."""
        id_caso = request.path_params["id_caso"]
        if not revisore.chiave_giusta(id_caso, request.query_params.get("chiave", "")):
            raise Rifiuto("link non valido")
        revisore.cartella_di(id_caso)
        return id_caso

    @mcp.custom_route("/verdetto/{id_caso}", methods=["GET"])
    async def verdetto(request: Request) -> Response:
        try:
            return HTMLResponse(revisore.pagina_di(della_persona(request)))
        except Rifiuto:
            return JSONResponse({"errore": "link non valido"}, status_code=404)

    @mcp.custom_route("/verdetto/{id_caso}/scelte", methods=["POST"])
    async def scelte_della_persona(request: Request) -> Response:
        try:
            id_caso = della_persona(request)
        except Rifiuto:
            return JSONResponse({"errore": "link non valido"}, status_code=404)
        try:
            dati, _ = await campi(request)
            return JSONResponse(await scegli(id_caso, dati.get("scelte"), "persona, dalla pagina del verdetto"))
        except Rifiuto as errore:
            return JSONResponse({"errore": str(errore)}, status_code=400)

    if revisore.catalogo is not None:

        @mcp.custom_route("/prove/contratti", methods=["GET"])
        async def prove_contratti(request: Request) -> Response:
            return JSONResponse(revisore.prove_contratti())

        @mcp.custom_route("/prove/contratto", methods=["POST"])
        async def prova_contratto(request: Request) -> Response:
            try:
                dati, _ = await campi(request)
                if in_piu := sorted(set(dati) - {"contratto", "modalita"}):
                    raise Rifiuto(f"campi non previsti: {', '.join(in_piu)}")
                return JSONResponse(
                    await anyio.to_thread.run_sync(
                        revisore.prova_dal_vivo, dati.get("contratto"), dati.get("modalita", "telepatia")
                    )
                )
            except Occupato as errore:
                return JSONResponse({"errore": str(errore)}, status_code=409)
            except Rifiuto as errore:
                return JSONResponse({"errore": str(errore)}, status_code=400)
            except Exception:
                log.exception("guasto in una prova dal vivo")
                return JSONResponse({"errore": GUASTO}, status_code=500)

    @mcp.custom_route("/salute", methods=["GET"])
    async def salute(request: Request) -> Response:
        return JSONResponse(
            {"pronto": True, "esame_in_corso": revisore.lucchetto.locked(), "prove": revisore.catalogo is not None}
        )

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
