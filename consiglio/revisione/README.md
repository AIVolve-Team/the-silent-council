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
| `revisione/dati.py` | legge contratti, risposte giuste, pezzi annotati e set dimostrativo da `consiglio/dati` |
| `revisione/configurazioni.py` | le configurazioni di confronto dell'eval: agente solo e voto fra 4 agenti indipendenti |
| `revisione/misure.py` | le misure dell'eval: F1 severa, bootstrap appaiato, costi, G4, sabotaggi, dissensi, taratura, importi e date, grafico |
| `revisione/esame.py` | fa girare l'eval e ne scrive il rapporto; sul test parte solo con la pre-registrazione congelata |
| `revisione/cieca.py` | il controllo a mano alla cieca: fogli neutri e mescolati, scheda da compilare e conti con la chiave |
| `revisione/taratura.py` | sceglie i passi latenti e propone le soglie di confidenza dai giri di sviluppo |

## Uso

```bash
cd consiglio/revisione
uv venv -p 3.12.venv && uv pip install -p.venv -e../../motore -r../../motore/requirements.txt
.venv/bin/python -m pytest -q -m "not modello" # 27 test veloci
.venv/bin/python -m pytest -q # 31 test, con Qwen3-0.6B

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

## L'eval 

Le regole sono in [`consiglio/PREREGISTRAZIONE.md`](../PREREGISTRAZIONE.md), che va congelata e committata prima del giro di test.

```bash
# Tutte le configurazioni con il modello caricato una volta: telepatia, testo, agente solo, voto fra 4 e le tre
# prove di sabotaggio (pensieri azzerati, pensieri di un altro contratto, contratto scambiato).
.venv/bin/python -m revisione.esame esegui --benchmark cuad --insieme sviluppo --passi 10 --uscita esame
.venv/bin/python -m revisione.esame esegui --benchmark dimostrativo --passi 10 --configurazioni telepatia testo --uscita esame
.venv/bin/python -m revisione.esame rapporto esame # rapporto.md, numeri.json e un grafico per benchmark

# Taratura, dai giri di esegui con --passi 0 10 20 40
.venv/bin/python -m revisione.taratura risultati --benchmark cuad
```

- Ogni configurazione scrive `<benchmark>-<insieme>-<configurazione>.jsonl`, nella forma delle revisioni del Consiglio; `esame-<benchmark>-<insieme>.json` dice modello, dtype, dispositivo, passi, commit del codice e della pre-registrazione.
- **Sul test** `esame` parte solo se la pre-registrazione non è più una bozza, è committata e il codice di `consiglio/` e `motore/` non ha modifiche locali. Il test gira una volta: un secondo giro chiede `--deviazione "motivo"`.
- Il rapporto ha solo numeri aggregati e si può incollare nel ticket; i `.jsonl` contengono frasi dei contratti e restano nel team.

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
