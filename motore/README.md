# motore — il motore telepatico

L'interfaccia è quella decisa in "Interfaccia del motore", il sigillo quello.
I termini (messaggio latente, staffetta, sigillo) sono quelli di `CONTEXT.md`.

Agenti Qwen3 che si passano un **messaggio latente per agente** invece del testo: la KV di ciò che l'agente ha letto, la KV dei suoi passi latenti, gli stati nascosti di quei passi e un'etichetta.
La stessa staffetta gira anche **a testo**, come confronto.

| File | Cosa fa |
|---|---|
| `motore/modello.py` | carica Qwen3, riallineamento e passi latenti di LatentMAS, decodifica greedy con vincolo JSON |
| `motore/messaggio.py` | il messaggio latente: etichetta, impronta, copia, salvataggio in safetensors |
| `motore/motore.py` | i comandi `pensa`, `scrivi`, `consegna` e il ricalcolo dei pensieri |
| `motore/staffetta.py` | gli agenti in fila, in telepatia o a testo |
| `motore/controllo.py` | i controlli dentro `consegna`: impronta e catena |
| `motore/sigillo.py` | firma Ed25519 per ruolo e il suo controllo |
| `motore/verifica.py` | verifica dei messaggi salvati, anche senza il motore |
| `tests/` | i test, con e senza modello |

## Uso

```bash
cd motore
uv venv -p 3.12.venv && uv pip install -p.venv -r requirements.txt
.venv/bin/python -m pytest -q # 19 test, circa 30 s su un Mac M4; scarica Qwen3-0.6B la prima volta
.venv/bin/python -m pytest -q -m "not modello" # solo i test veloci, senza modello
.venv/bin/ruff check. &&.venv/bin/ruff format --check.
```

```python
from motore import Agente, Modello, Motore, Staffetta

modello = Modello("Qwen/Qwen3-14B", "<revisione>") # bf16 su GPU (anche ROCm), fp32 su Mac e CPU
motore = Motore(modello, registro=Path("registro"))
legale = Agente("legale", "Sei l'esperto legale....")
#... finanza, rischio, relatore
staffetta = Staffetta(motore, [legale, finanza, rischio], relatore, modalita="telepatia", passi_latenti=10)
esito = staffetta.esegui(
    "contratto-A",
    {"legale": sezione_1, "finanza": sezione_2, "rischio": sezione_3, "relatore": "Scrivi il verdetto."},
    schema=schema_del_verdetto,
)
esito.finale.testo, esito.token_generati, esito.secondi, esito.fermata
```

- **`pensa(agente, testo, ricevuti,...)`** legge il testo sopra i messaggi ricevuti, fa i passi latenti e restituisce il messaggio latente. In modalità testo l'agente scrive invece la sua analisi, al massimo `max_token_testo` token (512 di default).
- **`scrivi(agente, testo, ricevuti, schema=...)`** scrive partendo dai messaggi ricevuti, su una copia della memoria. Con uno schema JSON la decodifica è vincolata. Ogni token ha il suo logprob e le 5 alternative più probabili, per la confidenza.
- **`consegna(messaggio, catena)`** passa sempre dai controlli e dà al destinatario una copia, solo se tutti dicono "passa". Se uno ferma, scrive un registro dell'incidente e salva il messaggio intero come prova.
- **Note per agente**: `scrivi` dello stesso agente con il proprio messaggio fra i ricevuti. La nota non entra nella catena.
- **Impegno**: `con_impegno(messaggio, impegno)` lo mette nell'etichetta e richiude il messaggio, così è sigillato.
- **Prove:** `passi_latenti=0` tiene la KV di ciò che è stato letto; `Staffetta.esegui(pensieri_da={...})` sostituisce i pensieri di un agente con quelli di un altro messaggio e ricalcola la loro KV nella posizione giusta.
- **Attacchi della demo:** `Staffetta.esegui(attacchi={"finanza": funzione})` manomette un messaggio dopo che è nato e prima della consegna.

### Sigillo e verifica

```python
from motore import ControlloSigillo, carica_private, carica_pubbliche, crea_chiavi

crea_chiavi(Path("~/.motore/chiavi-private").expanduser, Path("chiavi-pubbliche"), ["legale", "finanza", "rischio"])
motore = Motore(
    modello, firme=carica_private(...), controlli=[ControlloSigillo(carica_pubbliche(Path("chiavi-pubbliche")))]
)
```

```bash
.venv/bin/python -m motore.verifica <cartella dei messaggi salvati> --pubbliche chiavi-pubbliche
```

Il comando controlla impronta, firma e catena di ogni messaggio salvato, anche dei file senza KV.
Le chiavi private stanno fuori dal repo, con permessi 600; nel repo vanno solo le pubbliche.

## Regole

- **Senza perdite.** Nel passaggio normale la KV viaggia com'è nata, senza ricalcoli né conversioni di dtype. Gli hash dei blocchi e l'impronta si calcolano quando il messaggio nasce e si ricontrollano alla consegna.
- **Chi riceve lavora su una copia.**
- **Un pezzo non si sposta di posizione.** Il controllo della catena verifica che ogni messaggio inizi dove finisce il precedente, che il numero progressivo torni e che l'hash del precedente sia giusto.
- **Ruoli:** i nomi `planner`, `critic`, `refiner` e `judger` sono vietati.
- **Prompt.** Ogni agente è un turno chat di Qwen3 con le sue istruzioni come system. In telepatia il prompt finisce come in LatentMAS (`assistant\n`) e seguono i passi latenti. Per scrivere il modello risponde senza blocco `<think>`.
- **Riallineamento** `W_a` di LatentMAS acceso di default (`Modello(..., riallinea=False)` per spegnerlo). La normalizzazione della norma resta sempre.

## Sulla MI300X (G1)

- Torch nella build ROCm. L'eval pre-registrato gira con `transformers` 4.57.6; con la 5 il motore regge anche Gemma 4 (spike), e il servizio usa la 5. Il modello e la cache nascono in bf16 e restano così.
- Da, per la prova del primo giorno: confrontare con un riferimento fp32 e vietare il ripiego sul backend math di SDPA con `sdpa_kernel`.
- Da misurare: il tempo degli hash su messaggi da qualche GB e se il ricalcolo dei pensieri resta identico in bf16. Sul Mac in fp32 la differenza è 0.

## Cosa manca

- La **coerenza** è un controllo da aggiungere alla lista di `Motore(controlli=...)`, senza cambiare il resto.
- Il **traduttore** legge `messaggio.stati`: gli stati h_0..h_m dei passi latenti.
