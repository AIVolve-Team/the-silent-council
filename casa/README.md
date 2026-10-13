# casa — il link per i giudici

Una vetrina **sempre accesa** su Vercel per il **Consiglio silenzioso**: i verdetti registrati sulla MI300X funzionano sempre, le prove dal vivo quando la MI300X è accesa.
Lo Sportello è stato tolto dal repo il 13/10: è escluso dall'hackathon, e resta nella storia git e nel tag `archivio/sportello`.

| File | Cosa fa |
|---|---|
| `sorgenti/index.html` | la home: la dimostrazione in cima (gli stessi agenti che si scrivono e che si passano la memoria, con i contatori di `<progetto>/numeri.json`), i progetti, "dal vivo adesso" o la prossima finestra, come verificare un caso |
| `sorgenti/consiglio/prova.html` | la prova dal vivo del Consiglio: il giudice sceglie un contratto CUAD dall'elenco del server e lo fa esaminare adesso; le prove restano nel suo browser, e ognuna si apre come verdetto o a fumetti |
| `api/stato.mjs` | la MI300X è accesa? (chiede `/salute` al server del Consiglio) |
| `api/consiglio.mjs` | la prova dal vivo del Consiglio: l'elenco dei contratti e una prova, al server del Consiglio con la sua chiave; 409 se è occupato |
| `lib/comune.mjs` | risposte, corpo della richiesta, chiamata al server del Consiglio |
| `finestre.json` | le finestre dal vivo dopo il 18/10, da fissare il 12/10 |
| `costruisci.py` | scrive `public/`: la home e le pagine del Consiglio |
| `locale.mjs` | serve `public/` e le funzioni in locale, senza la CLI di Vercel |
| `mi300x/` | la MI300X a finestre: nasce da uno snapshot quando serve e si distrugge quando non serve (README lì) |
| `test/` | i test delle funzioni, con un server del Consiglio finto, e di `mi300x/` con un'API di DigitalOcean finta |

## Costruire e pubblicare

```bash
# dalla radice del repo: basta Python 3, senza dipendenze
python3 casa/costruisci.py --consiglio <pagine del verdetto> [--repo https://github.com/…]
cd casa && vercel deploy --prod # la CLI: il piano gratuito non collega i repo di un'organizzazione 
```

- **Nessun IBAN intero** esce dai PDF: `costruisci.py` controlla ogni HTML e JSON di `public/` e si ferma se ne trova uno.
- **Le scelte dei giudici restano nel loro browser**.

## Variabili d'ambiente su Vercel

| Variabile | Per | Note |
|---|---|---|
| `CONSIGLIO_URL` | stato, prova dal vivo del Consiglio | l'indirizzo pubblico del server del Consiglio, con TLS, acceso con `--dal-vivo` |
| `CONSIGLIO_SEGRETO` | stato, prova dal vivo del Consiglio | lo stesso `CONSIGLIO_SEGRETO` del server |

Le chiavi stanno solo qui: il browser non le vede mai, e nessuna funzione le rimanda indietro (lo controllano i test).

## Le prove dal vivo

Il server del Consiglio parte con `--dal-vivo` (vedi `consiglio/servizio`): il giudice sceglie un contratto dall'elenco del server, mai un testo suo, e lo fa esaminare adesso. Una prova alla volta: se il Consiglio è occupato, 409.

## Provare in locale

```bash
python3 casa/costruisci.py --consiglio <pagine del verdetto>
cd casa && CONSIGLIO_URL=http://127.0.0.1:8001 CONSIGLIO_SEGRETO=$CONSIGLIO_SEGRETO node locale.mjs # http://localhost:3000
npm test # le funzioni
```

## Cosa manca

- **Le finestre dopo il 18/10** (`finestre.json`) e **la MI300X che nasce da uno snapshot al mattino e si distrugge la sera**: si decidono il 12/10, quando si sa cosa dà l'organizzazione.
- **I verdetti registrati** sulla MI300X, entro il 17/10.
- **La pubblicazione su Vercel** (account e progetto del team).
