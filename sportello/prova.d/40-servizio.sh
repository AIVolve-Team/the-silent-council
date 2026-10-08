# Il motore chiamato come lo chiama l'agente principale in Evolus: il server con i due tool, una fattura
# esaminata con esamina_fattura via MCP e via HTTP, poi registra_decisione. La parte Evolus si prova sulla MI300X.
passo "Il motore come lo chiama l'agente: esamina_fattura e registra_decisione, via MCP e HTTP"
uv pip install -q -p "$PY" -e "$SPORTELLO/pagina" -e "$SPORTELLO/servizio" "mcp==2.3.0" "uvicorn==0.54.0" \
  "python-multipart==0.0.32"
(cd "$SPORTELLO/servizio" && "$PY" -m pytest -q -p no:cacheprovider)
mkdir -p "$USCITA/servizio"
SEGRETO_PROVA="$("$PY" -c 'import secrets; print(secrets.token_hex(32))')"
PORTA_PROVA="${PORTA_PROVA:-8765}"
(cd "$SPORTELLO/servizio" && exec env SPORTELLO_SEGRETO="$SEGRETO_PROVA" "$PY" -m servizio "$INSIEME" \
  --modello "$MODELLO" --dtype "$DTYPE" --casi "$USCITA/servizio/casi" --link "file://$USCITA/servizio/casi/{id}" \
  --porta "$PORTA_PROVA" >"$USCITA/servizio/server.log" 2>&1) &
SERVER=$!
trap 'kill "$SERVER" 2>/dev/null || true' EXIT
echo "Il server carica il modello (con il 14B qualche minuto)."
for _ in $(seq 1 900); do
  curl -sf "http://127.0.0.1:$PORTA_PROVA/salute" >/dev/null && break
  kill -0 "$SERVER" 2>/dev/null || ferma "Il server si è fermato: vedi $USCITA/servizio/server.log"
  sleep 1
done
curl -sf "http://127.0.0.1:$PORTA_PROVA/salute" >/dev/null || ferma "Il server non risponde: vedi $USCITA/servizio/server.log"
# La prima fattura pulita italiana: id, mittente, data e oggetto dell'email, separati da tabulazioni.
IFS=$'\t' read -r FATTURA MITTENTE DATA OGGETTO < <("$PY" -c 'import json, sys
for riga in open(sys.argv[1]):
    c = json.loads(riga)
    if c["anomalia"] is None and c["al_limite"] is None and c["lingua"] == "it":
        print(c["id"], c["email"]["mittente"], c["email"]["data"], c["email"]["oggetto"], sep="\t")
        break' "$INSIEME/verita.jsonl")
(cd "$SPORTELLO/servizio" && SPORTELLO_SEGRETO="$SEGRETO_PROVA" "$PY" -m servizio.chiama "http://127.0.0.1:$PORTA_PROVA" \
  "$INSIEME/fatture/$FATTURA.pdf" --mittente "$MITTENTE" --oggetto "$OGGETTO" --data "$DATA" \
  --uscita "$USCITA/servizio/risposte.json")
kill "$SERVER" 2>/dev/null || true
wait "$SERVER" 2>/dev/null || true
guarda "servizio/risposte.json" "la risposta di esamina_fattura via MCP e via HTTP, e registra_decisione"
guarda "servizio/casi/" "il caso come lo salva il server: registro, PDF, vista, risposta e decisioni"
