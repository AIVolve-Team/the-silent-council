#!/bin/bash
# La prova completa in una finestra del Terminale tutta sua: doppio clic nel Finder, oppure `open consiglio/prova.command`
# (anche da Claude Code). Così gira fuori da VS Code e da Claude Code, e alla fine la finestra resta aperta con il
# riepilogo. Guida: consiglio/PROVA.md.
cd "$(dirname "$0")/.." || exit 1
./consiglio/prova.sh "$@"
echo
read -r -p "Premi Invio per chiudere questa finestra." _
