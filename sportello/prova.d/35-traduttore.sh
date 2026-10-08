# Il traduttore e G3 (decisione su «Traduttore»): un messaggio per tipo (pulita, anomalia, testo nascosto F4) esaminato con
# la trascrizione della memoria, e la pagina per chi giudica G3. G3 vero, con 30 messaggi e Qwen3-14B, si fa sulla
# MI300X. SENZA_TRADUTTORE=1 salta il passo.
if [ "${SENZA_TRADUTTORE:-}" = "1" ]; then
  echo "Traduttore saltato (SENZA_TRADUTTORE=1)."
  return 0
fi
passo "Il traduttore: la memoria che passa fra gli agenti, ricopiata"
uv pip install -q -p "$PY" -e "$SPORTELLO/attacchi" -e "$SPORTELLO/pagina" -e "$SPORTELLO/traduttore"
(cd "$SPORTELLO/traduttore" && "$PY" -m pytest -q -p no:cacheprovider -m "not modello")
(cd "$SPORTELLO/traduttore" && "$PY" -u -m traduttore.g3 esegui "$INSIEME" --per-tipo 1 --passi 10 --modello "$MODELLO" \
  --dtype "$DTYPE" --uscita "$USCITA/g3" 2>&1 | grep --line-buffered -v -E "Warning|warn\(|Loading checkpoint")
(cd "$SPORTELLO/traduttore" && "$PY" -m traduttore.g3 pagina "$USCITA/g3")
guarda "g3/giudizio.html" "la vista del traduttore su 3 messaggi, come la vedrà chi giudica G3: si apre nel browser"
