# La pagina di ogni caso e l'indice con le proposte da approvare, dai risultati in telepatia: quello che
# vedrebbe la persona. Si aprono nel browser, senza server.
passo "Le pagine dei casi"
uv pip install -q -p "$PY" -e "$SPORTELLO/traduttore" -e "$SPORTELLO/pagina"  # la pagina mostra anche la trascrizione
(cd "$SPORTELLO/pagina" && "$PY" -m pytest -q -p no:cacheprovider)
(cd "$SPORTELLO/pagina" && "$PY" -m pagina.pagina "$USCITA/telepatia.jsonl" "$INSIEME" --uscita "$USCITA/pagine" \
  --registrato "$(date +%d/%m/%Y), prova con $MODELLO" --registri "$USCITA/registro/telepatia")
guarda "pagine/index.html" "le proposte da approvare e tutti i casi, con la pagina di ognuno: si apre nel browser"
