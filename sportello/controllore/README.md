# sportello/controllore — livello 2 della macchina della verità

Il livello 1 (sigillo, catena, registro dell'incidente, verifica) sta già nel motore (`../../motore`,).

| File | Cosa fa |
|---|---|
| `controllore/coerenza.py` | gli 8 dati critici e il confronto campo per campo fra impegno e lettura |
| `controllore/valuta.py` | l'esito della fattura: coerenza, tre testimoni, regole del catalogo, decisore; l'interruttore del livello 2 |
| `controllore/motore.py` | `ControlloCoerenza`, il controllo da aggiungere a `Motore(controlli=…)` |
| `tests/` | i test, senza modello |

## Uso

```bash
cd sportello/controllore
uv venv -p 3.12.venv && uv pip install -p.venv/bin/python -r requirements.txt -e.
.venv/bin/python -m pytest -q
.venv/bin/ruff check. &&.venv/bin/ruff format --check.
```

Finché del motore non è in `main`, il motore si installa dal suo ramo: `uv pip install -e <cartella del ramo feat/motore-telepatico>/motore`.

```python
from controllore.motore import ControlloCoerenza
from controllore.valuta import valuta

motore = Motore(modello, controlli=[ControlloSigillo(pubbliche), ControlloCoerenza])
# … la staffetta dello Sportello …
v = valuta(impegno, lettura, proposta, applica_regole(impegno, archivi, abbinamenti))
v.esito, v.motivi, v.discordanze, v.pagamento_proposto
```

## Come funziona

- **Tre testimoni**: l'impegno dell'estrattore, la lettura del verificatore (dalla memoria, senza la fattura) e la proposta di pagamento del decisore.
- **Gli 8 dati critici:** identificativo fiscale del fornitore, numero e data del documento, totale, IBAN, importo e scadenza del pagamento, numero d'ordine. li chiama "7 campi critici", ma l'elenco ne ha 8.
- **Confronto** dopo la normalizzazione di `fatture.normalizza`: uguaglianza esatta su identificativi, IBAN, numeri (come in A01) e date; ±0,01 € sugli importi.
- **Dove:** nel motore ogni agente dichiara in chiaro nel campo `impegno` della sua etichetta, coperto dal sigillo. Per il verificatore quel campo contiene la lettura. `ControlloCoerenza` li confronta quando il messaggio del verificatore sta per arrivare al decisore: se non coincidono la staffetta si ferma e il decisore non riceve mai la memoria che ha mentito.
- **Esito** (`valuta`), vince il più grave:
  - impegno ≠ lettura → **bloccare** (livello "coerenza");
  - un dato critico vuoto → **persona** (livello "coerenza"; la staffetta va avanti);
  - proposta ≠ impegno o lettura su IBAN e importo → **bloccare** (livello "tre testimoni");
  - le regole del catalogo con il loro esito (livello "regole"); una riga che il modello non ha giudicato (A11 "da giudicare") → persona;
  - il decisore può solo chiedere una persona: non paga ciò che i controlli fermano e non blocca da solo (un blocco nasce sempre da una regola,).
- **I motivi** sono in italiano e in inglese, con l'IBAN sempre abbreviato (`IT99…`), mai intero da copiare.
- **Interruttore del livello 2:** `valuta(…, livello2=False)` e `ControlloCoerenza(attivo=False)` spengono coerenza e tre testimoni. Esiste solo in modalità demo: con l'estrattore che mente il pagamento proposto va all'IBAN dell'attaccante, e A03 non se ne accorge perché la dichiarazione è pulita. Nelle misure è sempre acceso.
