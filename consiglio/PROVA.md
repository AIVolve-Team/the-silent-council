# Provare il Consiglio silenzioso

Un comando prepara tutto, fa girare il Consiglio sui contratti e apre la pagina del verdetto.

```bash
git clone https://github.com/AIVolve-Team/the-silent-council.git
cd the-silent-council
git checkout feat/pagina-verdetto
./consiglio/prova.sh
```

Su Mac c'è anche `consiglio/prova.command`: con un doppio clic nel Finder la prova parte in una finestra del Terminale tutta sua, che alla fine resta aperta con il riepilogo. Per farla partire da Claude Code vedi [Con Claude Code](#con-claude-code).

Mentre gira, il Mac non va in stop da solo: basta tenerlo collegato alla corrente e con il coperchio aperto.

Il repo è privato: serve l'accesso all'organizzazione AIVolve-Team, lo stesso con cui si vedono i ticket. Se `git clone` chiede una password, basta `gh auth login` una volta e poi `gh repo clone AIVolve-Team/the-silent-council` al posto della prima riga.

## Cosa serve

- **Un Mac con chip Apple e almeno 64 GB di memoria**, oppure Linux con una GPU NVIDIA da almeno 48 GB, per usare **Qwen3-14B**, il modello del Consiglio. Con meno memoria lo script sceglie da solo un modello più piccolo (8B, 4B), che serve solo a vedere che tutto funziona. Su un PC conta la memoria della scheda video, non la RAM: con una GPU da 24 GB lo script usa il 4B.
- Sotto gli 80 GB il contratto CUAD più lungo (22.863 token) si salta: il Consiglio ne terrebbe in memoria fino a tre copie, e con il 14B si stimano circa 46 GB solo per quel contratto.
- **Circa 40 GB liberi su disco**: 30 per il modello, il resto per dati e librerie.
- **Internet** per il primo giro.
- **Nient'altro**: Python e librerie li prepara lo script. Se manca `uv`, il gestore di Python, lo installa nella cartella dell'utente, senza `sudo`.

Su Windows lo script va lanciato dentro WSL2 (Ubuntu).

## Cosa fa

| Passo | Cosa | Tempo, la prima volta |
|---|---|---|
| 1 | Guarda memoria e GPU, sceglie il modello | subito |
| 2 | Python 3.12 e librerie, alle versioni fissate, in `consiglio/.venv` | qualche minuto |
| 3 | Test veloci di motore, dati e Consiglio, senza modello | un minuto |
| 4 | Scarica CUAD, ContractNLI e CLAUDETTE e ne controlla le impronte | un minuto |
| 5 | Cerca il set dimostrativo e ne controlla le impronte (vedi sotto) | subito |
| 6 | Scarica il modello: Qwen3-14B pesa circa 30 GB | dipende dalla rete |
| 7 | Fa girare il Consiglio, in telepatia e a testo | vedi sotto |
| 8 | Scrive le pagine del verdetto e apre la prima | subito |

Con Qwen3-14B su un Mac da 64 GB, il passo 7 dovrebbe durare **circa 2-3 ore** per il giro completo (4 contratti dimostrativi e 4 CUAD, ognuno in telepatia e a testo), di più sui chip meno recenti. Con `--veloce` gira solo la telepatia sui contratti dimostrativi: **circa mezz'ora**.

Rilanciarlo è sicuro: quello che è già scaricato non si riscarica, e i risultati del giro precedente vengono sovrascritti.

## Cosa guardare

Alla fine lo script stampa un riepilogo per ogni giro e apre la pagina del primo contratto.

- **La pagina del verdetto** (`consiglio/risultati-prova/pagine/`): raccomandazione, clausole da segnalare, dissenso fra gli esperti, citazioni con il bollino "trovata nel contratto". Ce n'è una per contratto e per modalità.
- **Il riepilogo** di ogni giro:
  - verdetti e note validi;
  - F1, cioè il voto da 0 a 100 sulle clausole trovate, con accanto la base "sempre sì";
  - token scritti e letti e secondi per contratto.

  Il confronto che conta è **telepatia contro testo**: stessa qualità (al massimo 3 punti di F1 in meno) con meno token e meno tempo.
- **Le revisioni complete** (`consiglio/risultati-prova/*.jsonl`): tutto quello che hanno scritto esperti e relatore, con confidenze, dissensi, token e tempi.

Sono numeri del **set di sviluppo**, per capire come va. I numeri per la giuria vengono dall'eval pre-registrato, sul set di test e sulla MI300X.

## Con Claude Code

Se la prova la chiedi a Claude Code, queste sono le regole per lui:

- **Non si modifica niente.** Niente file cambiati, niente pacchetti installati a mano, niente modello diverso: fa tutto `prova.sh`.
- **Il modello lo scarica lo script:** Qwen3-14B da Hugging Face, a una revisione fissata. Un Qwen già installato con Ollama o LM Studio non si può usare: il Consiglio passa da un agente all'altro la memoria interna del modello (la cache KV), e quei programmi non la danno.
- **La prova parte fuori da Claude Code**, in una finestra del Terminale tutta sua:

  ```bash
  open consiglio/prova.command
  ```

  Il giro dura ore e usa molta memoria: un comando lanciato dentro Claude Code può essere fermato quando la memoria si riempie. La prima volta macOS può chiedere il permesso di far aprire la cartella al Terminale: va accettato.
- **Per seguirla** basta leggere `consiglio/risultati-prova/prova.log`, che cresce mentre la prova va avanti. Alla fine c'è il riepilogo di ogni giro: va spiegato in parole semplici, mettendo a confronto telepatia e testo (F1, token, secondi). Le pagine del verdetto sono in `consiglio/risultati-prova/pagine/`.
- **Se si ferma, niente correzioni:** si riportano il messaggio d'errore e le ultime righe di `prova.log`.

## Il set dimostrativo

I 4 contratti italiani scritti dal team **non stanno nel repo** fino alla consegna. Lo script li cerca in due posti:

1. nella cartella `consiglio/dati/set-dimostrativo/`, se qualcuno del team te li ha passati;
2. nel repo privato `AIVolve-Team/consiglio-set-dimostrativo`, che lo script scarica da solo con lo stesso accesso usato per il clone, senza chiedere password.

In entrambi i casi controlla che le impronte coincidano con `consiglio/dati/set-dimostrativo.sha256`. Senza il set dimostrativo il giro usa solo i contratti CUAD, e le pagine sono di quelli.

Per regola, chi ha scritto o rivisto le risposte attese del set dimostrativo non fa il controllo a mano dell'eval.

## Se qualcosa non va

- **Il Mac rallenta molto o va in swap:** chiudi le applicazioni pesanti (macchine virtuali, browser con molte schede) e rilancia. Oppure prova prima `./consiglio/prova.sh --veloce`.
- **Vuoi un altro modello:** `MODELLO=Qwen/Qwen3-8B./consiglio/prova.sh`.
- **Tutto quello che è successo** è in `consiglio/risultati-prova/prova.log`: in caso di problemi basta mandare quel file.
