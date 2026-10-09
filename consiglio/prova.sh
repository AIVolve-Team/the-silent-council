#!/usr/bin/env bash
# Prova del Consiglio silenzioso con un comando: prepara tutto, fa girare il Consiglio e apre le pagine
# del verdetto. Guida: consiglio/PROVA.md.
#
#   ./consiglio/prova.sh                          giro completo: set dimostrativo (se c'è) e CUAD di sviluppo,
#                                                 in telepatia e a testo
#   ./consiglio/prova.sh --veloce                 solo telepatia, solo il set dimostrativo (o 2 contratti CUAD)
#   ./consiglio/prova.sh --diagnosi               dove si rompe la telepatia: solo telepatia sul set
#                                                 dimostrativo, senza riallineamento, con 0, 10 e 40 passi latenti;
#                                                 i risultati vanno in consiglio/risultati-prova/diagnosi
#   MODELLO=Qwen/Qwen3-8B ./consiglio/prova.sh    sceglie il modello invece di lasciarlo decidere allo script
#
# Funziona su macOS (Apple Silicon) e su Linux con una GPU NVIDIA; su Windows va lanciato dentro WSL2.
# Rilanciarlo è sicuro: quello che è già scaricato non si riscarica.
set -euo pipefail

RADICE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CONSIGLIO="$RADICE/consiglio"
VENV="$CONSIGLIO/.venv"
VELOCE=0
DIAGNOSI=0
for argomento in "$@"; do
  case "$argomento" in
    --veloce) VELOCE=1 ;;
    --diagnosi) DIAGNOSI=1 ;;
    -h | --help) sed -n '2,14p' "$0"; exit 0 ;;
    *) echo "Opzione sconosciuta: $argomento (vedi --help)"; exit 2 ;;
  esac
done
USCITA="$CONSIGLIO/risultati-prova"
[ "$DIAGNOSI" = 1 ] && USCITA="$USCITA/diagnosi"
mkdir -p "$USCITA"
exec > >(tee -a "$USCITA/prova.log") 2>&1

passo() { printf '\n== %s\n' "$*"; }
ferma() { printf '\n!! %s\n' "$*"; exit 1; }

passo "1/8 Il computer"
SISTEMA="$(uname -s)"
GPU_GB=0
if [ "$SISTEMA" = "Darwin" ]; then
  [ "$(uname -m)" = "arm64" ] || ferma "Serve un Mac con chip Apple (M1 o successivi)."
  MEMORIA_GB=$(($(sysctl -n hw.memsize) / 1073741824))
  CHIP="$(sysctl -n machdep.cpu.brand_string)"
  DISPOSITIVO="mps"
  GPU_GB=$MEMORIA_GB  # sul Mac la memoria è condivisa con la GPU
elif [ "$SISTEMA" = "Linux" ]; then
  MEMORIA_GB=$(($(awk '/MemTotal/ {print $2}' /proc/meminfo) / 1048576))
  CHIP="$(uname -m)"
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
echo "Sistema $SISTEMA ($CHIP), memoria $MEMORIA_GB GB, calcolo su $DISPOSITIVO ($GPU_GB GB disponibili per il modello)."
# Il giro dura ore: finché lo script è vivo il Mac non va in stop da solo (lo schermo invece può spegnersi).
if [ "$SISTEMA" = "Darwin" ] && command -v caffeinate >/dev/null 2>&1; then caffeinate -i -w $$ & fi

# Il modello più grande che ci sta: il 14B è quello del Consiglio; gli altri servono solo a provare.
if [ -z "${MODELLO:-}" ]; then
  if [ "$GPU_GB" -ge 48 ]; then MODELLO="Qwen/Qwen3-14B"
  elif [ "$GPU_GB" -ge 28 ]; then MODELLO="Qwen/Qwen3-8B"
  elif [ "$GPU_GB" -ge 14 ]; then MODELLO="Qwen/Qwen3-4B"
  else MODELLO="Qwen/Qwen3-1.7B"; fi
fi
# La staffetta tiene in memoria fino a tre copie della KV del contratto: la catena, la cache di lavoro e la copia
# che si allunga. Con Qwen3-0.6B il contratto CUAD più lungo (22.863 token) arriva a 12 GB; con il 14B si stimano
# circa 46 GB, troppi per un Mac da 64 GB. Sotto gli 80 GB si saltano i contratti oltre 14.000 token.
MAX_TOKEN=""
LIMITE=""
if [ "$GPU_GB" -lt 80 ]; then MAX_TOKEN="--max-token 14000"; LIMITE=", contratti fino a 14.000 token"; fi
echo "Modello: $MODELLO$LIMITE."
if [ "$DIAGNOSI" = 1 ]; then
  case "$MODELLO" in
    *Qwen3-0.6B | *Qwen3-1.7B | *Qwen3-4B)
      echo "Attenzione: con $MODELLO il riallineamento non cambia quasi niente (embedding d'ingresso e d'uscita"
      echo "sono gli stessi): la diagnosi dice qualcosa solo con Qwen3-8B o 14B, qui serve a vedere che tutto va." ;;
  esac
fi
[ "$DISPOSITIVO" = "cpu" ] && echo "Attenzione: senza GPU il giro è molto lento (anche ore per contratto)."

passo "2/8 Python e librerie (la prima volta qualche minuto)"
if ! command -v uv >/dev/null 2>&1; then
  echo "Installo uv, il gestore di Python, nella cartella dell'utente (niente sudo)."
  curl -LsSf https://astral.sh/uv/install.sh | sh
  export PATH="$HOME/.local/bin:$PATH"
fi
[ -x "$VENV/bin/python" ] || uv venv -q -p 3.12 "$VENV"
PY="$VENV/bin/python"
if [ "$DISPOSITIVO" = "rocm" ]; then
  [ -n "${TORCH_INDEX_URL:-}" ] || ferma "Su GPU AMD indica la build ROCm di torch: TORCH_INDEX_URL=https://download.pytorch.org/whl/rocm... ./consiglio/prova.sh"
  uv pip install -q -p "$PY" --index-url "$TORCH_INDEX_URL" "torch==2.14.1"
fi
uv pip install -q -p "$PY" "torch==2.14.1" "transformers==4.57.6" "safetensors==0.8.0" "huggingface-hub==0.36.2" \
  "lm-format-enforcer==0.11.3" "cryptography==50.0.2" "tokenizers==0.22.2" "pytest==9.1.1" -e "$RADICE/motore"
"$PY" -c "import torch, transformers; print('torch', torch.__version__, '| transformers', transformers.__version__, '| GPU:', 'mps' if torch.backends.mps.is_available() else ('cuda' if torch.cuda.is_available() else 'nessuna'))"
# Qwen3 è addestrato in bf16: in float16 i modelli Qwen possono andare in overflow e scrivere token senza senso,
# senza errori. Il float16 resta solo per le GPU che il bf16 non lo fanno, e lo si scopre provandolo.
case "$DISPOSITIVO" in rocm) DISPOSITIVO_TORCH="cuda" ;; *) DISPOSITIVO_TORCH="$DISPOSITIVO" ;; esac
DTYPE="bfloat16"
if ! "$PY" -c "import sys, torch; a = torch.ones(8, 8, dtype=torch.bfloat16, device=sys.argv[1]); (a @ a).sum().item()" \
  "$DISPOSITIVO_TORCH" >/dev/null 2>&1; then
  DTYPE="float16"
fi
echo "Pesi del modello in $DTYPE."

passo "3/8 Test veloci, senza modello"
(cd "$RADICE/motore" && "$PY" -m pytest -q -p no:cacheprovider -m "not modello")
(cd "$CONSIGLIO/dati" && "$PY" -m pytest -q -p no:cacheprovider)
(cd "$CONSIGLIO/revisione" && "$PY" -m pytest -q -p no:cacheprovider -m "not modello")

passo "4/8 Dati dei benchmark (CUAD, ContractNLI, CLAUDETTE), con le impronte controllate"
(cd "$CONSIGLIO/dati" && "$PY" prepara.py)

passo "5/8 Set dimostrativo"
DEMO="$CONSIGLIO/dati/set-dimostrativo"
if ! ls "$DEMO"/*.txt >/dev/null 2>&1; then
  # Il repo privato del team accanto a questo, con lo stesso accesso usato per il clone (HTTPS o SSH): senza
  # chiedere password, se l'accesso non c'è si va avanti con CUAD.
  ORIGINE="$(git -C "$RADICE" remote get-url origin 2>/dev/null || true)"
  REPO_DEMO="${SET_DIMOSTRATIVO_REPO:-${ORIGINE%/*}/consiglio-set-dimostrativo.git}"
  if GIT_TERMINAL_PROMPT=0 GIT_SSH_COMMAND="ssh -o BatchMode=yes" git clone -q "$REPO_DEMO" "$DEMO" 2>/dev/null; then
    echo "Set dimostrativo preso dal repo privato $REPO_DEMO."
  else
    echo "Il repo privato $REPO_DEMO non è raggiungibile."
  fi
fi
CON_DEMO=0
if ls "$DEMO"/*.txt >/dev/null 2>&1; then
  # Il set deve essere quello rivisto in le impronte sono nel repo dal 6/10.
  (cd "$CONSIGLIO/dati" && "$PY" -c '
import hashlib, sys
righe = [r.split() for r in open("set-dimostrativo.sha256") if r.strip()]
diversi = [f for h, f in righe if hashlib.sha256(open(f, "rb").read()).hexdigest() != h]
sys.exit("Il set dimostrativo non coincide con le impronte del repo: " + ", ".join(diversi) if diversi else 0)
') && CON_DEMO=1 && echo "Set dimostrativo trovato e verificato: $(ls "$DEMO"/*.txt | wc -l | tr -d ' ') contratti."
else
  echo "Set dimostrativo non trovato: il giro usa solo CUAD (vedi PROVA.md per averlo)."
fi
if [ "$DIAGNOSI" = 1 ] && [ "$CON_DEMO" = 0 ]; then
  ferma "La diagnosi gira sul set dimostrativo verificato, che qui manca (vedi PROVA.md per averlo)."
fi

passo "6/8 Modello $MODELLO (la prima volta può volerci molto: il 14B pesa circa 30 GB)"
REVISIONE="$(cd "$CONSIGLIO/revisione" && "$PY" -c "from revisione.esegui import MODELLI; print(MODELLI['$MODELLO'])")"
"$PY" -c "import sys; from huggingface_hub import snapshot_download; snapshot_download(sys.argv[1], revision=sys.argv[2])" "$MODELLO" "$REVISIONE"

passo "7/8 Il Consiglio"
giri=()
PASSI=(10)
if [ "$DIAGNOSI" = 1 ]; then
  # Un giro solo, così il modello si carica una volta per i tre valori dei passi. Con 0 passi il relatore riceve solo
  # la memoria di quello che gli esperti hanno letto: se resta rotto, il problema non sono i passi latenti.
  giri+=("--benchmark dimostrativo --modalita telepatia --senza-riallineamento")
  PASSI=(0 10 40)
else
  if [ "$CON_DEMO" = 1 ]; then
    giri+=("--benchmark dimostrativo --modalita telepatia")
    [ "$VELOCE" = 1 ] || giri+=("--benchmark dimostrativo --modalita testo")
  fi
  if [ "$VELOCE" = 1 ]; then
    [ "$CON_DEMO" = 1 ] || giri+=("--benchmark cuad --modalita telepatia --limite 2")
  else
    giri+=("--benchmark cuad --modalita telepatia" "--benchmark cuad --modalita testo")
  fi
fi
for giro in "${giri[@]}"; do
  echo "-- $giro ($(date +%H:%M))"
  # shellcheck disable=SC2086
  (cd "$CONSIGLIO/revisione" && "$PY" -u -m revisione.esegui $giro --passi "${PASSI[@]}" --modello "$MODELLO" \
    --dtype "$DTYPE" $MAX_TOKEN --uscita "$USCITA" 2>&1 | grep --line-buffered -v -E "Warning|warn\(|Loading checkpoint") ||
    echo "!! Il giro '$giro' si è fermato: il resto continua (dettagli in $USCITA/prova.log)."
done

passo "8/8 Pagine del verdetto"
if [ "$DIAGNOSI" = 1 ]; then
  echo "Nella diagnosi le pagine non servono: contano i numeri del riepilogo."
elif [ ! -f "$CONSIGLIO/revisione/revisione/vista.py" ]; then
  echo "La pagina del verdetto arriva con «Pagina del verdetto e flusso Evolus» (ramo feat/63-pagina-verdetto): per ora ci sono solo i .jsonl."
else
(cd "$CONSIGLIO/revisione" && "$PY" - "$USCITA" "$DEMO" <<'PAGINE'
import json, sys
from pathlib import Path
from revisione import BENCHMARK
from revisione.vista import pagina, vista

uscita, demo = Path(sys.argv[1]), Path(sys.argv[2])
cartella = uscita / "pagine"
cartella.mkdir(exist_ok=True)
for giro in sorted(uscita.glob("*.jsonl")):
    for riga in giro.open():
        r = json.loads(riga)
        contratto = demo / f"{r['contratto']}.txt"
        titolo = r["contratto"]
        if r["benchmark"] == "dimostrativo" and contratto.exists():
            righe = [x.strip() for x in contratto.read_text().splitlines() if x.strip()]
            oggetto = next((x.split(":", 1)[1].strip() for x in righe if x.lower().startswith("oggetto:")), None)
            titolo = oggetto or righe[0]
            titolo = titolo[0].upper() + titolo[1:].lower()
        breve = r["contratto"][:50].rstrip("-_. ")
        nome = f"{r['benchmark']}-{breve}-{r['modalita']}".replace("/", "_").replace(" ", "_")
        (cartella / f"{nome}.html").write_text(pagina(vista(r, BENCHMARK[r["benchmark"]], titolo)))
print(f"Pagine in {cartella}")
PAGINE
)
# Si apre per prima la pagina di un contratto italiano del set dimostrativo, se c'è.
PRIMA=""
for candidata in "$USCITA"/pagine/dimostrativo-*telepatia.html "$USCITA"/pagine/*telepatia.html; do
  if [ -f "$candidata" ]; then PRIMA="$candidata"; break; fi
done
if [ -n "$PRIMA" ]; then
  if command -v open >/dev/null 2>&1; then open "$PRIMA"; elif command -v xdg-open >/dev/null 2>&1; then xdg-open "$PRIMA"; fi
fi
fi

passo "Riepilogo"
grep -h " contratti | " "$USCITA/prova.log" | tail -n $((${#giri[@]} * ${#PASSI[@]})) || true
if [ "$DIAGNOSI" = 1 ]; then
  MANDA="Comprimi la cartella $USCITA e manda lo zip."
  if command -v zip >/dev/null 2>&1; then
    rm -f "$USCITA.zip"
    # Senza le copie intere dei messaggi che il motore salva solo se il sigillo si rompe: pesano GB.
    (cd "$(dirname "$USCITA")" && zip -qr diagnosi.zip diagnosi -x "diagnosi/registro/*.safetensors") &&
      MANDA="Lo zip da mandare è $USCITA.zip."
  fi
  cat <<FINE

Fatto. Risultati della diagnosi in $USCITA:
- *.jsonl          le revisioni complete, un file per numero di passi latenti (0, 10, 40)
- prova.log        tutto quello che è successo
$MANDA
Mandalo solo in privato a chi te l'ha chiesto, non su GitHub: contiene frasi del set dimostrativo.
FINE
  exit 0
fi
cat <<FINE

Fatto. Risultati in $USCITA:
- pagine/          le pagine del verdetto, una per contratto e modalità (la prima si è aperta da sola)
- *.jsonl          le revisioni complete: note, verdetto, confidenze, dissensi, token e tempi
- prova.log        tutto quello che è successo
Per condividerli col team basta mandare la cartella risultati-prova (il set dimostrativo resta fuori: è nei .jsonl
solo come citazioni, quindi va condivisa solo dentro il team).
FINE
