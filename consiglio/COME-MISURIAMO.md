# Come misuriamo il Consiglio

Una spiegazione per tutto il team, senza codice: cosa misura l'eval del Consiglio, come dà i punteggi e come si confrontano i sistemi.
Le regole ufficiali, fissate prima di misurare, sono nella pre-registrazione: [`consiglio/PREREGISTRAZIONE.md`](PREREGISTRAZIONE.md).

## 1. La domanda

Dato un contratto, **quali tipi di clausola contiene?**
Su CUAD, il benchmark principale, i tipi sono 19: per esempio "limitazione di responsabilità", "esclusiva", "rinnovo automatico", "divieto di concorrenza".
Per ogni contratto e ogni tipo la risposta è **sì o no**.

## 2. Il materiale: contratti con le risposte giuste

- **CUAD** è un dataset pubblico di contratti commerciali reali in cui **avvocati** hanno annotato, clausola per clausola, dove si trova ogni tipo.
- Da quelle annotazioni viene la **risposta giusta**: "sì" se gli avvocati hanno trovato almeno un pezzo di quel tipo nel contratto, "no" altrimenti.
- Il test usa **20 contratti** che nessuno ha guardato durante lo sviluppo. Con 19 tipi fanno **380 domande** con risposta nota.

L'unità di misura è la **coppia (contratto, tipo di clausola)**.

## 3. Il flusso: cosa succede a ogni contratto

1. Il contratto va al sistema da valutare.
2. Il sistema restituisce un **verdetto** in un formato fisso, uguale per tutti:
   - per ognuno dei 19 tipi, **sì o no**;
   - per i "sì", una **citazione** dal contratto come prova;
   - una **raccomandazione**: firmare, negoziare o non firmare.
3. Si registrano i **costi**: token letti, token generati, secondi.
4. Si registra la **confidenza**: per ogni sì/no, la probabilità che il modello gli dava, letta dalle sue probabilità interne.
5. Si confronta il verdetto con le risposte giuste.

## 4. I sistemi a confronto

Lo stesso modello, **Qwen3-14B**, con le stesse regole di decodifica, sulla stessa MI300X. Cambia solo come è organizzato il lavoro.

| Configurazione | Come lavora | A cosa serve |
|---|---|---|
| **Agente solo** | Un modello legge tutto il contratto e decide | Serve davvero un gruppo? |
| **Voto fra 4** | Quattro esperti leggono tutto, ognuno per conto suo; vince la maggioranza | Basta un gruppo che non comunica? |
| **Consiglio a testo** | Tre esperti leggono una sezione ciascuno e si scrivono le analisi; un relatore decide | Il gruppo che comunica scrivendo |
| **Consiglio in telepatia** | Come sopra, ma gli esperti si passano la **memoria di lettura** invece di scriverla | Il nostro sistema |
| **Contratto scambiato** | Il sistema legge un contratto e lo si valuta con le risposte di un altro | Controllo: il punteggio deve crollare |

## 5. Come si dà il punteggio

Ogni coppia (contratto, tipo) finisce in una di quattro caselle:

| | Risposta giusta **sì** | Risposta giusta **no** |
|---|---|---|
| Il sistema dice **sì** | ✅ trovata (vero positivo) | ❌ falso allarme |
| Il sistema dice **no** | ❌ mancata | ✅ giusto silenzio |

Da queste caselle, sommate su tutti i contratti:

- **Precisione:** delle clausole che il sistema ha segnalato, quante erano vere? Misura i **falsi allarmi**.
- **Richiamo:** delle clausole vere, quante ne ha trovate? Misura quelle **sfuggite**.
- **F1:** la media armonica fra precisione e richiamo, da 0 a 100. È **il voto principale**. È alta solo se il sistema trova le clausole **senza inventarne**: chi segnala tutto ha richiamo alto e precisione bassa, chi segnala poco il contrario, e in entrambi i casi l'F1 resta bassa.
- **MCC:** da −1 a 1. Tiene conto anche dei "no" giusti ed è utile quando i "sì" sono pochi.
- **"Sempre sì":** l'F1 di un sistema finto che dice sempre sì. È il **pavimento**: su CUAD di test vale 32,6, e un sistema serio deve stare ben sopra.

### Un esempio

Un contratto ha 4 clausole vere fra i 19 tipi. Il sistema ne segnala 5: 3 giuste e 2 sbagliate.
- Precisione = 3 / 5 = 60%
- Richiamo = 3 / 4 = 75%
- F1 = 2 × 60 × 75 / (60 + 75) ≈ 67

L'F1 ufficiale **non** è la media delle F1 dei singoli contratti: si sommano trovate, falsi allarmi e mancate di **tutti** i contratti e si calcola l'F1 una volta sola.

### Due regole di severità

- **Verdetto non valido o mancante:** conta come "no" su tutti i suoi tipi, e si riporta a parte. Chi sbaglia il formato non viene premiato.
- **F1 severa:** un "sì" giusto vale solo se la **citazione** coincide con il pezzo annotato dagli avvocati, con almeno 5 parole di fila in comune. Controlla che il sistema abbia trovato **la** clausola, non che abbia indovinato.

## 6. Il costo

- **Token generati:** quanto scrive il sistema, cioè note, analisi e verdetto. Sulla GPU ogni token generato è tempo di calcolo.
- **Token letti:** quanto testo il modello elabora in ingresso.
- **Secondi per contratto:** tempo reale sulla MI300X, un contratto alla volta (batch 1), così i tempi sono confrontabili.

## 7. Come si confrontano due sistemi

Con 20 contratti una differenza di 2-3 punti di F1 può essere fortuna. Per capirlo si usa il **bootstrap appaiato**:

1. si estraggono a caso 20 contratti fra i 20, con ripetizioni, **gli stessi per i due sistemi**;
2. si ricalcola la differenza di F1;
3. si ripete **10.000 volte**, con un seme fisso.

Ne esce un **intervallo al 95%**, per esempio "telepatia meno testo: da −4 a +7 punti". Se l'intervallo contiene lo zero, la differenza non è sicura.

## 8. Il criterio di successo (G4, su CUAD)

Il Consiglio in telepatia è **consegnabile** se:

1. **qualità:** F1 della telepatia ≥ F1 del testo − 3 punti. Per dire *"non perde, dimostrato"* anche il **limite inferiore** dell'intervallo deve stare entro −3;
2. **costo:** almeno il **50% di token generati in meno** del testo;
3. **velocità:** la telepatia non è più lenta del testo.

Accanto, **senza soglia**, si riporta la telepatia contro l'agente solo: è il confronto che isola l'effetto del canale.

## 9. Perché ci si può fidare

- **Pre-registrazione:** tutte le regole qui sopra sono state scritte e committate **prima** di far girare il test, con data e commit. Ogni cambiamento è scritto fra le deviazioni, con il motivo.
- **Una volta sola:** il test gira una volta. Rifarlo è una deviazione da dichiarare.
- **Sviluppo e test separati:** il numero di passi della telepatia si è scelto su altri contratti (la taratura,), mai su quelli del test.
- **Risposte giuste ricontrollate:** prima del test sono state rigenerate da zero dalle fonti originali, ed erano identiche.
- **Controllo del contratto scambiato:** se il sistema non leggesse davvero il contratto, il punteggio non crollerebbe.
- **Controllo a mano alla cieca** sui contratti italiani della demo: una persona del team giudica i verdetti senza sapere da quale sistema vengono.

## 10. Cosa questa misura non dice

- Dice se un sistema **trova i tipi di clausola giusti**, non se un contratto è buono o cattivo per il cliente.
- I contratti sono sotto i 24.000 token: sui documenti molto lunghi non dice niente.
- Venti contratti bastano a vedere differenze grandi; per differenze di 2-3 punti serve la replica su 50 contratti nuovi.
- Non misura il valore che non è F1: note per ruolo, dissensi visibili, catena firmata dei messaggi.

## In 30 secondi

> "Prendiamo contratti reali in cui avvocati hanno già segnato le clausole. Per ogni contratto il sistema dice quali di 19 tipi di clausola contiene, con una citazione come prova. Confrontiamo le sue risposte con quelle degli avvocati e calcoliamo l'F1: quante clausole trova senza inventarne. Confrontiamo quattro modi di organizzare lo stesso modello, con le regole scritte prima di misurare e un intervallo di confidenza su ogni differenza."
