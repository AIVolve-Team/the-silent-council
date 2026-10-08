# sportello/pagina — la pagina del caso e le proposte da approvare

Come la pagina del verdetto del Consiglio: HTML statico con i dati incorporati, stessi caratteri e colori, tema chiaro e scuro.

| File | Cosa fa |
|---|---|
| `pagina/vista.py` | i dati della pagina dal risultato della pipeline e dagli archivi: qui l'IBAN si abbrevia sempre |
| `pagina/nascosto.py` | le righe di testo nascosto del PDF, solo per mostrarle |
| `pagina/caso.html` | il modello della pagina del caso |
| `pagina/elenco.html` | l'indice: proposte in attesa di approvazione e tutti i casi |
| `pagina/pagina.py` | genera pagine, PDF accanto e indice da un giro della pipeline |
| `tests/` | i test |

## Uso

```bash
cd sportello/pagina
python -m pagina.pagina <giro>/telepatia.jsonl../dati/insiemi/sviluppo --uscita pagine/ --registrato "15/10/2026 · MI300X" \
    --registri <giro>/registro/telepatia
open pagine/index.html
```

`--api <indirizzo>` fa partire le scelte della persona anche verso Evolus, attraverso la funzione Vercel del secondo workflow.
`--registri` mette accanto a ogni pagina il **registro del caso in un file solo**, `registro-<id>.zip`: scompattato, `python -m motore.verifica registro-<id> --pubbliche registro-<id>/chiavi-pubbliche` lo controlla, ed è sempre lo stesso file per lo stesso registro.
Accanto all'indice c'è `dal-vivo.html`: la pagina dei casi nati dalle prove dal vivo della casa per i giudici, che prende i dati dal browser del giudice.

## La pagina del caso 

1. **Esito e motivo in una frase**: il motivo è quello del controllo che ha deciso, per esempio *"L'estrattore dichiara IBAN IT38…9938, nella memoria c'è IT99…2854"*.
2. **Cosa non torna**: i motivi della macchina della verità (sigillo, coerenza, tre testimoni, decisore), la **tabella dei tre testimoni** sugli 8 dati critici con le differenze evidenziate, le regole del catalogo scattate.
3. **La fattura accanto all'ordine**, il PDF originale e il pulsante **"mostra testo nascosto"**.
4. **"Mostra cosa ha pensato ogni agente"**: apre la trascrizione della memoria del traduttore, con il testo nascosto in rosso e i pensieri grezzi; `?vista=memoria` la apre subito. Se il caso non ha la trascrizione, porta alla tabella dei tre testimoni, cioè alla vista delle differenze.
5. **Sospetta frode**: *"non rispondere all'email"* e i contatti del fornitore **dall'anagrafica**, mai quelli della fattura.
6. **La decisione**: approvare (sempre all'IBAN in anagrafica; su un caso bloccato con la nota obbligatoria di verifica), rifiutare (con il motivo), segnalare una frode (l'IBAN sospetto, abbreviato, va nell'elenco da tenere d'occhio).
7. **Il registro del caso** e il comando per verificarlo.

- **L'IBAN non compare mai intero** nel testo della pagina, nemmeno nel testo nascosto mostrato: solo prime e ultime quattro cifre. L'unico posto dove compare intero è il PDF originale, che è la prova di ciò che è arrivato.
- **Italiano e inglese** con un interruttore; l'inglese è acceso se non si sceglie (`?lang=it` per l'italiano).
- **Le scelte restano nel browser** (`localStorage`): ogni giudice ha la sua copia, senza login.
- **Il testo nascosto si riconosce dal corpo del carattere** (sotto i 3 punti) solo per mostrarlo: lo Sportello non decide mai da qui. Bloccare ogni fattura con testo minuscolo fermerebbe gli attacchi con un controllo fra file, e la macchina della verità non servirebbe (stesso ragionamento sull'XML).
- **I dati incorporati sono sicuri**: `<`, `>` e `&` diventano sequenze `<`, `>`, `&`, quindi nessun testo della fattura può chiudere il blocco dei dati.
- **Il PDF sta accanto alla pagina** (`<caso>.pdf`): Chrome spesso non apre un PDF incorporato come `data:`.

## L'indice (Q4)

In cima le **proposte in attesa di approvazione**, con ✓ per i tre testimoni e per il sigillo, da approvare una alla volta o tutte insieme (nella demo lo stato diventa "approvato": nessuna banca vera); sotto, tutti i casi con l'esito.

