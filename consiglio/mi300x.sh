#!/usr/bin/env bash
# Il giro del Consiglio sulla MI300X, nel container del motore di G1, dopo i suoi passi 3 e 4 (container e
# fp32 contro bf16, g1/README.md): la guida è consiglio/MI300X.md. La prima volta va lanciato
# TORCH_DI_SISTEMA=1 SENZA_RIALLINEAMENTO=1 ./consiglio/prova.sh --veloce, che prepara Python, dati e modello e prova
# che tutto gira sulla GPU.
#
#   ./consiglio/mi300x.sh taratura     telepatia con 0, 10, 20 e 40 passi e testo, su CUAD e dimostrativo di
#                                      sviluppo; scrive le tabelle per scegliere passi e soglie
#   ./consiglio/mi300x.sh sviluppo     l'eval di sviluppo su tutti i benchmark, con PASSI=<passi scelti>
#   ./consiglio/mi300x.sh test         il giro di test, una volta sola, con la pre-registrazione congelata
#
# Variabili: PASSI (sviluppo e test); il riallineamento W_a è spento, come deciso con la diagnosi del 12/10
# (SENZA_RIALLINEAMENTO=0 lo riaccende, solo per un confronto: non è la configurazione pre-registrata).
# Per provare lo script senza GPU: MODELLO=Qwen/Qwen3-0.6B LIMITE=1 ./consiglio/mi300x.sh taratura (LIMITE=2 per
# sviluppo, perché gli scambi servono almeno 2 contratti).
set -euo pipefail

RADICE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CONSIGLIO="$RADICE/consiglio"
PY="${PY:-$CONSIGLIO/.venv/bin/python}"
FASE="${1:-}"
MODELLO="${MODELLO:-Qwen/Qwen3-14B}"
case "$FASE" in
  taratura | sviluppo | test) ;;
  *) sed -n '2,15p' "$0"; exit 2 ;;
esac
[ -x "$PY" ] || { echo "Manca $PY: lancia prima ./consiglio/prova.sh --veloce"; exit 1; }
USCITA="$CONSIGLIO/risultati-mi300x/$FASE"
mkdir -p "$USCITA"
exec > >(tee -a "$USCITA/giro.log") 2>&1
echo "== $FASE con $MODELLO ($(date '+%d/%m %H:%M'))"

opzioni=(--modello "$MODELLO" --dtype bfloat16)
[ "${SENZA_RIALLINEAMENTO:-1}" = 1 ] && opzioni+=(--senza-riallineamento)
prove=()
[ -n "${LIMITE:-}" ] && prove+=(--limite "$LIMITE")
filtra() { grep --line-buffered -v -E "Warning|warn\(|Loading checkpoint"; }
cd "$CONSIGLIO/revisione"

case "$FASE" in
  taratura)
    for benchmark in cuad dimostrativo; do
      echo "-- $benchmark: telepatia con 0, 10, 20, 40 passi ($(date +%H:%M))"
      "$PY" -u -m revisione.esegui --benchmark "$benchmark" --modalita telepatia --passi 0 10 20 40 "${opzioni[@]}" \
        ${prove[@]+"${prove[@]}"} --uscita "$USCITA" 2>&1 | filtra
      echo "-- $benchmark: testo ($(date +%H:%M))"
      "$PY" -u -m revisione.esegui --benchmark "$benchmark" --modalita testo --passi 10 "${opzioni[@]}" ${prove[@]+"${prove[@]}"} \
        --uscita "$USCITA" 2>&1 | filtra
    done
    for benchmark in cuad dimostrativo; do "$PY" -m revisione.taratura "$USCITA" --benchmark "$benchmark"; done \
      > "$USCITA/taratura.md"
    echo "Fatto. Tabelle per la taratura in $USCITA/taratura.md: si scelgono passi e soglie e si scrivono nella pre-registrazione."
    ;;
  sviluppo | test)
    [ -n "${PASSI:-}" ] || { echo "Serve PASSI, i passi latenti scelti in PASSI=10 $0 $FASE"; exit 2; }
    insieme=sviluppo
    if [ "$FASE" = test ]; then
      insieme=test
      [ -z "${LIMITE:-}" ] || { echo "Sul test girano tutti i contratti: niente LIMITE."; exit 2; }
    fi
    for benchmark in cuad contractnli claudette; do
      echo "-- $benchmark, $insieme ($(date +%H:%M))"
      "$PY" -u -m revisione.esame esegui --benchmark "$benchmark" --insieme "$insieme" --passi "$PASSI" "${opzioni[@]}" \
        ${prove[@]+"${prove[@]}"} --uscita "$USCITA" 2>&1 | filtra
    done
    # Il set dimostrativo non ha un test: è quello del controllo a mano alla cieca.
    echo "-- dimostrativo ($(date +%H:%M))"
    "$PY" -u -m revisione.esame esegui --benchmark dimostrativo --passi "$PASSI" "${opzioni[@]}" ${prove[@]+"${prove[@]}"} \
      --uscita "$USCITA" 2>&1 | filtra
    "$PY" -m revisione.esame rapporto "$USCITA" > /dev/null
    "$PY" -m revisione.cieca prepara "$USCITA" --uscita "$USCITA/cieca"
    echo "Fatto. Rapporto in $USCITA/rapporto.md (solo numeri aggregati, da pubblicare)."
    echo "Per il controllo alla cieca: $USCITA/cieca/per-chi-controlla, con i contratti; la chiave resta a chi organizza."
    ;;
esac
