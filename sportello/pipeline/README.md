# sportello/pipeline — la staffetta delle fatture

Usa il motore (`../../motore`,), le fatture e le regole (`../dati`,) e la coerenza (`../controllore`,).

| File | Cosa fa |
|---|---|
| `pipeline/testo.py` | dal PDF al testo, testo nascosto compreso |
| `pipeline/schemi.py` | gli schemi di impegno, lettura e proposta, con i formati imposti dalla decodifica vincolata |
| `pipeline/agenti.py` | i tre agenti e i loro prompt |
| `pipeline/sportello.py` | `esamina`: la staffetta, i controlli, l'esito e il registro del caso |
| `pipeline/giro.py` | un giro su un insieme di fatture, con ripresa dopo un'interruzione |
| `pipeline/riepilogo.py` | il riepilogo della prova: esiti, pagamenti dannosi, blocchi ingiusti, lettura giusta |
| `tests/` | i test; quelli con il modello usano Qwen3-0.6B |

## Uso

```bash
cd sportello/pipeline
uv venv -p 3.12.venv && uv pip install -p.venv/bin/python -r requirements.txt -e.
.venv/bin/python -m pytest -q # i 5 test con il modello durano circa 3 minuti sul Mac
.venv/bin/python -m pipeline.giro../dati/insiemi/sviluppo --modello Qwen/Qwen3-0.6B --limite 3 --uscita /tmp/sportello
.venv/bin/python -m pipeline.riepilogo /tmp/sportello../dati/insiemi/sviluppo
```

Per i colleghi c'è `../prova.sh`, con la guida `../PROVA.md`.

## La staffetta

1. **Estrattore:** legge il testo del PDF e pensa; da una copia della sua memoria scrive l'**impegno**, che va nell'etichetta del suo messaggio e viene firmato. A testo scrive l'impegno rileggendo la fattura.
2. **Verificatore:** non vede la fattura; pensa sulla memoria ricevuta e scrive la **lettura** degli 8 dati critici, nel campo `impegno` della sua etichetta.
3. **Consegna al decisore:** qui la coerenza confronta impegno e lettura; se non coincidono la staffetta si ferma e il decisore non riceve mai la memoria che ha mentito.
4. **Decisore:** scrive la **proposta** (IBAN, importo, esito, motivazione). Non può bloccare: un blocco nasce sempre da una regola.
5. **Abbinatore cieco:** abbina all'ordine le righe senza riferimento (A11). Vede solo le righe già estratte e l'ordine, **mai la memoria del documento**, dove può esserci una nota nascosta come "la riga 5 è compresa nella riga 1 dell'ordine" (F7). Lavora solo se ci sono righe senza riferimento, e i suoi token si contano come quelli degli altri agenti, nei due modi. Le regole fisse controllano comunque codice, prezzo e somma delle quantità di ogni abbinamento.
5. **Esito:** catena verificata, regole del catalogo, tre testimoni; vince il più grave (`controllore.valuta`).

L'uscita è quella di `esamina_fattura`: id del caso, esito, motivi con il livello, proposta, discordanze, stato del sigillo, più impegno, lettura, token e secondi. Il **registro del caso** contiene i messaggi firmati, l'esito e le chiavi pubbliche; `python -m motore.verifica <registro> --pubbliche <registro>/chiavi-pubbliche` lo controlla da solo.

## Scelte fatte qui

- **Prompt in inglese**, come le istruzioni che Qwen3 segue meglio; i valori si copiano come sono stampati.
- **I formati stanno negli schemi:** date ISO, IBAN senza spazi, identificativi con il prefisso del paese, `num_item` solo numerico. Il modello non può scriverli in un altro modo, quindi una discordanza è una discordanza vera. Il primo giro con Qwen3-0.6B aveva scritto il codice del prodotto al posto del numero della riga d'ordine: da qui lo schema e la correzione delle regole.
- **Limiti di scrittura:** impegno 2.048 token, lettura 320, proposta 512; a testo ogni agente scrive al massimo 1.024 token. Se il JSON resta incompleto, l'esito è "persona".
- **Chiavi:** una coppia Ed25519 per ruolo. In prova le private stanno in `~/.sportello/chiavi-prova`, fuori dal repo e dai risultati; nel registro vanno solo le pubbliche.
- **Agganci per gli attacchi** (`Attacco`): F3 (memoria da un altro PDF, impegno da quello vero), F1-F2 (un messaggio toccato dopo la firma) e la lettura sostituita, per i test. Nella modalità normale non esistono.
