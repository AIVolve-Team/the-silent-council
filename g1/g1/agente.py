"""Controllo dell'endpoint vLLM dell'agente principale: una vera chiamata a `esamina_fattura`?

    python -m g1.agente --url http://127.0.0.1:8000 --chiave "$VLLM_API_KEY"

Manda una richiesta come la manderebbe Evolus, senza parametri di campionamento né `chat_template_kwargs` (Evolus non
li passa), con lo strumento `esamina_fattura` del server del motore, e controlla che:
- la risposta sia una chiamata allo strumento letta dal parser `qwen3_coder`, non XML grezzo nel testo;
- gli argomenti siano JSON valido;
- non ci sia ragionamento: il "pensare" è spento lato server (`--default-chat-template-kwargs`).
Esce con 1 se trova un problema. Senza librerie in più: va bene in qualsiasi ambiente con Python.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.request

MODELLO = "Qwen/Qwen3.6-35B-A3B"
# Gli stessi campi del tool MCP del server del motore (sportello/servizio).
STRUMENTO = {
    "type": "function",
    "function": {
        "name": "esamina_fattura",
        "description": "Esamina il PDF originale di una fattura arrivata per email e restituisce l'esito: pagare (una "
        "proposta in attesa di approvazione), persona o bloccare.",
        "parameters": {
            "type": "object",
            "properties": {
                "mittente": {"type": "string", "description": "il mittente dell'email"},
                "oggetto": {"type": "string", "description": "l'oggetto dell'email"},
                "data": {"type": "string", "description": "la data dell'email"},
                "pdf_base64": {"type": "string", "description": "il PDF in base64"},
                "pdf_url": {"type": "string", "description": "un link al PDF, se il file è troppo grande"},
                "modalita": {"type": "string", "enum": ["telepatia", "testo"]},
            },
            "required": ["mittente", "oggetto", "data"],
        },
    },
}
MESSAGGI = [
    {
        "role": "system",
        "content": "Sei l'agente principale dello Sportello: per ogni email con una fattura chiami esamina_fattura, "
        "poi scegli il percorso in base all'esito.",
    },
    {
        "role": "user",
        "content": "È arrivata un'email da fornitore@example.com, oggetto «Fattura 12», data 2026-10-12, con la "
        "fattura allegata: https://example.org/fattura-12.pdf. Esaminala.",
    },
]


def problemi(risposta: dict) -> list[str]:
    """Cosa non va nella risposta di /v1/chat/completions; vuota se l'endpoint è pronto per Evolus."""
    messaggio = risposta["choices"][0]["message"]
    trovati = []
    testo = messaggio.get("content") or ""
    chiamate = messaggio.get("tool_calls") or []
    if "<tool_call>" in testo or "<function=" in testo:
        trovati.append(
            "la chiamata è rimasta nel testo: manca --tool-call-parser qwen3_coder o --enable-auto-tool-choice"
        )
    elif not chiamate:
        trovati.append("nessuna chiamata allo strumento: l'agente ha risposto a parole")
    for c in chiamate:
        nome = c["function"]["name"]
        if nome != "esamina_fattura":
            trovati.append(f"ha chiamato {nome} invece di esamina_fattura")
        try:
            json.loads(c["function"]["arguments"])
        except json.JSONDecodeError:
            trovati.append(f"gli argomenti di {nome} non sono JSON valido")
    if messaggio.get("reasoning_content") or messaggio.get("reasoning"):
        trovati.append(
            "c'è un pensiero prima della risposta: manca --default-chat-template-kwargs '{\"enable_thinking\": false}'"
        )
    return trovati


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--url", default="http://127.0.0.1:8000")
    parser.add_argument("--chiave", required=True, help="la --api-key di vLLM")
    parser.add_argument("--modello", default=MODELLO)
    a = parser.parse_args()
    corpo = {"model": a.modello, "messages": MESSAGGI, "tools": [STRUMENTO], "tool_choice": "auto"}
    richiesta = urllib.request.Request(
        f"{a.url.rstrip('/')}/v1/chat/completions",
        data=json.dumps(corpo).encode(),
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {a.chiave}"},
    )
    inizio = time.perf_counter()
    with urllib.request.urlopen(richiesta, timeout=300) as r:
        risposta = json.load(r)
    secondi = time.perf_counter() - inizio
    trovati = problemi(risposta)
    for c in risposta["choices"][0]["message"].get("tool_calls") or []:
        print(f"chiamata: {c['function']['name']}({c['function']['arguments']})")
    print(f"{secondi:.1f} s, {risposta.get('usage', {}).get('completion_tokens', '?')} token scritti")
    if trovati:
        print("\n".join(f"✗ {p}" for p in trovati))
        sys.exit(1)
    print("✓ endpoint pronto per Evolus: chiamata allo strumento, argomenti JSON, nessun pensiero")


if __name__ == "__main__":
    main()
