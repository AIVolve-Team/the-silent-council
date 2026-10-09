# Pre-registrazione dell'eval del Consiglio

Stato: bozza

Finché c'è la riga qui sopra, `revisione.esame` non fa girare il set di test.
Per congelare le regole: si compilano i punti segnati **da fissare**, si cambia la riga in `Stato: congelata il GG/MM/AAAA` e si fa il commit **prima** del giro di test.
Dopo, il test gira una volta sola, e ogni cambiamento si scrive fra le [deviazioni](#deviazioni) con il motivo.

Le regole vengono da Eval pre-registrato del Consiglio, da Metriche e soglie G1-G4 e dalle note.
Le **definizioni operative** sono nuove, scritte con il codice: vanno riviste dal team prima del congelamento.

## Dati

| File | SHA-256 |
|---|---|
| `consiglio/dati/set-di-misura/campione.json` | `3edaa8a7ae97019716d1c9b8ad3205c2836bb7b4b5b737327908e162b81751aa` |
| `consiglio/dati/set-di-misura/risposte-giuste.jsonl` | `c2b783c2a3c452683823b7c0d9113484c7193a451b7c4f025223a91824ee6675` |
| `consiglio/dati/set-dimostrativo.sha256` (impronte del set dimostrativo,) | `608bd5e51dc260a92aaafc151c041d80208de3204990702e58bf9dd910f280c6` |

- **Set di test:** 20 contratti CUAD, 20 ContractNLI e 20 CLAUDETTE, quelli di `campione.json` (seme fisso, sotto i 24.000 token).
- **Set dimostrativo:** i 4 contratti italiani, fuori dal repo fino alla consegna. Alla consegna si pubblicano e devono corrispondere alle impronte.
- **Etichette:** coppia (contratto, categoria) → da segnalare sì/no,.
  CUAD ha 19 categorie, ContractNLI 17 ipotesi e CLAUDETTE 9 categorie.

## Modello e decodifica

- **Qwen3-14B**, revisione `40c069824f4251a91eefaf281ebe4c544efd3e18`, in bf16, su una MI300X, batch 1.
- **Decodifica greedy** in tutte le configurazioni, cioè temperatura 0: un solo giro per configurazione.
- **Passi latenti:** **da fissare**, con la regola sul set di sviluppo: si provano 0, 10, 20 e 40, vince l'F1 più alto e, sotto 1 punto di differenza, il valore con meno passi.
- **Riallineamento W_a** dei passi latenti: **da fissare** (acceso o spento), dopo la diagnosi.

## Configurazioni

Tutte con lo stesso modello e lo stesso schema delle 19 righe (`revisione/schemi.py`).

1. **Agente solo:** legge tutto il contratto e scrive il verdetto senza obiezioni.
2. **4 agenti indipendenti e voto:** legale, finanza, rischio e avvocato del diavolo leggono ognuno tutto il contratto, dal proprio punto di vista, e scrivono un verdetto senza obiezioni (`istruzioni_indipendente`).
   - Per ogni categoria vince la maggioranza dei verdetti validi.
   - Sul 2-2 vince il gruppo con la confidenza media più alta, cioè la probabilità media della posizione scelta. A confidenza pari vince "sì".
   - La raccomandazione è la più frequente; sul pari, la più prudente (non firmare, poi negoziare, poi firmare).
   - Token e tempi sono la somma dei 4.
3. **Consiglio a testo.**
4. **Consiglio in telepatia.**

Su ContractNLI e CLAUDETTE il Consiglio è a tre, cioè legale, rischio e relatore, anche a testo. Il voto resta fra 4.
JEV non si fa girare: si cita il 77,38% pubblicato su ContractNLI.

## Voto

- **F1 sulle coppie (contratto, categoria)**, un numero per benchmark, mai sommati. CUAD è il numero principale; il riferimento è ContractEval, con Qwen3-14B da solo a 47,3.
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
  - ContractNLI e CLAUDETTE si riportano senza soglia.
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

Le prove di sabotaggio non bloccano la consegna: decidono la frase.

## Misure senza soglia

- **Chi aveva ragione nei dissensi** fra la nota dell'esperto e il verdetto:
  - nel dissenso grave (esperto "sì", verdetto "no"), quante volte aveva ragione l'esperto;
  - nel lieve (esperto "no", verdetto "sì"), quante volte aveva ragione il relatore.
- **Taratura della confidenza del verdetto:** quota di decisioni giuste per livello alto, medio e basso, con le soglie fissate (**da fissare**; oggi 0,9 e 0,7).
- **Accordo fra note e verdetto**, e F1 delle note prese come verdetto.
- **Importi e date nel verdetto**, solo sul set dimostrativo: quanti sono, e quanti non compaiono nel contratto. Un importo che non è nel contratto si segnala sempre, anche se capita una volta sola.
- **Grafico qualità contro costo:** F1 contro token generati per contratto, per le 4 configurazioni.

## Controllo a mano (set dimostrativo)

- Lo fa una persona del team **che non ha scritto né rivisto le risposte attese**, alla cieca: non sa quale verdetto viene dal testo e quale dalla telepatia.
- Giudica: raccomandazione giusta sì/no, dissenso atteso trovato sì/no, importi giusti.
- **Procedura** (proposta, da rivedere): chi organizza lancia `python -m revisione.cieca prepara <cartella dell'eval>`.
  - Ne escono un foglio per verdetto, con nomi neutri (`verdetto-01` …) e ordine mescolato con seme 31. Ogni foglio ha raccomandazione, clausole segnalate con citazione, obiezioni e dissensi, senza modalità, token, tempi o pensieri.
  - Ne esce anche una scheda da compilare.
  - Chi controlla riceve fogli, scheda e contratti, ma non i `.json` delle risposte attese.
  - La chiave (`chiave.json`) resta a chi organizza, che alla fine conta con `python -m revisione.cieca conta`.

## Come si fa girare

```bash
cd consiglio/revisione
.venv/bin/python -m revisione.esame esegui --benchmark cuad --insieme test --passi <passi fissati> --uscita esame-test
.venv/bin/python -m revisione.esame esegui --benchmark contractnli --insieme test --passi <passi fissati> --uscita esame-test
.venv/bin/python -m revisione.esame esegui --benchmark claudette --insieme test --passi <passi fissati> --uscita esame-test
.venv/bin/python -m revisione.esame esegui --benchmark dimostrativo --passi <passi fissati> --uscita esame-test
.venv/bin/python -m revisione.esame rapporto esame-test
```

Sul test il comando controlla che questo file sia congelato e committato, e che il codice di `consiglio/` e `motore/` non abbia modifiche locali. In `esame-<benchmark>-test.json` scrive il commit del codice e quello di questo file.

## Deviazioni

Nessuna.
