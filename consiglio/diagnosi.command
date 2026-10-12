#!/bin/bash
# La prova di diagnosi in una finestra del Terminale tutta sua: doppio clic nel Finder, oppure
# `open consiglio/diagnosi.command` (anche da Claude Code). `open` non passa opzioni a prova.command, per questo la
# diagnosi ha un file suo. Guida: consiglio/PROVA.md.
cd "$(dirname "$0")/.." || exit 1
./consiglio/prova.sh --diagnosi
echo
read -r -p "Premi Invio per chiudere questa finestra." _
