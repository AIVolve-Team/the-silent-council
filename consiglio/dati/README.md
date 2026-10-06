# consiglio/dati — set di misura e set dimostrativo del Consiglio

Le regole vengono da "Benchmark e contratti di prova" e da "Impostazione del Consiglio".
I termini (set di misura, set dimostrativo, clausola da segnalare, risposta giusta) sono quelli di `CONTEXT.md`.

`prepara.py` scarica CUAD, ContractNLI e i ToS italiani di CLAUDETTE dalle fonti ufficiali, a versioni fissate e con l'hash controllato.
Poi conta i token Qwen3 di ogni contratto, estrae il campione con seme fisso tra i contratti sotto il tetto e scrive la risposta giusta di ogni coppia (contratto, categoria).

| File | Cosa contiene |
|---|---|
| `prepara.py` | download, conteggio dei token, campione e risposte giuste |
| `categorie.py` | le categorie di ogni benchmark e il ruolo che le guarda |
| `test_prepara.py` | test delle regole sì/no e della lettura dei tag di CLAUDETTE |
| `dimostrativo.py` | controlla il set dimostrativo e ne scrive l'hash |
| `test_dimostrativo.py` | test dei controlli sul set dimostrativo |
| `set-di-misura/campione.json` | i contratti estratti, per benchmark e insieme |
| `set-di-misura/risposte-giuste.jsonl` | una riga per coppia (contratto, categoria) dei contratti estratti |
| `set-di-misura/conteggi.json` | quanti contratti stanno sotto il tetto, con mediana, p90 e massimo |
| `set-di-misura/token-per-contratto.csv` | i token Qwen3 di ogni contratto dei tre benchmark |
| `NOTICE.md` | attribuzioni e licenze dei dati |

## Uso

```bash
cd consiglio/dati
uv venv -p 3.12.venv && uv pip install -p.venv -r requirements.txt
.venv/bin/python -m pytest -q
.venv/bin/python prepara.py # tetto 24k; con --tetto 12000 il ripiego deciso
.venv/bin/ruff check. &&.venv/bin/ruff format --check.
```

I file scaricati restano in `cache/`, fuori dal repo.
Due giri dello script producono gli stessi file.

## Regole

- **Tetto:** 24.000 token Qwen3, contati sul solo testo del contratto con il tokenizer di Qwen3-14B.
- **Campione:** seme 60, estrazione indipendente per benchmark e insieme.
  - CUAD e ContractNLI: 5 contratti di sviluppo dallo split *train* e 20 di test dallo split *test* ufficiale.
  - CLAUDETTE, che non ha uno split ufficiale: 20 di test, e tutti gli altri sotto il tetto come sviluppo.
- **Risposta giusta:**
  - CUAD: "sì" se c'è almeno un pezzo di testo annotato per una delle 19 categorie. Le risposte vengono da `CUADv1.json`; i file dello split servono solo a sapere in quale insieme sta un contratto.
  - ContractNLI: "sì" se l'ipotesi ha etichetta Contradiction; l'etichetta originale resta nella riga.
  - CLAUDETTE: "sì" se almeno una clausola della categoria ha grado 2 o 3; il grado 3 da solo è nel campo `da_segnalare_grado_3`.
- **Correzioni a CLAUDETTE:** due tag chiusi male nei ToS italiani (Weebly e Yelp), corretti come nella versione inglese degli stessi ToS. Sono in `CORREZIONI_CLAUDETTE`, e lo script si ferma se il testo originale cambia.

## Numeri del campione (tetto 24k)

| Benchmark | Sotto il tetto | Test: coppie | Test: da segnalare | F1 di chi dice sempre "sì" |
|---|---|---|---|---|
| CUAD | train 357/408, test 92/102 | 380 | 74 (19%) | 32,6 |
| ContractNLI | 423/423, 123/123 | 340 | 38 (11%) | 20,1 |
| CLAUDETTE | 42/50 | 180 | 143 (79%) | 88,5 |

Su CLAUDETTE quasi tutte le coppie vanno segnalate: un sistema che dice sempre "sì" prende già F1 88,5.
Il numero va letto contro questa base, oppure sul grado 3 da solo (46 coppie su 180).

## Da rivedere

**Mappa ruolo → categorie per ContractNLI e CLAUDETTE** (`categorie.py`): è una proposta e va rivista da @portapulito prima di far girare quei due benchmark.
Nessuna delle 17 ipotesi di ContractNLI e delle 9 categorie di CLAUDETTE è finanziaria, quindi la finanza resta senza categorie.
In CLAUDETTE la modifica unilaterale comprende anche i cambi di prezzo: è l'unica categoria che si potrebbe dare alla finanza.

## Set dimostrativo

I contratti B2B in italiano scritti dal team stanno in `set-dimostrativo/`, che git ignora: restano fuori dal repo fino alla consegna.
Ogni contratto è un file `<nome>.txt` con accanto la risposta attesa `<nome>.json`, nel formato di "Verdetto e dissenso":

- la raccomandazione (firmare, negoziare o non firmare) con la motivazione;
- le 19 righe CUAD, con citazione e motivazione per le righe a "sì";
- il dissenso atteso: dove è plausibile che la nota di un esperto e il verdetto non siano d'accordo, e chi ha ragione;
- gli importi e le date che il verdetto deve riportare giusti.

```bash
.venv/bin/python dimostrativo.py # controlla citazioni, importi, categorie e dissensi
.venv/bin/python dimostrativo.py --hash # dopo la revisione: scrive set-dimostrativo.sha256
shasum -a 256 -c set-dimostrativo.sha256 # alla consegna, per verificare che il set non sia cambiato
```

Nel repo va solo `set-dimostrativo.sha256`, scritto dopo la revisione di una persona del team.
Chi rivede il set non fa il controllo a mano dell'eval.
