# g1 — il primo cancello: il motore sulla MI300X

Le regole sono pre-registrate in Eval pre-registrato §2; qui ci sono lo script e le istruzioni per il 12/10.
Usa il motore telepatico di `../motore`.

## Cosa decide G1

- **G1 passa se:**
  - il motore (Qwen3-14B su Transformers) e l'agente principale (Qwen3.6-35B-A3B su vLLM) girano **sulla stessa MI300X senza errori di memoria**;
  - in telepatia i **token generati** sono **almeno il 50% in meno** che a testo.
- **Precisione** della telepatia con 10 passi latenti, contro il testo, in tre zone:
  - **entro 3 punti:** *"dimostrato"*;
  - **da 3 a 10 punti sotto:** si va avanti, e decidono G2 e l'eval del Consiglio;
  - **più di 10 punti sotto:** ci si ferma e si passa al pavimento a testo.

## Scelte fissate qui, prima di misurare

non le fissava; valgono da questo commit, e ogni cambiamento dopo la misura è una deviazione da scrivere.

- **Problemi:** i primi 100 del test ufficiale di GSM8K ([openai/grade-school-math](https://github.com/openai/grade-school-math) al commit `3101c7d`, licenza MIT), copiati in `dati/gsm8k-test-100.jsonl`. Lo script controlla l'impronta del file (`1d266ea0…ff90`) a ogni avvio.
- **Agenti:** tre analisti (`pianificatore`, `revisore`, `perfezionatore`) e un `risolutore` che scrive la risposta in `\boxed{}`, come la catena di LatentMAS ma con nomi e prompt nostri. I prompt sono in inglese, come i problemi.
- **Tre giri:** testo, telepatia con 10 passi latenti (il valore degli autori su GSM8K), telepatia senza pensieri (`m=0`). Il terzo è il confronto `m=0` contro `m>0` promesso.
- **Lunghezze:** nel modo a testo ogni analista scrive al massimo **1.024 token**, come lo Sportello; la risposta finale al massimo 1.024 token in tutti i modi. Il rapporto conta i messaggi troncati.
- **Decodifica** deterministica (greedy) e thinking spento, come nel motore; un solo giro.
- **Risposta del modello:** l'ultimo numero dell'ultimo `\boxed{}`; senza riquadro, l'ultimo numero del testo. Si confronta come numero (`18` = `18.0`).
- **Modello:** `Qwen/Qwen3-14B` alla revisione `40c069824f4251a91eefaf281ebe4c544efd3e18`, la stessa del Consiglio; in bf16 sulla MI300X.
- **SDPA:** sulla MI300X solo i kernel flash ed efficient; il ripiego sul backend math è vietato, così un problema dei kernel dà un errore invece di numeri sbagliati.
- **Ordine:** un problema alla volta nei tre modi. Se il tempo finisce, il rapporto confronta i problemi finiti e scrive "parziale".

| File | Cosa fa |
|---|---|
| `g1/esegui.py` | i tre giri: ogni problema finito si scrive subito, e rilanciando si riparte da dove ci si era fermati |
| `g1/agente.py` | controllo dell'endpoint vLLM dell'agente principale: chiamata a `esamina_fattura`, niente pensiero |
| `g1/misure.py` | memoria con i due modelli insieme, impronta, ricalcolo dei pensieri, confronto fp32 contro bf16 |
| `g1/riepilogo.py` | il verdetto e il rapporto da incollare |
| `g1/gsm8k.py` | i 100 problemi e l'estrazione delle risposte |
| `tests/` | i test, con e senza modello |

## Sul Mac

```bash
cd g1
uv venv -p 3.12.venv && uv pip install -p.venv/bin/python -r requirements.txt
.venv/bin/python -m pytest # i test con Qwen3-0.6B girano in circa un minuto
.venv/bin/ruff check. &&.venv/bin/ruff format --check.

# la prova completa, con un modello piccolo e pochi problemi
M="--modello Qwen/Qwen3-0.6B --revisione c1899de289a04d12100db370d81485cdf75e47ca"
.venv/bin/python -m g1.esegui $M --problemi 3 --uscita /tmp/g1
.venv/bin/python -m g1.misure memoria $M --pesi-vllm-gb 71.9 --uscita /tmp/g1/memoria.json
.venv/bin/python -m g1.riepilogo /tmp/g1
```

Prova dell'8/10/2026 su un Mac M4 da 16 GB (MPS, fp32), con Qwen3-0.6B, 3 problemi e i limiti veri (1.024 token):

| Giro | Precisione | Token generati | Secondi per problema |
|---|---|---|---|
| testo | 2 su 3 | 2.572 | 38,4 |
| telepatia (10 passi) | 2 su 3 | 372 | 6,9 |
| senza pensieri | 2 su 3 | 456 | 7,0 |

Misura della memoria con un testo da 1.000 token: messaggio di 0,25 GB, impronta in 0,26 s, ricalcolo dei pensieri identico, picco di 6,6 GB.
Con 4.000 token il Mac va in swap: la staffetta arriva a circa 16.000 posizioni, circa 3,7 GB per copia in fp32, e il motore ne tiene circa tre.
Sulla MI300X, con Qwen3-14B in bf16, un messaggio da 4.000 token pesa circa 0,66 GB.
Il verdetto della prova non conta: serve solo a vedere che tutto gira.

## Il 12/10 sulla MI300X

La scheda per i partecipanti arriva al kickoff (17:00) e **G1 scade alle 22:00**. Non sappiamo ancora in che forma arriva:
- **una macchina con Docker**, come il droplet di AMD Developer Cloud dello spike: si seguono i passi qui sotto;
- **un ambiente tipo notebook** con PyTorch ROCm già installato, come in ACT II: si salta Docker, si crea il venv del passo 3 e si continua uguale. vLLM deve comunque girare sulla stessa scheda per la misura della memoria.

Tempi *(stima)* da correggere qui dopo il giro vero:

| # | Passo | Tempo |
|---|---|---|
| 1 | Controllare la scheda, avviare i download | 5 min, poi i download in background |
| 2 | Copiare `g1/` e `motore/` dal Mac | 2 min |
| 3 | Container e venv del motore | 10 min |
| 4 | Confronto fp32 contro bf16, con vLLM spento | 10-15 min |
| 5 | Avviare vLLM con Qwen3.6 | 5-10 min |
| 6 | Misura della memoria con i due modelli insieme | 5 min |
| 7 | I tre giri sui 100 problemi | da misurare: lo dice il passo 7 dopo 5 problemi |
| 8 | Rapporto | 5 min |

### 1. La scheda e i download

```bash
rocm-smi --showproductname --showmeminfo vram --showdriverversion # 1x MI300X, circa 192 GB
df -h # servono circa 130 GB liberi: 72 GB di Qwen3.6, 30 di Qwen3-14B, 12 di immagine
export HF_HOME=/root/hf # sul disco grande; in ~/.bashrc se servono altre sessioni SSH
command -v hf || pip install -U "huggingface_hub[cli]" # il comando hf sull'host
nohup docker pull vllm/vllm-openai-rocm:v0.30.0 > pull.log 2>&1 &
nohup hf download Qwen/Qwen3-14B --revision 40c069824f4251a91eefaf281ebe4c544efd3e18 > dl-14b.log 2>&1 &
nohup hf download Qwen/Qwen3.6-35B-A3B --revision 995ad96eacd98c81ed38be0c5b274b04031597b0 > dl-36.log 2>&1 &
```

Se la macchina è un droplet di DigitalOcean, **si paga anche da spenta**: alla fine va distrutta.
I modelli vanno sul disco di avvio, non sullo scratch: lo snapshot del passo finale copre solo il disco di avvio.

### 2. Il codice

Nessun token GitHub sulla macchina (come nello spike): il codice si copia dal Mac.

```bash
# sul Mac, dalla radice del repo
rsync -a --exclude.venv --exclude risultati g1 motore root@<IP>:~/hackathon/
```

### 3. Container e venv del motore

Il motore usa il torch ROCm dell'immagine e il suo `transformers` 4.57.6, in un venv separato da quello di vLLM.

```bash
docker run -d --name motore --network=host --ipc=host --shm-size 16G \
  --device=/dev/kfd --device=/dev/dri --group-add video --cap-add=SYS_PTRACE --security-opt seccomp=unconfined \
  -v "$HF_HOME":/root/hf -e HF_HOME=/root/hf -v ~/hackathon:/work -w /work/g1 \
  --entrypoint sleep vllm/vllm-openai-rocm:v0.30.0 infinity
docker exec -it motore bash
# dentro il container
python -m venv --system-site-packages /root/venv &&. /root/venv/bin/activate
pip install -r requirements-rocm.txt
python -c "import torch, transformers; print(torch.__version__, torch.version.hip, torch.cuda.get_device_name(0), transformers.__version__)"
python -m pytest -m "not modello" # i test senza modello
```

Se `torch.cuda.is_available` è falso o il nome della scheda non è MI300X, ci si ferma qui e si scrive l'errore.

### 4. fp32 contro bf16 (vLLM spento)

Da: su ROCm le maschere di SDPA hanno avuto bug, quindi si confronta con un riferimento fp32.

```bash
python -m g1.misure fp32 --problemi 5 --uscita risultati/fp32.json
```

Ci si aspetta che le risposte coincidano; i testi possono divergere di poco. Se le risposte divergono su più di 1 problema su 5, si scrive prima di andare avanti.

### 5. vLLM con Qwen3.6

vLLM si prende di solito il 90% della memoria della scheda: qui è limitato alla metà, così il motore ci sta. Si avvia **prima** del motore.

```bash
docker run -d --name vllm --network=host --ipc=host --shm-size 16G \
  --device=/dev/kfd --device=/dev/dri --group-add video --security-opt seccomp=unconfined \
  -v "$HF_HOME":/root/hf -e HF_HOME=/root/hf --entrypoint vllm vllm/vllm-openai-rocm:v0.30.0 \
  serve Qwen/Qwen3.6-35B-A3B --revision 995ad96eacd98c81ed38be0c5b274b04031597b0 --port 8000 \
  --api-key "$VLLM_API_KEY" --gpu-memory-utilization 0.5 --max-model-len 32768 \
  --enable-auto-tool-choice --tool-call-parser qwen3_coder --reasoning-parser qwen3 \
  --default-chat-template-kwargs '{"enable_thinking": false}' \
  --override-generation-config '{"temperature": 0.7, "top_p": 0.8, "top_k": 20, "min_p": 0.0, "presence_penalty": 1.5, "repetition_penalty": 1.0}'
docker logs -f vllm 2>&1 | grep -m2 -E "Model loading took|startup complete" # annota i GB del primo
python -m g1.agente --url http://127.0.0.1:8000 --chiave "$VLLM_API_KEY" # deve finire con ✓
```

I parametri dell'agente principale sono quelli di Building block Evolus (non `hermes`).
Evolus non passa parametri di richiesta, quindi "pensiero" e campionamento si fissano qui, lato server:

- **Niente pensiero** (`enable_thinking: false`): l'agente sceglie il percorso e scrive un avviso breve, il ragionamento sulla fattura lo fa il motore; così è più veloce e prevedibile, e il timeout di Evolus non lo conosciamo ancora.
- **Campionamento** della scheda di Qwen3.6 per la modalità senza pensiero: temperature 0.7, top_p 0.80, top_k 20, min_p 0, presence_penalty 1.5.
- Se `vllm serve --help` della v0.30.0 non ha uno dei due flag, si cerca il nome nuovo nell'aiuto: il controllo `g1.agente` dice se il pensiero è spento davvero.

`g1.agente` manda la richiesta come la manderebbe Evolus, con lo strumento `esamina_fattura` e senza parametri, e controlla che torni una vera chiamata allo strumento (non XML nel testo, quindi parser giusto), con argomenti JSON e senza pensiero.

### 6. Memoria con i due modelli insieme

```bash
python -m g1.misure memoria --pesi-vllm-gb <GB del log di vLLM> --uscita risultati/memoria.json
```

Misura la staffetta in telepatia su un testo da 4.000 token (al posto della fattura più lunga, se il generatore non c'è ancora): picco del motore, memoria della scheda vista da `rocm-smi` con vLLM acceso, tempo dell'impronta (: se pesa, BLAKE3) e ricalcolo dei pensieri in bf16.

### 7. I tre giri

```bash
nohup python -m g1.esegui --uscita risultati > risultati/esegui.log 2>&1 &
tail -f risultati/esegui.log
```

Dopo 5 problemi `python -m g1.riepilogo risultati` dà i secondi per problema di ogni modo: moltiplicati per 100 dicono se si finisce entro le 22:00.
Se il giro si interrompe, si rilancia lo stesso comando e riparte dal primo problema che manca.

### 8. Il rapporto

```bash
python -m g1.riepilogo risultati > risultati/rapporto.md
```

Si copia `risultati/` sul Mac (`rsync -a root@<IP>:~/hackathon/g1/risultati/ g1/risultati-mi300x/`) e si pubblica il rapporto (`gh issue comment 78 --body-file g1/risultati-mi300x/rapporto.md`), entro le 22:00.

### Dopo G1, se la macchina è un droplet

Con `casa/mi300x/mi300x.sh` della casa per i giudici, che parla con l'API di AMD Developer Cloud (è quella di DigitalOcean):

- **Snapshot** del disco di avvio, con i modelli dentro: `mi300x.sh snapshot`. Ci vogliono circa 1-3 minuti per GB usato, e intanto la macchina si paga: conviene lanciarlo a fine giornata. Prima si preparano i servizi che devono ripartire da soli (`casa/mi300x/README.md`, "La macchina d'oro").
- **Distruggere la macchina:** `mi300x.sh distruggi`, che ricontrolla e dà errore se ne resta una accesa.
- **Il tempo di nascita da snapshot**, la mattina dopo: `mi300x.sh crea aspetta`, che stampa i secondi fino alla macchina attiva e, con `MI300X_SALUTE`, fino al motore pronto. Va scritto.
