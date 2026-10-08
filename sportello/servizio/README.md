# sportello/servizio — il server del motore: i due tool via MCP e HTTP

L'agente principale in Evolus chiama il motore con due tool, esposti via MCP e, come ripiego, via HTTP semplice, con lo stesso gestore.
Il server sta sulla MI300X accanto al modello; le prove dal vivo della casa per i giudici passano dalla stessa porta.

| File | Cosa fa |
|---|---|
| `servizio/gestore.py` | i due tool, con le loro regole, uguali per MCP e HTTP |
| `servizio/server.py` | l'app: MCP su `/mcp`, le stesse rotte in HTTP, il segreto |
| `servizio/__main__.py` | carica Qwen3 una volta e avvia il server |
| `tests/` | i test, con una staffetta finta al posto del modello |

## I due tool

- **`esamina_fattura`**: `pdf_base64` (oppure `pdf_url`), `mittente`, `oggetto`, `data`, `modalita` (`telepatia` o `testo`).
  Restituisce `id_caso`, `esito`, `motivo` e `motivi` con il livello, `proposta` (solo se l'esito è pagare: importo, scadenza, IBAN in anagrafica, "in attesa di approvazione"), `discordanze`, `sigillo`, `contatti_anagrafica`, `frode_sospetta`, `non_rispondere_al_mittente` e il `link` alla pagina del caso.
- **`registra_decisione`**: `id_caso`, `decisione` (`approvato`, `rifiutato`, `segnalato`, come sulla pagina del caso), `chi`, `nota`.
  Lo chiama il secondo workflow, che la casa per i giudici avvia quando la persona decide.

Regole che valgono per tutti e due i trasporti:

- **L'IBAN esce sempre abbreviato** (prime e ultime quattro cifre), anche dentro i motivi e la nota: intero c'è solo nel PDF del registro.
- **L'interruttore del livello 2 non è un parametro**.
- **Un esame alla volta**: la GPU è una. Le decisioni non aspettano un esame in corso.
- **La stessa email due volte è lo stesso caso**: il nuovo tentativo di Evolus non rifà l'esame, riceve la risposta già scritta.
- **Un caso bloccato si approva solo con la nota** della verifica fatta con i contatti in anagrafica; per rifiutare serve il motivo.
- **"Pagare" è una proposta**, mai un pagamento: nella demo "approvato" resta scritto nel caso.
- **Una richiesta sbagliata** (non un PDF, oltre 10 MB, modalità sconosciuta, id di un caso che non esiste) si rifiuta prima di toccare il modello: 400 in HTTP, errore del tool in MCP.
- **Un guasto del motore** non mostra dettagli: 500 in HTTP con *"riprova una volta, poi passa il caso a una persona"*, la traccia solo nel log.

## Rotte

| Rotta | Cosa fa |
|---|---|
| `POST /mcp` | MCP Streamable HTTP, senza stato, risposte JSON |
| `POST /esamina_fattura` | lo stesso tool in HTTP: JSON con `pdf_base64`, oppure modulo con il file nel campo `pdf` |
| `POST /registra_decisione` | lo stesso tool in HTTP, JSON |
| `GET /casi` | i casi con esito e ultima decisione, per l'indice della casa dei giudici |
| `GET /casi/{id}`, `GET /casi/{id}/fattura.pdf` | la vista della pagina del caso con le decisioni, e il PDF |
| `GET /salute` | l'unica aperta: `{"pronto": true, "esame_in_corso": false}` |

Tutte le altre chiedono il segreto, in `Authorization: Bearer <segreto>` oppure in `X-Api-Key: <segreto>`.
`pdf_url` funziona solo da https e dagli host passati con `--host-pdf`, senza redirect, fino a 10 MB: serve se il connettore di Evolus ha un limite di dimensione troppo basso.

## Avvio

```bash
cd sportello/servizio
uv venv --python 3.12 && uv pip install -r requirements.txt
export SPORTELLO_SEGRETO=$(openssl rand -hex 32) # lo stesso va nel connettore di Evolus e nella funzione Vercel
.venv/bin/python -m servizio../dati/insiemi/sviluppo --modello Qwen/Qwen3-14B --passi 20 \
    --link "https://<casa dei giudici>/caso.html?id={id}" --host-pubblico motore.example.org
```

- **TLS:** Caddy davanti (`caddy reverse-proxy --from motore.example.org --to 127.0.0.1:8000`), oppure uvicorn con `--ssl-certfile`, `--ssl-keyfile` e `--host 0.0.0.0`.
- **`--host-pubblico`:** il nome con cui il server si raggiunge da fuori. Senza, l'SDK MCP accetta solo richieste a 127.0.0.1 e localhost (protezione dal DNS rebinding).
- **`--passi`:** i passi latenti scelti da G2.
- **Ogni caso** si salva in `--casi/<id>/` (predefinito `~/.sportello/casi`): registro firmato della pipeline, `fattura.pdf`, `vista.json`, `risposta.json`, `decisioni.jsonl`. `python -m motore.verifica <casi>/<id> --pubbliche <casi>/<id>/chiavi-pubbliche` lo controlla da solo.
- **Le chiavi private** restano in `--chiavi` (predefinito `~/.sportello/chiavi-prova`), fuori dal repo e dai casi.

## Test

```bash
.venv/bin/python -m pytest -q # 18 test, senza modello
```

Due punti di test: il **gestore** (le regole dei due tool, con una staffetta finta) e l'**app** (segreto, stesso caso via MCP con il client dell'SDK e via HTTP, errori in HTTP).

## Cosa manca

- **Il lato Evolus** (workflow dall'email, blocco *choice*, avviso per email, secondo workflow, agente principale su vLLM): dipende da cosa c'è nella workspace dell'evento, che si sa al kickoff del 12/10.
- **Le prove dal vivo** della casa per i giudici (scegliere una nostra fattura, i due attacchi, "prova tu a ingannarlo") e l'interruttore del livello 2 della modalità demo:.
