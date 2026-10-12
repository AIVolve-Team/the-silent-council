# Provare il Consiglio silenzioso

Un comando prepara tutto, fa girare il Consiglio sui contratti e apre la pagina del verdetto.

```bash
git clone https://github.com/AIVolve-Team/the-silent-council.git
cd the-silent-council
./consiglio/prova.sh
```

Dal 12/10/2026 tutto il lavoro sta su `main`, il ramo su cui parte il clone. Chi aveva già clonato il repo passa a `main` con `git fetch origin && git checkout -B main origin/main`, anche se il suo `main` era rimasto indietro; se ci sono modifiche non salvate git si ferma, e prima serve `git stash`.

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

Il riepilogo ha anche due numeri che dicono **dove si perde una segnalazione**, se negli esperti o nel relatore:

- **note come verdetto**: l'F1 che avrebbe il Consiglio se il verdetto si facesse mettendo insieme le note degli esperti;
- **note e verdetto d'accordo**: su quante categorie il relatore dice lo stesso dell'esperto che le guarda.

Se le note vanno bene e il verdetto no, il problema è nel relatore.

## La prova di diagnosi

Con Qwen3-14B, nella prova dell'8/10, in telepatia le note degli esperti erano buone mentre il verdetto del relatore no. La diagnosi serve a capire perché:

```bash
./consiglio/prova.sh --diagnosi
```

Su Mac c'è anche `consiglio/diagnosi.command`, che fa la stessa cosa in una finestra del Terminale tutta sua (doppio clic nel Finder, oppure `open consiglio/diagnosi.command`).

- Gira **solo la telepatia** e **solo sui 4 contratti del set dimostrativo**, che quindi deve esserci (vedi [Il set dimostrativo](#il-set-dimostrativo)).
- **Spegne il riallineamento** dei passi latenti: è una correzione dei "pensieri" degli esperti prima di passarli avanti (la matrice W_a di LatentMAS). Nel Consiglio è accesa, in LatentMAS è spenta di default.
- Fa **tre giri**, con 0, 10 e 40 passi latenti, cioè i passi in cui ogni esperto "pensa" senza scrivere. Il modello si carica una volta sola.
- Con Qwen3-14B su un Mac M1 Max da 64 GB dura **circa un'ora**. Con modelli più piccoli dell'8B il riallineamento non cambia quasi niente: la prova serve solo a vedere che tutto funziona.
- I risultati vanno in `consiglio/risultati-prova/diagnosi/`, così quelli della prova normale restano. Alla fine lo script prepara lo zip `consiglio/risultati-prova/diagnosi.zip`.
- **Lo zip contiene frasi del set dimostrativo:** va mandato in privato a chi l'ha chiesto, mai su GitHub.

Come si leggono i numeri, confrontandoli con la prova dell'8/10 (10 passi con riallineamento):

- **con 0 passi** il relatore riceve solo la memoria di quello che gli esperti hanno letto, senza "pensieri": se il verdetto resta rotto, il relatore non riesce a ritrovare le informazioni nella memoria degli altri senza avere il contratto davanti;
- se invece **con 0 e 10 passi senza riallineamento** il verdetto torna vicino a quello a testo, il colpevole è il riallineamento;
- se va bene con 0 passi ma non con 10, anche senza riallineamento, a confondere il relatore sono i "pensieri" stessi.

## La verifica su CUAD

La diagnosi del 12/10 ha dato la colpa al riallineamento: senza, la telepatia sul set dimostrativo arriva a F1 98,2, con 0, 10 e 40 passi. Prima di congelare la pre-registrazione va confermato sui contratti CUAD di sviluppo, dove si misura G4:

```bash
./consiglio/prova.sh --diagnosi-cuad
```

Su Mac c'è anche `consiglio/diagnosi-cuad.command` (doppio clic nel Finder, oppure `open consiglio/diagnosi-cuad.command`).

- Gira **solo sui CUAD di sviluppo**. Su un Mac sotto gli 80 GB sono i 4 contratti fino a 14.000 token, gli stessi della prova dell'8/10. Il set dimostrativo non serve.
- **Telepatia senza riallineamento con 0 e 10 passi:** 0 è il valore da confermare, 10 serve al controllo dei pensieri azzerati.
- **Testo rifatto con il codice di oggi**, così il confronto con la telepatia è pulito. Il testo dell'8/10 veniva da un codice più vecchio.
- Con Qwen3-14B su un Mac M1 Max da 64 GB dura **circa un'ora e un quarto**.
- I risultati vanno in `consiglio/risultati-prova/diagnosi-cuad/`, e alla fine lo script prepara lo zip `consiglio/risultati-prova/diagnosi-cuad.zip`.
- **Lo zip contiene solo contratti CUAD, che sono pubblici:** niente del set dimostrativo.

## Con Claude Code

Se la prova la chiedi a Claude Code, queste sono le regole per lui:

- **Sempre in un clone nuovo**, fatto apposta per la prova, anche se il repo è già sul computer: mai in una cartella dove lavorano altre sessioni di Claude Code o altre persone. Se qualcuno cambia ramo in quella cartella mentre la prova gira, la prova si ferma a metà, per esempio con `No module named revisione.esegui`.

  ```bash
  CARTELLA=~/consiglio-prova-$(date +%Y%m%d-%H%M)
  git clone https://github.com/AIVolve-Team/the-silent-council.git "$CARTELLA"
  ```

  Il modello non si riscarica, perché sta nella cache di Hugging Face fuori dal clone, e il set dimostrativo lo riprende da solo lo script dal repo privato. Se invece il set te l'avevano passato a mano, va copiato in `consiglio/dati/set-dimostrativo/` del clone nuovo.
- **Non si modifica niente.** Niente file cambiati, niente pacchetti installati a mano, niente modello diverso: fa tutto `prova.sh`.
- **Il modello lo scarica lo script:** Qwen3-14B da Hugging Face, a una revisione fissata. Un Qwen già installato con Ollama o LM Studio non si può usare: il Consiglio passa da un agente all'altro la memoria interna del modello (la cache KV), e quei programmi non la danno.
- **La prova parte fuori da Claude Code**, in una finestra del Terminale tutta sua:

  ```bash
  open consiglio/prova.command
  ```

  Per la [prova di diagnosi](#la-prova-di-diagnosi) il comando è `open consiglio/diagnosi.command`, per la [verifica su CUAD](#la-verifica-su-cuad) `open consiglio/diagnosi-cuad.command`.

  Il giro dura ore e usa molta memoria: un comando lanciato dentro Claude Code può essere fermato quando la memoria si riempie. La prima volta macOS può chiedere il permesso di far aprire la cartella al Terminale: va accettato.
- **Per seguirla** basta leggere `consiglio/risultati-prova/prova.log` (per la diagnosi `consiglio/risultati-prova/diagnosi/prova.log`, per la verifica su CUAD `consiglio/risultati-prova/diagnosi-cuad/prova.log`), che cresce mentre la prova va avanti.
  - È finita quando in fondo al log compare la riga che comincia con `Fatto.`.
  - Si è fermata se `pgrep -f consiglio/prova.sh` non trova più niente e quella riga non c'è.
- **Alla fine** il log ha il riepilogo di ogni giro: va spiegato in parole semplici, mettendo a confronto telepatia e testo (F1, token, secondi). Le pagine del verdetto sono in `consiglio/risultati-prova/pagine/`.
  Nella diagnosi invece si confrontano i tre giri (0, 10 e 40 passi) e si ricorda di mandare lo zip in privato.
  Nella verifica su CUAD si confronta la telepatia con 0 passi con il testo, e la telepatia con 0 passi con quella con 10.
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
