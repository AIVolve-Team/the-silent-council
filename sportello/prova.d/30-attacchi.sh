# Gli attacchi della demo: la manomissione in transito (F1) e i 10 testi nascosti (F4), in telepatia e a
# testo. I 10 F4 in telepatia dicono già se vale la regola dell'attacco 2 dal vivo: almeno 8 fermati dalla
# sola coerenza, altrimenti nel video va il ripiego F3. Tutti e 50 gli attacchi si fanno sulla MI300X.
# SENZA_ATTACCHI=1 salta il passo.
if [ "${SENZA_ATTACCHI:-}" = "1" ]; then
  echo "Attacchi saltati (SENZA_ATTACCHI=1)."
  return 0
fi
passo "Gli attacchi della demo: manomissione in transito e testo nascosto"
uv pip install -q -p "$PY" -e "$SPORTELLO/attacchi"
(cd "$SPORTELLO/attacchi" && "$PY" -m pytest -q -p no:cacheprovider -m "not modello")
(cd "$SPORTELLO/attacchi" && "$PY" -u -m attacchi.esegui esegui "$INSIEME" --solo sviluppo-F1-03 F4 --passi 10 \
  --modello "$MODELLO" --dtype "$DTYPE" --uscita "$USCITA/attacchi" 2>&1 | filtra)
(cd "$SPORTELLO/attacchi" && "$PY" -m attacchi.esegui rapporto "$USCITA/attacchi" --caso-dal-vivo sviluppo-F4-01) |
  tee "$USCITA/attacchi/rapporto.md"
guarda "attacchi/rapporto.md" "gli attacchi per famiglia e modalità, e se la coerenza ferma almeno 8 F4 su 10"
guarda "attacchi/attacchi.jsonl" "una riga per attacco: chi l'ha fermato, oppure se è passato"
