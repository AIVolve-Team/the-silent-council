#!/usr/bin/env bash
# Prova dello Sportello telepatico con un comando: prepara tutto, genera le fatture di sviluppo, fa girare la
# pipeline in telepatia e a testo e stampa il riepilogo. Guida: sportello/PROVA.md.
#
#   ./sportello/prova.sh                          10 fatture di sviluppo, in telepatia e a testo
#   ./sportello/prova.sh --tutte                  tutte le 100 fatture di sviluppo
#   MODELLO=Qwen/Qwen3-8B ./sportello/prova.sh    sceglie il modello invece di lasciarlo decidere allo script
#   FATTURE=3 ./sportello/prova.sh                solo le prime 3 fatture
#
# Funziona su macOS (Apple Silicon) e su Linux con una GPU; su Windows va lanciato dentro WSL2.
# Rilanciarlo è sicuro: le fatture già esaminate non si rifanno.
set -euo pipefail

RADICE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SPORTELLO="$RADICE/sportello"
USCITA="$SPORTELLO/risultati-prova"
VENV="$SPORTELLO/.venv"
INSIEME="$SPORTELLO/dati/insiemi/sviluppo"
IMPRONTA_SVILUPPO="160d6c45285a88075e9cfe0c27377b04dd3b434cbcac3a25da0cc9e18340cc4e"
FATTURE="${FATTURE:-10}"
for argomento in "$@"; do
  case "$argomento" in
    --tutte) FATTURE=100 ;;
    -h | --help) sed -n '2,11p' "$0"; exit 0 ;;
    *) echo "Opzione sconosciuta: $argomento (vedi --help)"; exit 2 ;;
  esac
done
mkdir -p "$USCITA"
exec > >(tee -a "$USCITA/prova.log") 2>&1

passo() { printf '\n== %s\n' "$*"; }
ferma() { printf '\n!! %s\n' "$*"; exit 1; }

[ -d "$RADICE/motore" ] || ferma "Manca la cartella motore/: serve un ramo che contenga il motore telepatico."

passo "1/6 Il computer"
SISTEMA="$(uname -s)"
if [ "$SISTEMA" = "Darwin" ]; then
  [ "$(uname -m)" = "arm64" ] || ferma "Serve un Mac con chip Apple (M1 o successivi)."
  MEMORIA_GB=$(($(sysctl -n hw.memsize) / 1073741824))
  DISPOSITIVO="mps"
  GPU_GB=$MEMORIA_GB  # sul Mac la memoria è condivisa con la GPU
elif [ "$SISTEMA" = "Linux" ]; then
  MEMORIA_GB=$(($(awk '/MemTotal/ {print $2}' /proc/meminfo) / 1048576))
  if command -v nvidia-smi >/dev/null 2>&1; then
    DISPOSITIVO="cuda"
    GPU_GB=$(($(nvidia-smi --query-gpu=memory.total --format=csv,noheader,nounits | head -1) / 1024))
  elif command -v rocm-smi >/dev/null 2>&1 || [ -e /dev/kfd ]; then
    DISPOSITIVO="rocm"
    GPU_GB=192
  else
    DISPOSITIVO="cpu"
    GPU_GB=$MEMORIA_GB
  fi
else
  ferma "Sistema non supportato: $SISTEMA. Su Windows lancia lo script dentro WSL2 (Ubuntu)."
fi
echo "Sistema $SISTEMA, memoria $MEMORIA_GB GB, calcolo su $DISPOSITIVO ($GPU_GB GB disponibili per il modello)."
if [ "$SISTEMA" = "Darwin" ] && command -v caffeinate >/dev/null 2>&1; then caffeinate -i -w $$ & fi

# Il più grande che ci sta: il 14B è il modello dello Sportello; gli altri servono solo a vedere che tutto gira.
# Le fatture sono corte (al più qualche migliaio di token), quindi la memoria serve soprattutto ai pesi.
if [ -z "${MODELLO:-}" ]; then
  if [ "$GPU_GB" -ge 48 ]; then MODELLO="Qwen/Qwen3-14B"
  elif [ "$GPU_GB" -ge 28 ]; then MODELLO="Qwen/Qwen3-8B"
  elif [ "$GPU_GB" -ge 20 ]; then MODELLO="Qwen/Qwen3-4B"
  else MODELLO="Qwen/Qwen3-1.7B"; fi
fi
echo "Modello: $MODELLO, $FATTURE fatture di sviluppo."
[ "$DISPOSITIVO" = "cpu" ] && echo "Attenzione: senza GPU il giro è molto lento."

passo "2/6 Python e librerie (la prima volta qualche minuto)"
if ! command -v uv >/dev/null 2>&1; then
  echo "Installo uv, il gestore di Python, nella cartella dell'utente (niente sudo)."
  curl -LsSf https://astral.sh/uv/install.sh | sh
  export PATH="$HOME/.local/bin:$PATH"
fi
[ -x "$VENV/bin/python" ] || uv venv -q -p 3.12 "$VENV"
PY="$VENV/bin/python"
if [ "$DISPOSITIVO" = "rocm" ]; then
  [ -n "${TORCH_INDEX_URL:-}" ] || ferma "Su GPU AMD indica la build ROCm di torch: TORCH_INDEX_URL=https://download.pytorch.org/whl/rocm... ./sportello/prova.sh"
  uv pip install -q -p "$PY" --index-url "$TORCH_INDEX_URL" "torch==2.14.1"
fi
uv pip install -q -p "$PY" "torch==2.14.1" "transformers==4.57.6" "safetensors==0.8.0" "huggingface-hub==0.36.2" \
  "lm-format-enforcer==0.11.3" "cryptography==50.0.2" "tokenizers==0.22.2" "faker==40.41.0" "reportlab==5.0.1" \
  "pypdf==6.19.0" "jsonschema==4.26.0" "pytest==9.1.1" \
  -e "$RADICE/motore" -e "$SPORTELLO/dati" -e "$SPORTELLO/controllore" -e "$SPORTELLO/pipeline"
case "$DISPOSITIVO" in rocm) DISPOSITIVO_TORCH="cuda" ;; *) DISPOSITIVO_TORCH="$DISPOSITIVO" ;; esac
# Qwen3 è addestrato in bf16: in float16 può andare in overflow senza dare errori. Il float16 resta solo per le GPU
# che il bf16 non lo fanno; in fp32 servirebbe il doppio della memoria.
DTYPE="bfloat16"
if ! "$PY" -c "import sys, torch; a = torch.ones(8, 8, dtype=torch.bfloat16, device=sys.argv[1]); (a @ a).sum().item()" \
  "$DISPOSITIVO_TORCH" >/dev/null 2>&1; then
  DTYPE="float16"
fi
echo "Pesi del modello in $DTYPE."

passo "3/6 Test veloci, senza modello"
(cd "$RADICE/motore" && "$PY" -m pytest -q -p no:cacheprovider -m "not modello")
for cartella in dati controllore pipeline; do
  (cd "$SPORTELLO/$cartella" && "$PY" -m pytest -q -p no:cacheprovider -m "not modello")
done

passo "4/6 Fatture di sviluppo (seme 101), con l'impronta controllata"
if [ ! -f "$INSIEME/impronta.txt" ]; then
  (cd "$SPORTELLO/dati" && "$PY" -c 'from pathlib import Path; from fatture.genera import genera_insieme; from fatture.insiemi import salva_insieme
print(salva_insieme(genera_insieme("sviluppo"), Path("insiemi/sviluppo")))')
fi
if [ "$(tr -d '[:space:]' < "$INSIEME/impronta.txt")" = "$IMPRONTA_SVILUPPO" ]; then
  echo "Fatture di sviluppo pronte: impronta uguale a quella scritta su “Pre-registered eval G1-G4”."
else
  echo "Attenzione: l'impronta delle fatture di sviluppo è diversa da quella su «Eval pre-registrato G1-G4» (generatore cambiato?)."
fi

passo "5/6 Modello $MODELLO (la prima volta può volerci molto: il 14B pesa circa 30 GB)"
# Dalla cartella della pipeline: dalla radice del repo Python prenderebbe la cartella motore/ al posto del pacchetto.
REVISIONE="$(cd "$SPORTELLO/pipeline" && "$PY" -c "from pipeline.giro import MODELLI; print(MODELLI['$MODELLO'])")"
"$PY" -c "import sys; from huggingface_hub import snapshot_download; snapshot_download(sys.argv[1], revision=sys.argv[2])" "$MODELLO" "$REVISIONE"

passo "6/6 Lo Sportello, in telepatia e a testo"
for modalita in telepatia testo; do
  echo "-- $modalita ($(date +%H:%M))"
  (cd "$SPORTELLO/pipeline" && "$PY" -u -m pipeline.giro "$INSIEME" --modalita "$modalita" --passi 10 \
    --limite "$FATTURE" --modello "$MODELLO" --dtype "$DTYPE" --uscita "$USCITA" 2>&1 |
    grep --line-buffered -v -E "Warning|warn\(|Loading checkpoint") ||
    echo "!! Il giro '$modalita' si è fermato: il resto continua (dettagli in $USCITA/prova.log)."
done

passo "Riepilogo"
(cd "$SPORTELLO/pipeline" && "$PY" -m pipeline.riepilogo "$USCITA" "$INSIEME")
cat <<FINE

Fatto. Risultati in $USCITA:
- telepatia.jsonl, testo.jsonl   una riga per fattura: esito, motivi, impegno, lettura, proposta, token e tempi
- registro/                      il registro di ogni caso: messaggi firmati e chiavi pubbliche, verificabile con
                                 python -m motore.verifica registro/<modalità>/<caso> --pubbliche registro/<modalità>/<caso>/chiavi-pubbliche
- prova.log                      tutto quello che è successo
Le fatture sono inventate dal generatore: i risultati si possono condividere liberamente.
FINE
