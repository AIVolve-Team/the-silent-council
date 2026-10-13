# Pre-registrazione dell'eval del Consiglio

Stato: congelata il 13/10/2026

Finché c'è la riga qui sopra, `revisione.esame` non fa girare il set di test.
Per congelare le regole: si compilano i punti segnati **da fissare**, si cambia la riga in `Stato: congelata il GG/MM/AAAA` e si fa il commit **prima** del giro di test.
Dopo, il test gira una volta sola, e ogni cambiamento si scrive fra le [deviazioni](#deviazioni) con il motivo.

Le regole vengono da Eval pre-registrato del Consiglio, da Metriche e soglie G1-G4 e dalle note.
Le **definizioni operative** sono nuove, scritte con il codice: andavano riviste dal team prima del congelamento. Non è stato fatto: vedi le [deviazioni](#deviazioni).

## Dati

| File | SHA-256 |
|---|---|
| `consiglio/dati/set-di-misura/campione.json` | `3edaa8a7ae97019716d1c9b8ad3205c2836bb7b4b5b737327908e162b81751aa` |
| `consiglio/dati/set-di-misura/risposte-giuste.jsonl` | `c2b783c2a3c452683823b7c0d9113484c7193a451b7c4f025223a91824ee6675` |
| `consiglio/dati/set-dimostrativo.sha256` (impronte del set dimostrativo,) | `608bd5e51dc260a92aaafc151c041d80208de3204990702e58bf9dd910f280c6` |

- **Set di test:** 20 contratti CUAD, 20 ContractNLI e 20 CLAUDETTE, quelli di `campione.json` (seme fisso, sotto i 24.000 token).
- **Set dimostrativo:** i 4 contratti italiani, fuori dal repo fino alla consegna. Alla consegna si pubblicano e devono corrispondere alle impronte.
- **Taglio per ruolo:** il contratto si divide fra gli esperti per titoli (`revisione/taglio.py`), senza buchi: ogni pezzo annotato del test sta intero in una sezione. Su CUAD di test però 34 delle 74 coppie da segnalare (46%) stanno nella sezione di un esperto che non ha quella categoria, quasi sempre il legale, che fa da ruolo di riserva. A testo l'esperto scrive solo delle sue categorie, quindi quelle clausole rischiano di perdersi; in telepatia il relatore lavora anche sulla memoria della loro lettura (vedi Configurazioni).
- **Etichette:** coppia (contratto, categoria) → da segnalare sì/no,.
  CUAD ha 19 categorie, ContractNLI 17 ipotesi e CLAUDETTE 9 categorie.

## Modello e decodifica

- **Qwen3-14B**, revisione `40c069824f4251a91eefaf281ebe4c544efd3e18`, in bf16, su una MI300X, batch 1.
- **Ambiente:** il container del motore di G1 (`vllm/vllm-openai-rocm:v0.30.0`, con il torch ROCm dell'immagine), dopo il confronto fp32 contro bf16 di G1 (`g1/README.md`, passo 4): su ROCm le maschere dell'attenzione hanno avuto bug. La guida è `consiglio/MI300X.md`.
- **Decodifica greedy** in tutte le configurazioni, cioè temperatura 0: un solo giro per configurazione.
- **Passi latenti: 0**, fissati con la taratura sulla MI300X del 12/10/2026 (`mi300x.sh taratura`, sezione [Taratura sulla MI300X](#taratura-sulla-mi300x)), sul set di sviluppo di CUAD: si provano 0, 10, 20 e 40, vince l'F1 più alto e, sotto 1 punto di differenza, il valore con meno passi. Ha vinto 0 con F1 71,4, contro 65,1 con 10 passi.
  - 10, 20 e 40 sono i valori. Lo 0 è la sua *verifica anticipata* dei pensieri: se vince, sul set di sviluppo i pensieri non aiutano, e permette di correggere il sistema prima del congelamento.
  - Sul Mac (M1 Max, 12/10/2026, senza riallineamento) CUAD di sviluppo dava F1 68,8 con 0 passi e 56,2 con 10; il testo 51,6.
- **Riallineamento W_a** dei passi latenti: **spento**, con la diagnosi (12/10/2026, Qwen3-14B su M1 Max). Acceso, la telepatia faceva 28,6 sul set dimostrativo e 19,0 su CUAD di sviluppo; spento, 98,2 e 68,8, contro 78,3 e 51,6 del testo. Su Qwen3-14B, che ha gli embedding d'ingresso e d'uscita separati, il riallineamento rompe la memoria passata al relatore.

## Configurazioni

Tutte con lo stesso modello e lo stesso schema delle 19 righe (`revisione/schemi.py`).

1. **Agente solo:** legge tutto il contratto e scrive il verdetto senza obiezioni.
2. **4 agenti indipendenti e voto:** legale, finanza, rischio e avvocato del diavolo leggono ognuno tutto il contratto, dal proprio punto di vista, e scrivono un verdetto senza obiezioni (`istruzioni_indipendente`).
   - Per ogni categoria vince la maggioranza dei verdetti validi.
   - Sul 2-2 vince il gruppo con la confidenza media più alta, cioè la probabilità media della posizione scelta. A confidenza pari vince "sì".
   - La raccomandazione è la più frequente; sul pari, la più prudente (non firmare, poi negoziare, poi firmare).
   - Token e tempi sono la somma dei 4.
3. **Consiglio a testo.** Ogni esperto scrive un'analisi della sua sezione, al massimo **2.048 token** (`MAX_TOKEN_ANALISI`), e il relatore legge le analisi. Con i 512 token di default del motore la taratura le troncava tutte (9 su 9); con 2.048 la più lunga dello sviluppo arriva a 1.414. Il rapporto conta le analisi che toccano il tetto.
4. **Consiglio in telepatia.** Il relatore lavora sulla memoria della lettura di tutte le sezioni, cioè di tutto il contratto, invece che su analisi scritte. È il meccanismo, e il rapporto lo descrive così. Il prompt del relatore dice "Non hai letto il contratto" in tutte e due le modalità: in telepatia non è vero alla lettera, ma resta com'era nella taratura.

Su ContractNLI e CLAUDETTE il Consiglio è a tre, cioè legale, rischio e relatore, anche a testo. Il voto resta fra 4.
JEV non si fa girare: il 77,38% pubblicato su ContractNLI usa un'altra metrica, quindi è solo contesto, non un confronto.

## Voto

- **F1 sulle coppie (contratto, categoria)**, un numero per benchmark, mai sommati. CUAD è il numero principale. ContractEval (Qwen3-14B da solo a 47,3) ha compito, categorie e campione diversi: è contesto, non un riferimento alla pari. Il riferimento alla pari è la nostra configurazione 1, l'agente solo.
- Accanto a ogni F1: **clausole mancate** e **falsi allarmi**, **MCC** e la base **"sempre sì"**. Per CLAUDETTE anche la vista sul **solo grado 3**.
- Un verdetto non valido o mancante conta come "no" su tutte le sue coppie, e si conta a parte.
- **Versione severa.** Un "sì" giusto conta solo se una citazione del verdetto per quella categoria **si sovrappone** a un pezzo annotato; altrimenti vale come clausola mancata. I falsi allarmi restano falsi allarmi.
  - *Si sovrappone* vuol dire avere in comune almeno **5 parole di fila** con il pezzo annotato, oppure la citazione intera se è più corta. Il confronto si fa dopo la normalizzazione di `citazioni.normalizza`: niente maiuscole, spazi doppi, virgolette e apostrofi tipografici.
  - Le citazioni di meno di 3 parole non contano.
  - Nel set dimostrativo i pezzi annotati sono le citazioni delle risposte attese.

## Criterio di successo e G4

- **Qualità.** Si calcola F1 della telepatia meno F1 del testo su CUAD, con un **intervallo al 95% con bootstrap appaiato**:
  - si ricampionano i **contratti** con reinserimento, gli stessi per le due configurazioni, **10.000** volte, con seme **62**;
  - l'intervallo va dal 2,5° al 97,5° percentile;
  - se anche il limite inferiore sta entro i −3 punti si dice *"non perde, dimostrato"*, altrimenti *"risultati compatibili"*;
  - ContractNLI e CLAUDETTE si riportano senza soglia e senza giudizio.
- **Telepatia contro agente solo** su CUAD, con lo stesso bootstrap appaiato, **senza soglia** e fuori da G4. È il confronto che isola il canale: in telepatia il relatore lavora sulla memoria della lettura di tutto il contratto, l'agente solo legge tutto il contratto. Sullo sviluppo l'agente solo era davanti (vedi Taratura sulla MI300X).
- **Token.** Si contano tutti, letti e generati, separati e sommati, note per la persona comprese. Si confrontano le **medie per contratto**.
- **Tempo.** Secondi per contratto sulla MI300X, batch 1, media sui contratti.
- **G4: il Consiglio è consegnabile se**, su CUAD:
  - F1 telepatia ≥ F1 testo − 3 punti;
  - token generati almeno il −50%;
  - la telepatia non è più lenta del testo.

## Prove di sabotaggio

Tutte in telepatia, con i passi latenti scelti.

- **Pensieri azzerati:** passi latenti 0; restano le sezioni lette.
- **Pensieri di un altro contratto:** il contratto *i* riceve, per ogni esperto, i pensieri dello stesso esperto sul contratto *i+1* nell'ordine del campione (l'ultimo li riceve dal primo). Le sezioni lette restano giuste. Il motore ricalcola la memoria dei pensieri da quegli stati nascosti (`pensieri_da`).
- **Contratto scambiato:** il Consiglio legge il contratto *i+1* e si vota con le risposte del contratto *i*. È il controllo di base: deve crollare, altrimenti c'è un errore nel codice.
- **Cosa diciamo:**
  - *"Gli agenti si passano i pensieri"* si dice sempre;
  - *"I pensieri migliorano il risultato"* solo se i pensieri azzerati fanno calare l'F1 di **almeno 2 punti** e quelli di un altro contratto lo fanno calare;
  - altrimenti: *"Gli agenti si passano la memoria di ciò che hanno letto invece di riscriverlo: stessa qualità, meno token."*

**Con 0 passi latenti** non ci sono pensieri: le prove *pensieri azzerati* e *pensieri di un altro contratto* non si fanno (la prima sarebbe lo stesso giro della telepatia, la seconda non ha pensieri da scambiare) e vale la frase di riserva. Anche la frase che si dice sempre descrive il meccanismo per quello che è: *"Gli agenti si passano la memoria di ciò che hanno letto."* Il *contratto scambiato* resta.

Le prove di sabotaggio non bloccano la consegna: decidono la frase.

## Misure senza soglia

- **Chi aveva ragione nei dissensi** fra la nota dell'esperto e il verdetto:
  - nel dissenso grave (esperto "sì", verdetto "no"), quante volte aveva ragione l'esperto;
  - nel lieve (esperto "no", verdetto "sì"), quante volte aveva ragione il relatore.
- **Taratura della confidenza del verdetto:** quota di decisioni giuste per livello alto, medio e basso, con le soglie fissate: **alta da 0,9, media da 0,7**. La taratura su CUAD dice che nessuna soglia arriva a 9 decisioni giuste su 10 (sopra 0,99 sono giuste l'89%): le soglie restano queste, e il rapporto lo dice.
- **Accordo fra note e verdetto**, e F1 delle note prese come verdetto.
- **Importi e date nel verdetto**, solo sul set dimostrativo: quanti sono, e quanti non compaiono nel contratto. Un importo che non è nel contratto si segnala sempre, anche se capita una volta sola.
- **Per lunghezza (esplorativa):** F1 di agente solo, telepatia e testo sui contratti CUAD di test sopra e sotto la mediana di lunghezza, in token di Qwen3-14B. Si calcola dai `.jsonl` dopo il test e si riporta come indizio, senza soglia: i contratti sopra i 24.000 token sono esclusi dal campione, quindi sui testi davvero lunghi il test non dice niente.
- **CLAUDETTE** è sbilanciato: il 79% delle coppie è da segnalare e "sempre sì" fa F1 88,5. Lì contano MCC e la base "sempre sì".
- **Grafico qualità contro costo:** F1 contro token generati per contratto, per le 4 configurazioni.

## Controllo a mano (set dimostrativo)

- Lo fa una persona del team **che non ha scritto né rivisto le risposte attese**, alla cieca: non sa quale verdetto viene dal testo e quale dalla telepatia.
- Giudica: raccomandazione giusta sì/no, dissenso atteso trovato sì/no, importi giusti.
- **Procedura** (proposta, da rivedere): chi organizza lancia `python -m revisione.cieca prepara <cartella dell'eval>`.
  - Ne escono un foglio per verdetto, con nomi neutri (`verdetto-01` …) e ordine mescolato con seme 31. Ogni foglio ha raccomandazione, clausole segnalate con citazione, obiezioni e dissensi, senza modalità, token, tempi o pensieri.
  - Ne esce anche una scheda da compilare.
  - Chi controlla riceve fogli, scheda e contratti, ma non i `.json` delle risposte attese.
  - La chiave (`chiave.json`) resta a chi organizza, che alla fine conta con `python -m revisione.cieca conta`.

## Taratura sulla MI300X

12/10/2026, 1× MI300X (AMD Developer Cloud, ROCm 7.2), container `vllm/vllm-openai-rocm:v0.30.0` con torch `2.12.0+git6bbd260` e transformers 4.57.6, codice al commit `1ad3b02`, riallineamento spento. Spiegazione completa in [TARATURA-MI300X.md](TARATURA-MI300X.md) e.

| F1 | 0 passi | 10 passi | 20 passi | 40 passi | testo |
|---|---|---|---|---|---|
| CUAD, sviluppo (5 contratti) | **71,4** | 65,1 | 58,5 | 61,5 (1 verdetto non valido) | 52,6 |
| Set dimostrativo (4 contratti) | **98,2** | 98,2 | 98,2 | 98,2 | 76,6 |

- **Passi scelti: 0**, con la regola qui sopra. Valgono le regole per 0 passi delle [prove di sabotaggio](#prove-di-sabotaggio): niente prove sui pensieri, frase di riserva, il contratto scambiato resta.
- **Soglie di confidenza: 0,9 e 0,7**, come sopra.
- **Accordo coppia per coppia** dei sì/no del verdetto con i giri del Mac sullo stesso codice (12/10/2026): CUAD 98,7% con 0 passi, 96,1% con 10, 98,7% a testo (4 contratti in comune, 76 coppie ciascuno); set dimostrativo 100% con 0, 10 e 40 passi. Nessuna divergenza da cercare prima del test.

**Prova del 13/10/2026 sullo sviluppo di CUAD, dopo la revisione delle metriche**, con il tetto nuovo delle analisi a testo (stessa macchina, stesso modello):

| Configurazione | F1 | Token generati per contratto | Secondi per contratto |
|---|---|---|---|
| Agente solo | **76,2** | 586 | 31 |
| Consiglio in telepatia, 0 passi (12/10) | 71,4 | 1.217 | 70 |
| Consiglio a testo, analisi fino a 2.048 token | 58,5 | 4.767 | 169 |
| Consiglio a testo, analisi a 512 token (12/10) | 52,6 | 2.776 | 103 |

Nessuna analisi tocca il nuovo tetto (la più lunga 1.414 token). I passi scelti non cambiano: la regola guarda solo la telepatia.

## Replica su CUAD

Decisa il 13/10/2026 verso le 13:25, mentre il test girava ancora su ContractNLI e prima che esistesse il suo rapporto: si fa **qualunque sia il risultato del test**. Su CUAD si conoscevano già le F1 per configurazione (agente solo 75,9, voto fra 4 74,8, telepatia 72,5, testo 70,7), non gli intervalli. La prima versione prevedeva 50 contratti estratti a caso. La sera del 13/10/2026 si è passati a tutti i 72, per il tempo di GPU chiesto dal team (commento).

- **Perché:** con 20 contratti l'intervallo al 95% delle differenze di F1 è largo, e differenze di 2-3 punti non si distinguono dal caso. Con 92 contratti si stringe a circa 0,47 volte.
- **Contratti:** tutti i contratti di test di CUAD sotto i 24.000 token (tokenizer di Qwen3-14B, come il test), **esclusi i 20 del test**: sono 72, senza estrazione. 1.368 coppie, 244 da segnalare. I file sono a parte, così quelli del test restano quelli della tabella in [Dati](#dati):

  | File | SHA-256 |
  |---|---|
  | `consiglio/dati/set-di-misura/campione-replica.json` | `6efc690d4432877859bb534eca96d850c677bd62c0d4db1a8c8c5d46818bf6b1` |
  | `consiglio/dati/set-di-misura/risposte-giuste-replica.jsonl` | `61eeab9edcfe3e88bb7f184fbd095d1e02bd78e043747666467d075d8d5cb7d4` |

- **Configurazioni:** telepatia (0 passi), testo (analisi fino a 2.048 token) e agente solo. Voto fra 4 e prove di sabotaggio non si ripetono: il test li ha già misurati.
- **Stesso codice e stesse regole del test:** modello, revisione, decodifica, ambiente, W_a spento, metriche e bootstrap appaiato (10.000 ripetizioni, seme 62). **Gira una volta sola**: un secondo giro è una deviazione, come per il test.
- **Cosa si riporta:** test (20), replica (72) e totale (92), ognuno con F1, token e tempo, e con l'intervallo al 95% di telepatia contro testo e di telepatia contro agente solo. Il totale ricampiona insieme i contratti di test e replica.
- **G4 resta deciso sul test da 20.** Su replica e totale non si dà il giudizio *"non perde, dimostrato"*. La replica **conferma** G4 se le tre condizioni di G4, calcolate sulla sola replica, danno lo stesso esito del test (superato in tutti e due, o non superato in tutti e due); se no lo **smentisce**. Si usa la sola replica, non il totale, perché il totale contiene il test.
- **Come si fa girare:** `PASSI=0./consiglio/mi300x.sh replica`, dopo la fine del test. Lo script collega i giri di CUAD del test e scrive il rapporto con le tre sezioni.

## Come si fa girare

Nel container del motore di G1, dalla radice del repo (la guida è `consiglio/MI300X.md`):

```bash
PASSI=<passi fissati>./consiglio/mi300x.sh test
```

`mi300x.sh` fa girare i quattro benchmark con il riallineamento spento e scrive il rapporto. A mano sono questi comandi:

```bash
cd consiglio/revisione
.venv/bin/python -m revisione.esame esegui --benchmark cuad --insieme test --passi <passi fissati> --senza-riallineamento --uscita esame-test
.venv/bin/python -m revisione.esame esegui --benchmark contractnli --insieme test --passi <passi fissati> --senza-riallineamento --uscita esame-test
.venv/bin/python -m revisione.esame esegui --benchmark claudette --insieme test --passi <passi fissati> --senza-riallineamento --uscita esame-test
.venv/bin/python -m revisione.esame esegui --benchmark dimostrativo --passi <passi fissati> --senza-riallineamento --uscita esame-test
.venv/bin/python -m revisione.esame rapporto esame-test
```

Sul test il comando controlla che questo file sia congelato e committato, e che il codice di `consiglio/` e `motore/` non abbia modifiche locali. In `esame-<benchmark>-test.json` scrive il commit del codice e quello di questo file.

## Deviazioni

1. **Congelata senza la rilettura del team delle definizioni operative** (riga in cima). Il 12/10/2026 si è scelto di congelare e lanciare il test subito dopo la taratura, per avere i numeri prima del G4 del 16/10. La rilettura resta da fare dopo: se trova un errore, lo si scrive qui e il rapporto lo dice, senza rifare il test in silenzio.
2. **Il confronto fp32 contro bf16 di G1** (sezione Modello e decodifica) è girato con il riferimento fp32 sul backend math di SDPA invece dei soli kernel veloci, che in fp32 si fermavano con `No available kernel` (commit `903d2ee` su `feat/g1`, spiegato in g1/RISULTATI-MI300X.md). Risposte uguali 5 su 5. Il giro del Consiglio non cambia.
3. **Riaperta e ricongelata il 13/10/2026, prima del test.** Una revisione delle metriche, delle risposte giuste e dell'equità del confronto ha trovato che il testo partiva svantaggiato: analisi troncate a 512 token, tutte. Le risposte giuste sono state rigenerate dalle fonti e sono identiche; le formule sono corrette. Cambiamenti, nel codice e qui:
   - tetto delle analisi a testo da 512 a 2.048 token, con il conteggio delle troncate;
   - confronto telepatia contro agente solo nel rapporto, senza soglia;
   - "dimostrato" solo su CUAD, come già scritto in Criterio di successo;
   - analisi esplorativa per lunghezza;
   - le note su taglio per ruolo, prompt del relatore, riferimenti esterni e CLAUDETTE.

   Il test non era ancora girato: sono regole fissate prima di vedere i suoi risultati. Erano invece già noti i numeri di sviluppo dell'agente solo: hanno motivato il confronto in più, senza cambiare G4.
