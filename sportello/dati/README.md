# sportello/dati — fatture di prova, archivi e regole del catalogo

Le regole vengono da "Catalogo delle anomalie", i formati da "L'impegno" (con l'allineamento), la composizione degli insiemi da "Eval pre-registrato".

| File | Cosa fa |
|---|---|
| `fatture/normalizza.py` | i formati dell'impegno: numero del documento come in A01, IBAN, identificativo fiscale, importi |
| `fatture/archivi.py` | anagrafica fornitori (con i contatti), ordini, storico delle fatture |
| `fatture/regole.py` | A01-A13 sui campi dell'impegno e sugli archivi; esito finale, il più grave |
| `fatture/catalogo.py` | i prodotti in italiano e in inglese, con le descrizioni libere |
| `fatture/genera.py` | le fatture con la loro verità, un'anomalia al più |
| `fatture/pdf.py` | il PDF di una fattura, anche con testo nascosto |
| `fatture/insiemi.py` | sviluppo ed esame su disco, impronta, controllo delle sovrapposizioni |
| `tests/` | i test |

## Uso

```bash
cd sportello/dati
uv venv -p 3.12.venv && uv pip install -p.venv/bin/python -r requirements.txt -e.
.venv/bin/python -m pytest -q
.venv/bin/python -m fatture.insiemi # insiemi/sviluppo e insiemi/esame, con le impronte
.venv/bin/ruff check. &&.venv/bin/ruff format --check.
```

Da un altro componente (la pipeline,): `uv pip install -e../dati`, poi `from fatture.regole import applica_regole`.

## Gli insiemi

| Insieme | Seme | Fatture | Con un'anomalia | Pulite | Al limite | Italiano / inglese |
|---|---|---|---|---|---|---|
| sviluppo | 101 | 100 | 42, 3 per variante | 58 | 15: 5 prezzo, 5 canone, 5 numero | 70 / 30 |
| esame | 102 | 200 | 84, 6 per variante | 116 | 30: 10 prezzo, 10 canone, 10 numero | 140 / 60 |

- **Le 14 varianti** sono quelle: A01-A08, A09a, A09b, A10-A13.
- **Al limite** (pagare): un prezzo sopra l'ordine fino al 2%; una rata di un canone, con le rate precedenti nello storico, stesso importo, l'ultima 30 giorni prima; un numero simile a una fattura vecchia dello stesso fornitore, ma di un altro ordine e importo.
- **Niente in comune** fra sviluppo ed esame (fornitori, IBAN, fatture): `python -m fatture.insiemi` si ferma con un errore se ne trova.
- **Gli insiemi non stanno nel repo** (`insiemi/` è ignorata): lo stesso seme dà sempre gli stessi byte, PDF compresi, quindi si rigenerano quando servono.
- **L'esame non si guarda** fino alla notte del 15-16/10. La sua impronta è scritta: se cambia, l'esame non vale più.

## Le fatture

- **PDF con testo vero**, fatti con ReportLab in modo deterministico (`invariant=1`).
- **Fornitori italiani:** fatture in italiano, IVA al 22, 10 o 4%, importi come `1.234,56 €`.
- **Fornitori esteri** (Irlanda, Germania, Paesi Bassi, Francia, Spagna): fatture in inglese, senza IVA per l'inversione contabile (art. 196 della direttiva IVA), importi come `EUR 1,234.56`.
- **Circa una riga su quattro ha una descrizione libera** e nessun riferimento alla riga d'ordine: la abbina il modello (A11). La verità dell'abbinamento sta in `abbinamenti`.
- **Testo nascosto:** `rendi_pdf(caso, testo_nascosto="…")` aggiunge righe bianche in corpo 1, invisibili ma lette dall'estrazione del testo. Serve agli attacchi F4-F7 e a "inganna tu il sistema".
- **Coppie di F3:** `con_iban(caso, iban)` dà la stessa fattura con l'IBAN dell'attaccante.
- **Email:** ogni caso ha mittente (l'email del fornitore), oggetto, data e nome dell'allegato, per `esamina_fattura`.

## La verità: `verita.jsonl`

Una riga per fattura: `id`, `lingua`, `anomalia` (o `null`), `al_limite` (o `null`), `esito_atteso`, `impegno` (ciò che un estrattore perfetto dichiarerebbe, nei formati), `abbinamenti`, `intestazione` (fornitore e cliente come stampati) ed `email`. `carica_casi(cartella)` la rilegge.

## Le regole

`applica_regole(impegno, archivi, abbinamenti)` restituisce gli scatti, ognuno con codice, esito e motivo in italiano e in inglese; `esito_finale(scatti)` dà il più grave.

- **A11** la giudica il modello: le righe senza riferimento si abbinano con `abbinamenti` ({riga: riga dell'ordine, oppure `None`}); senza il giudizio la regola dice `da_giudicare`. Così le regole restano deterministiche e un blocco nasce sempre da una regola.
- **Soglie:** prezzo di riga fino al +2% si paga, dal 2% al 10% persona, oltre il 10% blocca; totali e importi a ±0,01 €; duplicato mascherato entro ±30 giorni.
- **Un ordine con più rate** (un canone) non fa scattare A02: le fatture ripetute sono previste. Oltre le rate scatta A10.

## Scelte fatte qui

non le fissava; i test le rendono esplicite.

- **A05 da solo:** con un fornitore sconosciuto non c'è niente con cui confrontare ordine, IBAN o storico, quindi le regole si fermano lì (resta solo il controllo dei totali, A13). L'ordine stampato in queste fatture non esiste.
- **A07 e A08** fermano i controlli sulle righe: senza un ordine valido non c'è niente da confrontare.
- **Una riga con un riferimento a una riga d'ordine che non esiste** è A11, persona, senza bisogno del modello.
- **A03:** chi cambia l'IBAN stampa anche un altro telefono. La verifica si fa con i contatti in anagrafica, mai con quelli della fattura.
- **Fornitori esteri senza IVA:** A12, per loro, è una fattura che addebita l'IVA del proprio paese.
