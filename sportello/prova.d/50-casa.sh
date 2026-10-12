# La casa per i giudici in locale: la home, i casi di questa prova e le prove dal vivo, con il motore acceso in
# modalità demo. Resta accesa finché non premi Ctrl-C, quindi parte solo se lo chiedi: CASA=1 ./sportello/prova.sh
if [ "${CASA:-}" != "1" ]; then
  echo "La casa per i giudici in locale si accende con: CASA=1 ./sportello/prova.sh (vedi PROVA.md)."
  return 0
fi
passo "La casa per i giudici in locale"
command -v node >/dev/null 2>&1 || ferma "Serve Node.js 20 o più recente (https://nodejs.org) per le funzioni della casa."
uv pip install -q -p "$PY" -e "$SPORTELLO/attacchi" -e "$SPORTELLO/traduttore" -e "$SPORTELLO/pagina" -e "$SPORTELLO/servizio" "mcp==2.3.0" \
  "uvicorn==0.54.0" "python-multipart==0.0.32"
(cd "$RADICE/casa" && npm test --silent)
"$PY" "$RADICE/casa/costruisci.py" --insieme "$INSIEME" --giro "$USCITA/telepatia.jsonl" \
  --registri "$USCITA/registro/telepatia" --registrato "$(date +%d/%m/%Y), prova con $MODELLO" --uscita "$USCITA/casa/public"
SEGRETO_CASA="$("$PY" -c 'import secrets; print(secrets.token_hex(32))')"
PORTA_MOTORE="${PORTA_MOTORE:-8766}"
PORTA_CASA="${PORTA_CASA:-3000}"
(cd "$SPORTELLO/servizio" && exec env SPORTELLO_SEGRETO="$SEGRETO_CASA" "$PY" -m servizio "$INSIEME" --demo \
  --modello "$MODELLO" --dtype "$DTYPE" --casi "$USCITA/casa/casi" --porta "$PORTA_MOTORE" \
  --link "http://localhost:$PORTA_CASA/sportello/dal-vivo.html?id={id}" >"$USCITA/casa/motore.log" 2>&1) &
MOTORE_PID=$!
trap 'kill "$MOTORE_PID" "${CASA_PID:-}" 2>/dev/null || true' EXIT
echo "Il motore carica il modello (con il 14B qualche minuto)."
for _ in $(seq 1 900); do
  curl -sf "http://127.0.0.1:$PORTA_MOTORE/salute" >/dev/null && break
  kill -0 "$MOTORE_PID" 2>/dev/null || ferma "Il motore si è fermato: vedi $USCITA/casa/motore.log"
  sleep 1
done
(cd "$USCITA/casa" && exec env MOTORE_URL="http://127.0.0.1:$PORTA_MOTORE" MOTORE_SEGRETO="$SEGRETO_CASA" \
  PORT="$PORTA_CASA" node "$RADICE/casa/locale.mjs") &
CASA_PID=$!
guarda "casa/public/" "la casa per i giudici costruita da questa prova (con CASA=1)"
printf '\nIntanto, i risultati della prova:\n'
cat "$DOVE"
printf '\nLa casa è accesa: apri http://localhost:%s nel browser. Ctrl-C la spegne.\n' "$PORTA_CASA"
wait "$CASA_PID"
