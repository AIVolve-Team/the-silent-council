# sportello — lo Sportello telepatico con macchina della verità

Codice dell': agenti che esaminano le fatture arrivate per email passandosi la memoria (telepatia), controllati da una macchina della verità (sigillo, coerenza, traduttore). Le decisioni stanno nella mappa.

| Cartella | Ticket | Cosa contiene |
|---|---|---|
| `dati/` | | fatture di prova con la loro verità, archivi, regole del catalogo A01-A13 |
| `controllore/` | | livello 2 della macchina della verità: coerenza, tre testimoni, esito della fattura |
| `pipeline/` | | la staffetta estrattore → verificatore → decisore, in telepatia e a testo, e il registro del caso |
| `harness/` | | le misure pre-registrate: G2, esame del 16/10, prove anti-trucco, lista di G4 |
| `attacchi/` | | i 50 attacchi sulla pipeline, contati per famiglia, con le soglie |
| `pagina/` | | la pagina del caso e l'indice con le proposte da approvare, in italiano e in inglese |

Il motore telepatico condiviso con il Consiglio sta in `../motore`, la casa per i giudici in `../casa`. Per provarlo in un comando: `prova.sh`, con la guida `PROVA.md`.
