# I passi in più della prova per i colleghi

`sportello/prova.sh` li esegue dopo la pipeline, in ordine di nome, dentro una subshell: uno che si ferma non ferma gli altri.
Ogni ticket di build che fa girare un modello aggiunge qui il suo file `NN-nome.sh`, e una riga nella tabella "I passi in più" di `sportello/PROVA.md`.

Un passo può usare le variabili e le funzioni di `prova.sh`: `$PY`, `$RADICE`, `$SPORTELLO`, `$USCITA`, `$INSIEME`, `$MODELLO`, `$DTYPE`, `$FATTURE`, `passo`, `ferma`, `filtra` (toglie gli avvisi delle librerie da un comando con `| filtra`) e `guarda "<file>" "<cosa c'è>"`, che aggiunge una riga all'elenco finale di dove guardare.
Le sue librerie le installa lui, con `uv pip install -q -p "$PY" …`.
