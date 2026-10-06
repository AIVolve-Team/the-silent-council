# Hackathon AMD ACT III

Il linguaggio comune dei progetti del team per l'AMD Developer Hackathon ACT III.
Contiene i termini del Consiglio silenzioso, la revisione di contratti in telepatia, e quelli del motore telepatico e della macchina della verità, condivisi con lo sportello.

## Language

### Consiglio silenzioso: contratti di prova

**Set di misura**:
I contratti presi da benchmark pubblici con cui si misura il Consiglio. È l'unica fonte dei numeri da portare alla giuria.
_Avoid_: dataset di test, benchmark (quando si intende il sottoinsieme scelto)

**Set dimostrativo**:
I pochi contratti B2B in italiano scritti dal team per la demo, con verdetto e dissenso attesi. Non entra mai nei numeri.
_Avoid_: contratti di prova, contratti sintetici, i 20 contratti

**Clausola da segnalare**:
Una clausola che un revisore porta all'attenzione della persona, qualunque parte del contratto sia. Conta che ci sia, non per chi è un problema.
_Avoid_: clausola rischiosa, clausola abusiva, red flag

**Risposta giusta**:
Per ogni coppia (contratto, categoria), se va segnalata sì o no, con i pezzi di testo che lo provano. È scritta prima di misurare.
_Avoid_: ground truth, gold, etichetta

### Motore telepatico e macchina della verità

**Messaggio latente**:
Quello che un agente passa al successivo al posto del testo: la memoria di ciò che ha letto e dei suoi passi latenti, con un'etichetta. Ce n'è uno per agente, e in fila ridanno la memoria dell'intera staffetta.
_Avoid_: busta (solo in conversazione), KV cache (quando si intende il messaggio intero), embedding

**Staffetta**:
La sequenza di agenti in cui ognuno riceve i messaggi latenti dei precedenti e aggiunge il suo. Esiste in modalità telepatia e in modalità testo, con gli stessi agenti e gli stessi prompt.
_Avoid_: pipeline, catena (quando si intende la sequenza di agenti)

**Sigillo**:
La firma digitale di un agente sul suo messaggio latente, che copre tutto il messaggio più il numero progressivo e l'hash del messaggio precedente. Dice che nessuno ha toccato il messaggio dopo la firma, non che il contenuto sia vero.
_Avoid_: HMAC, hash (quando si intende il sigillo), crittografato

**Impegno**:
Nello sportello, i dati della fattura che l'estrattore dichiara in chiaro accanto al suo messaggio latente, in JSON con schema fisso. Sta nell'etichetta, quindi è coperto dal sigillo.
_Avoid_: estrazione, output dell'estrattore, commitment

**Lettura**:
I dati critici della fattura che il verificatore ricava dal messaggio latente, senza vedere la fattura. Si confronta con l'impegno: se non coincidono, l'agente ha trasportato nella memoria qualcosa di diverso da quello che ha dichiarato.
_Avoid_: verifica (quando si intende la lettura), seconda estrazione

### Sportello: anomalie e attacchi

**Azione dannosa**:
Ciò che lo sportello non deve mai fare, scritto come regola pubblicabile: pagare due volte, pagare un beneficiario diverso da quello registrato, pagare un fornitore sconosciuto o disattivato, pagare più del dovuto, pagare senza ordine.
_Avoid_: errore, rischio (quando si intende l'azione da impedire)

**Anomalia**:
Un difetto della fattura rispetto a ordine e anagrafica, che il generatore inserisce nelle fatture di prova. Ognuna ha un esito atteso: pagare, passare a una persona o bloccare.
_Avoid_: attacco, frode (quando si intende il difetto inserito)

**Attacco**:
Una manipolazione del sistema, non della fattura: per esempio un messaggio latente manomesso o un testo nascosto nel PDF. Lo fermano il sigillo e la coerenza.
_Avoid_: anomalia
