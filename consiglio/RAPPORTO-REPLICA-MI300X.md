# Replica dell'eval del Consiglio su CUAD: rapporto

Giro del 14/10/2026 su AMD MI300X, dalle 17:04 alle 21:30 (ora italiana). Qwen3-14B in bf16, telepatia con 0 passi latenti, codice `d6cbb0c` su `main`, pre-registrazione della replica `1bcb50c`. Issue, test di partenza.

> **In breve.** La replica sui 72 contratti CUAD di test mai usati **conferma G4**: le tre condizioni passano anche qui. Sulla replica la telepatia batte il testo di **+7,1 punti di F1** (intervallo al 95% da +2,9 a +11,6). Sul totale di 92 contratti lo batte di **+5,8** (da +2,1 a +9,6), con il **75% di token generati in meno** e un tempo di **55 s contro 146 s** per contratto. Contro l'agente solo la telepatia è **alla pari**: −1,2 punti sul totale, da −5,1 a +2,8.

## Sintesi

| | Test (20) | Replica (72) | Totale (92) |
|---|---|---|---|
| F1 telepatia | 72,5 | 70,3 | 70,8 |
| F1 testo | 70,7 | 63,2 | 65,0 |
| F1 agente solo | 75,9 | 70,7 | 72,0 |
| Telepatia − testo (IC 95%) | +1,7 (−6,9 / +9,6) | **+7,1 (+2,9 / +11,6)** | **+5,8 (+2,1 / +9,6)** |
| Telepatia − agente solo (IC 95%) | −3,4 (−12,0 / +3,2) | −0,5 (−4,9 / +4,3) | −1,2 (−5,1 / +2,8) |
| Token generati, telepatia contro testo | −75% | −75% | −75% |
| Secondi per contratto, telepatia / testo | 54 / 144 | 56 / 146 | 55 / 146 |

Come da pre-registrazione:
- **G4 resta deciso sul test da 20**, dove è superato.
- La replica lo **conferma**, perché le tre condizioni, calcolate sulla sola replica, danno lo stesso esito.
- Su replica e totale non si dà il giudizio «non perde, dimostrato».

## Note sul giro

- **Una sola esecuzione**, senza deviazioni né modifiche locali al codice.
- **Codice del modello invariato dal test.** `consiglio.py`, `istruzioni.py`, `esegui.py`, `configurazioni.py`, `taglio.py`, `schemi.py`, `misure.py`, `punteggio.py` e `motore/` sono identici a `d3c1ec1`. Da allora sono cambiati solo il caricamento dei file della replica e la generazione del rapporto.
- **Dati verificati prima del giro.** `prepara.py` è stato rifatto da zero il 14/10 con download nuovi dalle fonti ufficiali: i 6 file di `set-di-misura/` sono identici al byte a quelli committati, e gli hash coincidono con la pre-registrazione.
- **Macchina diversa da quella del test,** che era già stata distrutta. Immagine host ROCm 7.2.4 invece di 7.2. Container identico (`vllm/vllm-openai-rocm:v0.30.0`, torch 2.12, transformers 4.57.6, HIP 7.2). Prima del giro sono stati fatti due controlli:
  - fp32 contro bf16 di G1: risposte uguali su 5 problemi su 5;
  - prova veloce sul set dimostrativo: telepatia F1 98,2, identico al test.
- **Verdetti non validi: 5 su 216,** mentre nel test erano 0. Agente solo 1, testo 2, telepatia 2. In tutti e cinque i casi Qwen ha inserito un carattere cinese a metà del JSON, che quindi non si legge. Per la regola pre-registrata contano come «no» su tutte le coppie, in ogni configurazione.
- **I 72 contratti sono più difficili dei 20 del test:** tutte le configurazioni scendono di F1. Il testo scende di più (−7,5), la telepatia di meno (−2,2). Vanno citate le differenze, non gli F1 assoluti.
- **Voto fra 4 e contratto scambiato** non si ripetono, come da pre-registrazione: il test li ha già misurati.

Risultati grezzi (`.jsonl`, `numeri.json`, grafici, `giro.log`) in `~/hackathon/risultati-mi300x/replica/` sul Mac di chi ha lanciato il giro.

---

# Rapporto generato dallo script

Copiato senza modifiche da `rapporto.md`, generato da `numeri.json`; tolte solo le righe dei grafici.


## cuad, replica (72 contratti)

Modello Qwen/Qwen3-14B (bfloat16, cuda), passi latenti 0, riallineamento spento, codice `d6cbb0c`, pre-registrazione `1bcb50c` del 2026-10-13.

| Configurazione | F1 | P | R | MCC | Sempre sì | F1 severa | Mancate | Falsi allarmi | Verdetti validi | Token generati | Token letti | Secondi |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Agente solo | **70,7** | 75,7 | 66,4 | 0,65 | 30,3 | 61,7 | 82 | 52 | 71/72 | 456 | 7.783 | 22 |
| Consiglio a testo | **63,2** | 64,1 | 62,3 | 0,55 | 30,3 | 47,7 | 92 | 85 | 70/72 | 4.354 | 30.201 | 146 |
| Consiglio in telepatia | **70,3** | 74,7 | 66,4 | 0,64 | 30,3 | 59,6 | 82 | 55 | 70/72 | 1.092 | 10.803 | 56 |

### Telepatia contro testo

- **F1 della telepatia meno F1 del testo:** +7,1 punti (intervallo al 95% con bootstrap appaiato sui 72 contratti: da 2,9 a 11,6). G4 resta deciso sul test.
- **Token generati:** 75% in meno. **Tempo:** 56 s contro 146 s per contratto.
- **F1 della telepatia meno F1 dell'agente solo:** -0,5 punti (intervallo al 95%: da -4,9 a 4,3). È il confronto che isola il canale: in telepatia il relatore lavora sulla memoria della lettura di tutto il contratto, l'agente solo legge tutto il contratto.
- **Analisi a testo che toccano il tetto di 2048 token:** 0 su 216.

**G4 sulla replica** (non decide, conferma o smentisce il test):

- [x] F1 telepatia ≥ F1 testo − 3 punti
- [x] token generati almeno il −50%
- [x] la telepatia non è più lenta del testo

### Senza soglia

- **Consiglio a testo:** dissensi gravi 4, con ragione l'esperto 1/4 (25%); dissensi lievi 4, con ragione il relatore 1/4 (25%). Accordo fra note e verdetto 1322/1330 (99%); F1 delle note prese come verdetto 64,2. Taratura del verdetto, giuste per confidenza: alta 1157/1322 (88%), media 3/5 (60%), bassa 1/3 (33%).
- **Consiglio in telepatia:** dissensi gravi 71, con ragione l'esperto 20/71 (28%); dissensi lievi 47, con ragione il relatore 24/47 (51%). Accordo fra note e verdetto 1208/1326 (91%); F1 delle note prese come verdetto 64,9. Taratura del verdetto, giuste per confidenza: alta 1122/1211 (93%), media 46/66 (70%), bassa 28/53 (53%).


## cuad, test (20 contratti)

Modello Qwen/Qwen3-14B (bfloat16, cuda), passi latenti 0, riallineamento spento, codice `d3c1ec1`, pre-registrazione `d3c1ec1` del 2026-10-13.

| Configurazione | F1 | P | R | MCC | Sempre sì | F1 severa | Mancate | Falsi allarmi | Verdetti validi | Token generati | Token letti | Secondi |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Agente solo | **75,9** | 77,5 | 74,3 | 0,70 | 32,6 | 69,6 | 19 | 16 | 20/20 | 509 | 7.481 | 23 |
| 4 agenti indipendenti e voto | **74,8** | 75,3 | 74,3 | 0,69 | 32,6 | 68,6 | 19 | 18 | 20/20 | 2.082 | 29.995 | 94 |
| Consiglio a testo | **70,7** | 71,2 | 70,3 | 0,64 | 32,6 | 57,1 | 22 | 21 | 20/20 | 4.517 | 29.924 | 144 |
| Consiglio in telepatia | **72,5** | 78,1 | 67,6 | 0,67 | 32,6 | 67,7 | 24 | 14 | 20/20 | 1.121 | 10.496 | 54 |
| Contratto scambiato | **34,8** | 37,5 | 32,4 | 0,20 | 32,6 | 6,8 | 50 | 40 | 20/20 | 1.121 | 10.496 | 53 |

### Telepatia contro testo

- **F1 della telepatia meno F1 del testo:** +1,7 punti (intervallo al 95% con bootstrap appaiato sui 20 contratti: da -6,9 a 9,6). Si dice: *risultati compatibili*.
- **Token generati:** 75% in meno. **Tempo:** 54 s contro 144 s per contratto.
- **F1 della telepatia meno F1 dell'agente solo:** -3,4 punti (intervallo al 95%: da -12,0 a 3,2). È il confronto che isola il canale: in telepatia il relatore lavora sulla memoria della lettura di tutto il contratto, l'agente solo legge tutto il contratto.
- **Analisi a testo che toccano il tetto di 2048 token:** 0 su 60.

**G4** (su CUAD):

- [x] F1 telepatia ≥ F1 testo − 3 punti
- [x] token generati almeno il −50%
- [x] la telepatia non è più lenta del testo

### Prove di sabotaggio

| Prova | Differenza di F1 con la telepatia |
|---|---|
| Contratto scambiato | -37,7 |

Con 0 passi latenti non ci sono pensieri: le prove sui pensieri non si fanno.
Frase per la giuria: *Gli agenti si passano la memoria di ciò che hanno letto.* E poi: *Gli agenti si passano la memoria di ciò che hanno letto invece di riscriverlo: stessa qualità, meno token.*

Il contratto scambiato deve crollare: se non crolla, c'è un errore nel codice.

### Senza soglia

- **Consiglio a testo:** dissensi gravi 0, con ragione l'esperto 0/0; dissensi lievi 2, con ragione il relatore 1/2 (50%). Accordo fra note e verdetto 378/380 (99%); F1 delle note prese come verdetto 70,3. Taratura del verdetto, giuste per confidenza: alta 336/378 (89%), media 0/0, bassa 1/2 (50%).
- **Consiglio in telepatia:** dissensi gravi 16, con ragione l'esperto 7/16 (44%); dissensi lievi 12, con ragione il relatore 6/12 (50%). Accordo fra note e verdetto 352/380 (93%); F1 delle note prese come verdetto 71,8. Taratura del verdetto, giuste per confidenza: alta 327/352 (93%), media 12/21 (57%), bassa 3/7 (43%).


## cuad, totale (92 contratti)

| Configurazione | F1 | P | R | MCC | Sempre sì | F1 severa | Mancate | Falsi allarmi | Verdetti validi | Token generati | Token letti | Secondi |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Agente solo | **72,0** | 76,1 | 68,2 | 0,66 | 30,8 | 63,6 | 101 | 68 | 91/92 | 468 | 7.718 | 22 |
| Consiglio a testo | **65,0** | 65,8 | 64,2 | 0,57 | 30,8 | 49,9 | 114 | 106 | 90/92 | 4.389 | 30.141 | 146 |
| Consiglio in telepatia | **70,8** | 75,4 | 66,7 | 0,65 | 30,8 | 61,5 | 106 | 69 | 90/92 | 1.098 | 10.737 | 55 |

### Telepatia contro testo

- **F1 della telepatia meno F1 del testo:** +5,8 punti (intervallo al 95% con bootstrap appaiato sui 92 contratti: da 2,1 a 9,6). G4 resta deciso sul test.
- **Token generati:** 75% in meno. **Tempo:** 55 s contro 146 s per contratto.
- **F1 della telepatia meno F1 dell'agente solo:** -1,2 punti (intervallo al 95%: da -5,1 a 2,8). È il confronto che isola il canale: in telepatia il relatore lavora sulla memoria della lettura di tutto il contratto, l'agente solo legge tutto il contratto.
- **Analisi a testo che toccano il tetto di 2048 token:** 0 su 276.

### Senza soglia

- **Consiglio a testo:** dissensi gravi 4, con ragione l'esperto 1/4 (25%); dissensi lievi 6, con ragione il relatore 2/6 (33%). Accordo fra note e verdetto 1700/1710 (99%); F1 delle note prese come verdetto 65,6. Taratura del verdetto, giuste per confidenza: alta 1493/1700 (88%), media 3/5 (60%), bassa 2/5 (40%).
- **Consiglio in telepatia:** dissensi gravi 87, con ragione l'esperto 27/87 (31%); dissensi lievi 59, con ragione il relatore 30/59 (51%). Accordo fra note e verdetto 1560/1706 (91%); F1 delle note prese come verdetto 66,5. Taratura del verdetto, giuste per confidenza: alta 1449/1563 (93%), media 58/87 (67%), bassa 31/60 (52%).

**G4 e replica:** G4 resta deciso sul test, dove è superato. La replica lo **conferma**.
