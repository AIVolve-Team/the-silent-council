# sportello — lo Sportello telepatico con macchina della verità

Codice dell': agenti che esaminano le fatture arrivate per email passandosi la memoria (telepatia), controllati da una macchina della verità (sigillo, coerenza, traduttore). Le decisioni stanno nella mappa.

| Cartella | Ticket | Cosa contiene |
|---|---|---|
| `dati/` | | fatture di prova con la loro verità, archivi, regole del catalogo A01-A13 |
| `controllore/` | | livello 2 della macchina della verità: coerenza, tre testimoni, esito della fattura |
| `pipeline/` | | la staffetta estrattore → verificatore → decisore, in telepatia e a testo, e il registro del caso |
| `attacchi/` | | i 50 attacchi sulla pipeline, contati per famiglia, con le soglie |
| `pagina/` | | la pagina del caso e l'indice con le proposte da approvare, in italiano e in inglese |
| `servizio/` | | il server del motore: `esamina_fattura` e `registra_decisione` via MCP e HTTP |
| `traduttore/` | | la memoria che passa fra gli agenti, ricopiata, con il testo nascosto in rosso, e G3 |

Il motore telepatico condiviso con il Consiglio sta in `../motore`. Per provarlo in un comando: `prova.sh`, con la guida `PROVA.md`. Le altre cartelle arrivano con le misure e la casa per i giudici.
