# casa — il link per i giudici

Una vetrina **sempre accesa** su Vercel: i casi registrati sulla MI300X funzionano sempre, le prove dal vivo quando la MI300X è accesa.
Una sola casa per i due progetti fino a G4 (16/10); dopo, solo quello consegnato.

| File | Cosa fa |
|---|---|
| `sorgenti/index.html` | la home: la dimostrazione in cima (gli stessi agenti che si scrivono e che si passano la memoria, con i contatori di `<progetto>/numeri.json`), i progetti, "dal vivo adesso" o la prossima finestra, come verificare un caso |
| `sorgenti/consiglio/prova.html` | la prova dal vivo del Consiglio: il giudice sceglie un contratto CUAD dall'elenco del server e lo fa esaminare adesso; le prove restano nel suo browser, e ognuna si apre come verdetto o a fumetti |
| `sorgenti/sportello/prove.html` | le prove dal vivo: una nostra fattura, i due attacchi della demo, "prova tu a ingannarlo" |
| `api/stato.mjs` | la MI300X è accesa? (chiede `/salute` al motore dello Sportello e al server del Consiglio) |
| `api/consiglio.mjs` | la prova dal vivo del Consiglio: l'elenco dei contratti e una prova, al server del Consiglio con la sua chiave; 409 se è occupato |
| `api/prova.mjs` | porta le prove al motore con la sua chiave; una alla volta (409 se è occupato) |
| `api/decisione.mjs` | la scelta della persona verso il secondo workflow di Evolus; **spenta di base** |
| `lib/comune.mjs` | risposte, corpo della richiesta, chiamata al motore |
| `finestre.json` | le finestre dal vivo dopo il 18/10, da fissare il 12/10 |
| `costruisci.py` | scrive `public/`: home, pagine dei casi registrati con PDF e registro, dati delle prove, Consiglio |
| `locale.mjs` | serve `public/` e le funzioni in locale, senza la CLI di Vercel |
| `mi300x/` | la MI300X a finestre: nasce da uno snapshot quando serve e si distrugge quando non serve (README lì) |
| `test/` | i test delle funzioni, con un motore e un Evolus finti, e di `mi300x/` con un'API di DigitalOcean finta |

## Costruire e pubblicare

```bash
# dalla radice del repo, con l'ambiente di sportello/servizio (pagina, generatore, attacchi)
sportello/servizio/.venv/bin/python casa/costruisci.py --insieme sportello/dati/insiemi/sviluppo \
    --giro <risultati>/telepatia.jsonl --registri <risultati>/registro/telepatia --registrato "15/10/2026 on the MI300X" \
    --consiglio <pagine del verdetto> # fino a G4
cd casa && vercel deploy --prod # la CLI: il piano gratuito non collega i repo di un'organizzazione 
```

- **Nessun IBAN intero** esce dai PDF: `costruisci.py` controlla ogni HTML e JSON di `public/` e si ferma se ne trova uno.
- **Le scelte dei giudici restano nel loro browser**: le pagine dei giudici si costruiscono senza `--api-decisione`.

## Variabili d'ambiente su Vercel

| Variabile | Per | Note |
|---|---|---|
| `MOTORE_URL` | stato, prove, decisione | l'indirizzo pubblico del server del motore, con TLS |
| `MOTORE_SEGRETO` | stato, prove, decisione | lo stesso `SPORTELLO_SEGRETO` del server |
| `CONSIGLIO_URL` | stato, prova dal vivo del Consiglio | l'indirizzo pubblico del server del Consiglio, con TLS, acceso con `--dal-vivo` |
| `CONSIGLIO_SEGRETO` | stato, prova dal vivo del Consiglio | lo stesso `CONSIGLIO_SEGRETO` del server |
| `EVOLUS_ATTIVO` | decisione | `1` solo per le riprese del video e per il palco: ogni giro Evolus costa crediti |
| `EVOLUS_WORKFLOW`, `EVOLUS_API_KEY`, `EVOLUS_SPAZIO` | decisione | il secondo workflow, `POST https://api.evolus.ai/api/v1/workflows/{id}/execute` in multipart con `X-ApiKey` e `X-Application-Id`, come nella [pagina per sviluppatori](https://evolus.ai/en/developers). Id e chiave da «When it starts» › «Trigger via webhook», lo "Space ID" da «Your company» › «API keys». I parametri `id_caso`, `decisione`, `chi`, `nota` vanno dichiarati nel workflow (`sportello/servizio/EVOLUS.md`, passo 5) |
| `EVOLUS_URL` | decisione | solo se l'indirizzo dell'API non è `https://api.evolus.ai` |

Le chiavi stanno solo qui: il browser non le vede mai, e nessuna funzione le rimanda indietro (lo controllano i test).

## Le prove dal vivo

Il server del motore parte con `--demo` (vedi `sportello/servizio`): così esistono `POST /prove/fattura`, `/prove/attacco` e `/prove/inganna`.

- **Una nostra fattura:** due pulite per lingua e una per ogni anomalia del catalogo, in telepatia o a testo.
- **Attacco 1, manomissione in transito** (F1): dopo la firma l'IBAN cambia nell'etichetta del messaggio, e il sigillo deve rompersi.
- **Attacco 2, testo nascosto** (F4, ripiego F3 secondo la regola): in telepatia o a testo, con l'interruttore del livello 2, che esiste solo qui.
- **"Prova tu a ingannarlo":** il giudice scrive il testo nascosto su una nostra fattura pulita, fino a 300 caratteri latini. Emoji e altri alfabeti nel PDF diventerebbero ■ e non arriverebbero al modello, quindi si rifiutano subito.

Il caso che nasce resta nel browser del giudice e si apre con `sportello/dal-vivo.html?id=…`; anche le sue proposte compaiono nell'indice dello Sportello.

## Provare in locale

Il modo più semplice: `CASA=1./sportello/prova.sh` (passo `50-casa.sh` della prova per i colleghi), che costruisce la casa con i casi della prova e accende motore e funzioni su http://localhost:3000. A mano:

```bash
export SPORTELLO_SEGRETO=$(openssl rand -hex 32)
cd sportello/servizio &&.venv/bin/python -m servizio../dati/insiemi/sviluppo --modello Qwen/Qwen3-0.6B --demo --porta 8766 \
    --link "http://localhost:3000/sportello/dal-vivo.html?id={id}" &
cd casa && MOTORE_URL=http://127.0.0.1:8766 MOTORE_SEGRETO=$SPORTELLO_SEGRETO node locale.mjs # http://localhost:3000
npm test # le funzioni
```

## Cosa manca

- **Le finestre dopo il 18/10** (`finestre.json`) e **la MI300X che nasce da uno snapshot al mattino e si distrugge la sera**: si decidono il 12/10, quando si sa cosa dà l'organizzazione.
- **I casi registrati** sulla MI300X, entro il 17/10.
- **La pubblicazione su Vercel** (account e progetto del team).
