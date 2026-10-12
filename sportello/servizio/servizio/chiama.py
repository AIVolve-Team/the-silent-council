"""Chiama il motore come lo chiama l'agente principale in Evolus: un controllo da capo a fondo del server.

    SPORTELLO_SEGRETO=… python -m servizio.chiama https://motore.example.org fattura.pdf \\
        --mittente fornitore@example.com --oggetto "Fattura 12" --data 2026-10-12

1. `esamina_fattura` via MCP, con il client dell'SDK;
2. la stessa email via HTTP: deve tornare lo stesso caso, senza un secondo esame;
3. `registra_decisione` via MCP ("segnalato", che non chiede la nota).

Lo usano la prova per i colleghi (`sportello/prova.d/40-servizio.sh`) e il controllo del server sulla MI300X.
"""

from __future__ import annotations

import argparse
import asyncio
import base64
import json
import os
import sys
from pathlib import Path

import httpx2
from mcp import Client
from mcp.client.streamable_http import streamable_http_client


async def prova_completa(
    url: str, pdf: bytes, email: dict, segreto: str, *, http: httpx2.AsyncClient | None = None
) -> dict:
    """I due tool via MCP e via HTTP sulla stessa fattura. `http` serve ai test, per parlare con l'app in memoria."""
    argomenti = {
        "pdf_base64": base64.b64encode(pdf).decode(),
        "mittente": email["mittente"],
        "oggetto": email.get("oggetto", ""),
        "data": email["data"],
    }
    proprio = http is None
    http = http or httpx2.AsyncClient(timeout=600)
    http.headers["Authorization"] = f"Bearer {segreto}"
    try:
        async with Client(streamable_http_client(f"{url.rstrip('/')}/mcp", http_client=http)) as mcp:
            r = await mcp.call_tool("esamina_fattura", argomenti)
            if r.is_error:
                raise RuntimeError(f"esamina_fattura via MCP: {r.content[0].text}")
            via_mcp = r.structured_content
            via_http = (await http.post(f"{url.rstrip('/')}/esamina_fattura", json=argomenti)).raise_for_status().json()
            decisione = {"id_caso": via_mcp["id_caso"], "decisione": "segnalato", "chi": "prova per i colleghi"}
            r = await mcp.call_tool("registra_decisione", decisione)
            if r.is_error:
                raise RuntimeError(f"registra_decisione via MCP: {r.content[0].text}")
            return {"mcp": via_mcp, "http": via_http, "uguali": via_mcp == via_http, "decisione": r.structured_content}
    finally:
        if proprio:
            await http.aclose()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("url", help="l'indirizzo del server del motore, per esempio http://127.0.0.1:8000")
    parser.add_argument("pdf", type=Path)
    parser.add_argument("--mittente", required=True)
    parser.add_argument("--oggetto", default="")
    parser.add_argument("--data", required=True)
    parser.add_argument("--uscita", type=Path, default=None, help="dove scrivere le risposte in JSON")
    a = parser.parse_args()
    segreto = os.environ.get("SPORTELLO_SEGRETO") or sys.exit("Serve SPORTELLO_SEGRETO, lo stesso del server.")
    email = {"mittente": a.mittente, "oggetto": a.oggetto, "data": a.data}
    esito = asyncio.run(prova_completa(a.url, a.pdf.read_bytes(), email, segreto))
    if a.uscita:
        a.uscita.write_text(json.dumps(esito, ensure_ascii=False, indent=1))
    r = esito["mcp"]
    print(f"esamina_fattura: {r['id_caso']} → {r['esito']} ({r['motivo']['it']}), {r['secondi']} s")
    print(f"stesso caso via HTTP: {'sì' if esito['uguali'] else 'NO'}")
    print(f"registra_decisione: {esito['decisione']['decisione']}, registrata {esito['decisione']['registrata']}")
    if not esito["uguali"]:
        sys.exit(1)


if __name__ == "__main__":
    main()
