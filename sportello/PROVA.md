# Provare lo Sportello telepatico

Un comando prepara tutto, genera le fatture di sviluppo, fa girare lo Sportello in telepatia e a testo e stampa il riepilogo.

```bash
git clone https://github.com/AIVolve-Team/the-silent-council.git
cd the-silent-council
git checkout prova/sportello # pipeline e motore insieme, finché le e non sono in main
./sportello/prova.sh
```

Meglio lanciarlo da un terminale che chiederlo a Claude Code: può durare più di un'ora, e quando la memoria si riempie Claude Code può fermare i comandi che ha lanciato lui.
Mentre gira, il Mac non va in stop da solo: basta tenerlo collegato alla corrente e con il coperchio aperto.

Il repo è privato: serve l'accesso all'organizzazione AIVolve-Team. Se `git clone` chiede una password, basta `gh auth login` una volta e poi `gh repo clone AIVolve-Team/the-silent-council`.

## Cosa serve

- **Un Mac con chip Apple e almeno 64 GB di memoria**, oppure Linux con una GPU da almeno 48 GB, per usare **Qwen3-14B**, il modello dello Sportello. Con meno memoria lo script sceglie da solo un modello più piccolo (8B, 4B, 1.7B), che serve solo a vedere che tutto gira.
- **Circa 40 GB liberi su disco**: 30 per il modello, il resto per librerie e risultati.
- **Internet** per il primo giro.
- **Nient'altro**: Python e librerie li prepara lo script; se manca `uv`, il gestore di Python, lo installa nella cartella dell'utente, senza `sudo`.

## Cosa fa

| Passo | Cosa | Tempo, la prima volta |
|---|---|---|
| 1 | Guarda memoria e GPU, sceglie il modello | subito |
| 2 | Python 3.12 e librerie, alle versioni fissate, in `sportello/.venv` | qualche minuto |
| 3 | Test veloci di motore, dati, controllore e pipeline, senza modello | un minuto |
| 4 | Genera le 100 fatture di sviluppo (seme 101) e ne controlla l'impronta | subito |
| 5 | Scarica il modello: Qwen3-14B pesa circa 30 GB | dipende dalla rete |
| 6 | Fa esaminare le fatture allo Sportello, in telepatia e a testo | da misurare al primo giro |

Con `--tutte` esamina tutte le 100 fatture di sviluppo; con `FATTURE=3` solo le prime 3. Rilanciarlo è sicuro: le fatture già esaminate non si rifanno.

### I passi in più

Dopo il riepilogo lo script esegue i passi di `sportello/prova.d/`, uno per ogni pezzo dello Sportello che fa girare il modello. Se uno si ferma, gli altri vanno avanti; alla fine lo script elenca dove guardare.

| Passo | Ticket | Cosa | Come si spegne |
|---|---|---|---|
| `20-pagine.sh` | | Le pagine dei casi in telepatia e l'indice con le proposte da approvare, come le vedrebbe la persona: si aprono nel browser. | |
| `30-attacchi.sh` | | La manomissione in transito (F1) e i 10 testi nascosti (F4), in telepatia e a testo, cioè 21 esami. Il rapporto dice chi li ferma e se la sola coerenza blocca almeno 8 F4 su 10: è la regola dell'attacco 2 dal vivo. | `SENZA_ATTACCHI=1` |
| `40-servizio.sh` | | Il motore chiamato come lo chiama l'agente in Evolus: il server con i due tool, una fattura esaminata con `esamina_fattura` via MCP e via HTTP (deve tornare lo stesso caso), poi `registra_decisione`. | |
| `50-casa.sh` | | La casa per i giudici in locale: home, casi di questa prova con il registro da scaricare, e le prove dal vivo (una nostra fattura, i due attacchi, "prova tu a ingannarlo") con il motore acceso. Si apre su http://localhost:3000; serve Node.js 20 o più recente. | parte solo con `CASA=1` |

Per provare la casa senza rifare la pipeline basta rilanciare con `CASA=1 SENZA_ATTACCHI=1./sportello/prova.sh`: le fatture già esaminate non si rifanno. La casa resta accesa finché non premi Ctrl-C.

### Cosa non prova

- **La parte Evolus** (email, agente principale Qwen3.6 su vLLM, connettore MCP): gira solo sull'AMD Developer Cloud.
- **G2 e l'esame veri**: il riepilogo qui sopra è l'anteprima di G2; il giro pre-registrato a 10, 20 e 40 passi latenti si fa sulla MI300X.
- **G1**: misura la memoria e la velocità sulla MI300X.

## Cosa guardare

Alla fine lo script stampa una tabella per modalità:

- **Esito giusto:** quante fatture hanno l'esito atteso (pagare, persona, bloccare).
- **Pagamenti dannosi:** fatture che andavano bloccate e che lo Sportello pagherebbe. Devono essere **zero**.
- **Blocchi ingiusti:** fatture pulite bloccate.
- **Lettura giusta:** quanti degli 8 dati critici (fornitore, numero e data, totale, IBAN, importo e scadenza, ordine) il verificatore ricava giusti dalla memoria, senza vedere la fattura. È l'**anteprima di G2**: la telepatia deve stare al massimo 3 punti sotto il testo.
- **Token e secondi per fattura**, nei due modi.

Sono numeri delle **fatture di sviluppo**, per capire come va: i numeri per la giuria vengono dall'esame del 16/10, sulla MI300X.

Nella cartella `sportello/risultati-prova/` ci sono anche le righe complete di ogni fattura e il **registro di ogni caso**: i messaggi firmati e le chiavi pubbliche, che chiunque può verificare con il comando stampato alla fine. Le fatture sono inventate dal generatore, quindi i risultati si possono condividere liberamente.
