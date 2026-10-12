# consiglio/revisione — il Consiglio silenzioso

Il Consiglio gira sul motore telepatico di `motore/` e usa i dati di `consiglio/dati/`.
Le regole vengono da "Impostazione del Consiglio", "Verdetto e dissenso" e "Interfaccia del motore".

Per un contratto:

1. **taglio**: una sezione per esperto, con una regola sui titoli delle clausole; senza titoli, parti contigue;
2. **staffetta** sul motore: legale → finanza → rischio pensano in ordine, il relatore riceve la memoria di tutti e scrive il verdetto. Su ContractNLI e CLAUDETTE la finanza non è convocata;
3. **note**: ogni esperto scrive la sua da una copia della propria memoria, e la nota non entra nella catena;
4. **verdetto**: le righe di tutte le categorie, i dettagli con citazione e motivazione, la raccomandazione *firmare / negoziare / non firmare*. JSON con schema vincolato, prima le obiezioni;
5. **confidenza** dai logprob dei token `true` e `false`; **dissenso** grave o lieve fra nota e verdetto; **citazioni** cercate parola per parola nel contratto.

| File | Cosa fa |
|---|---|
| `revisione/taglio.py` | trova i titoli (numerati, in maiuscolo, su una riga da soli) e dà ogni clausola a un ruolo con parole chiave per famiglia di contratti |
| `revisione/categorie.py` | le categorie di ogni benchmark, con nome e descrizione in italiano per i prompt |
| `revisione/istruzioni.py` | i prompt di esperti e relatore, gli stessi in telepatia e a testo |
| `revisione/schemi.py` | gli schemi JSON di nota e verdetto, con voci e caratteri limitati |
| `revisione/consiglio.py` | `Consiglio.revisiona`: taglio, staffetta, note, verdetto, confidenza e dissenso |
| `revisione/confidenza.py` | p(sì) dai logprob osservati, livelli alta / media / bassa |
| `revisione/citazioni.py` | verifica delle citazioni nel testo del contratto |
| `revisione/punteggio.py` | F1, precisione, richiamo, MCC e base "sempre sì" sulle coppie (contratto, categoria), per il verdetto e per le note; accordo fra note e verdetto |
| `revisione/esegui.py` | fa girare il Consiglio su un insieme e scrive una revisione per riga in `risultati/` |
| `revisione/dati.py` | legge contratti, risposte giuste e set dimostrativo da `consiglio/dati` |
| `revisione/vista.py` | dalla revisione alla vista della pagina del verdetto, e la pagina con i dati dentro |
| `pagina/verdetto.html` | la pagina del verdetto per la persona |
| `revisione/vetrina.py` e `pagina/vetrina.html` | la parte del Consiglio nel sito per i giudici: indice dei contratti in inglese e italiano e pagine del verdetto, per `casa/costruisci.py --consiglio` |

## Uso

```bash
cd consiglio/revisione
uv venv -p 3.12.venv && uv pip install -p.venv -e../../motore -r../../motore/requirements.txt
.venv/bin/python -m pytest -q -m "not modello" # 22 test veloci
.venv/bin/python -m pytest -q # 24 test, circa 4 minuti su un Mac M4 (Qwen3-0.6B)

# I contratti del set di misura vengono da consiglio/dati/cache (prepara.py li scarica).
.venv/bin/python -m revisione.esegui --benchmark cuad --modalita telepatia --passi 10 --modello Qwen/Qwen3-1.7B
.venv/bin/python -m revisione.esegui --benchmark dimostrativo --modalita testo
.venv/bin/python -m revisione.esegui --benchmark cuad --passi 0 10 20 40 # taratura dei passi latenti 
.venv/bin/python -m revisione.esegui --benchmark dimostrativo --senza-riallineamento --passi 0 10 40 # diagnosi 
```

- Il set dimostrativo sta in `consiglio/dati/set-dimostrativo`, fuori dal repo; con `CONSIGLIO_SET_DIMOSTRATIVO` si indica un'altra cartella.
- `esegui` gira solo sul set di **sviluppo**. Il test si fa girare una volta sola, con l'eval pre-registrato.
- Le revisioni finiscono in `risultati/`, una per riga, con note, verdetto, confidenze, dissensi, citazioni verificate, token, tempo e impronte dei messaggi.
- `--senza-riallineamento` spegne la matrice W_a di LatentMAS sui passi latenti, come è di default in LatentMAS; il nome del file finisce con `-senza-riallineamento`. Il riepilogo di ogni giro dà anche l'F1 delle note prese come verdetto e l'accordo fra note e verdetto, per vedere se una segnalazione si perde negli esperti o nel relatore.
- Per le prove e per la demo, `Consiglio.revisiona(..., pensieri_da=..., attacchi=...)` passa le opzioni alla staffetta del motore.

## La pagina del verdetto 

`pagina/verdetto.html` mostra alla persona il verdetto di una revisione, con le regole:

- in cima la raccomandazione *firmare / negoziare / non firmare*, con la motivazione;
- le righe di tutte le categorie, divise per esperto: citazione con il bollino "trovata nel contratto" o "non trovata", motivazione e confidenza;
- il dissenso grave con l'esperto sicuro sempre in evidenza, gli altri dissensi si aprono con un clic. Su ogni dissenso la persona sceglie chi ha ragione;
- il sigillo: "comunicazione tra esperti integra" con le impronte dei messaggi, oppure l'avviso rosso senza verdetto;
- "Mostra cosa ha pensato ogni esperto" apre le note;
- "Scarica il riepilogo (PDF)" stampa raccomandazione, clausole segnalate, dissensi e scelte; "Salva le scelte" scarica un JSON.

```bash
.venv/bin/python -m revisione.vista risultati/<giro>.jsonl --contratto <id> --titolo "Contratto..." --uscita vista.json --html verdetto.html
```

Con `--html` la pagina contiene già i dati: è un file solo, da aprire o allegare. Senza, la pagina legge `?vista=vista.json` o un file scelto a mano.
`pagina/esempio.html` è la pagina di una revisione inventata (`pagina/esempio-revisione.json`): non contiene niente del set dimostrativo, che resta privato.
Per rigenerarla:

```bash
.venv/bin/python -c "import json; from pathlib import Path; from revisione import BENCHMARK; from revisione.vista import pagina, vista; r = json.loads(Path('pagina/esempio-revisione.json').read_text); Path('pagina/esempio.html').write_text(pagina(vista(r, BENCHMARK['dimostrativo'], 'Contratto di fornitura di componenti (esempio)')))"
```

Il collegamento con Evolus (email con il link alla pagina, scelte rimandate con il secondo workflow) aspetta l'integrazione dell'.

## Scelte

- **Taglio senza LLM.** I titoli si riconoscono con regole su numeri, maiuscole e righe corte:
  - si scartano gli indici (titolo seguito da un numero di pagina) e le righe ripetute (intestazioni e piè di pagina EDGAR);
  - i titoli senza numero contano solo se ce ne sono almeno tre nel corpo del testo, così indirizzi e firme di una lettera non bastano.

  Le parole chiave dei titoli stanno in `PAROLE_CHIAVE`, per tre famiglie: contratti commerciali (CUAD e set dimostrativo), NDA e ToS. Senza parola chiave la clausola va al legale.
- **Schemi limitati.** Al massimo 3 citazioni per nota e 8 dettagli nel verdetto, con un massimo di caratteri: nota e verdetto si chiudono sempre entro 300 e 1.100 token.
- **Confidenza.** Le soglie alta / media / bassa (0,9 e 0,7) sono provvisorie: si fissano sul set di sviluppo con Qwen3-14B.
- **Traduzione delle citazioni** solo con `traduci=True`: serve quando la persona legge un contratto non in italiano, non nell'eval.

## Cosa manca

- La prova con Qwen3-14B sulla MI300X, la scelta dei passi latenti e le soglie di confidenza: servono la GPU (G1).
- L'eval completo, con le configurazioni di confronto e le prove di sabotaggio, è.
