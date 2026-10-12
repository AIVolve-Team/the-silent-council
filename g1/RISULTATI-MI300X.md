# G1 sulla MI300X: cosa abbiamo dimostrato (12/10/2026)

**In breve: G1 passa, nella zona migliore, "dimostrato".**
Il nostro motore telepatico gira su una sola AMD MI300X insieme all'agente principale. Fa generare l'**81% di token in meno** del testo, risponde in circa **un quarto del tempo** e sbaglia solo un problema in più su 100.


## Che cos'è G1

G1 è il **primo cancello** del progetto: la prima prova sulla GPU vera. Risponde a una domanda sola: *la telepatia fra agenti funziona davvero sulla MI300X, o solo sul Mac?*

Se G1 non passava, cadevano sia lo Sportello sia il Consiglio, e si passava al pavimento a testo.

## Cosa abbiamo confrontato

Quattro agenti, tutti Qwen3-14B, risolvono problemi di matematica scritti a parole. Sono i primi 100 del test ufficiale di **GSM8K**, un benchmark pubblico molto usato. Gli agenti lavorano in fila:
- tre **analisti**: chi pianifica, chi rivede e chi perfeziona;
- un **risolutore**, che scrive la risposta finale.

Ogni problema viene risolto in tre modi:

| Modo | Come si passano il lavoro gli analisti |
|---|---|
| **Testo** | Ognuno scrive la sua analisi, al massimo 1.024 token, e il successivo la legge. È il modo classico. |
| **Telepatia, 10 passi** | Ognuno passa al successivo la sua **memoria di lavoro interna** (la cache KV), senza scrivere niente. Prima di passarla "pensa in silenzio" per 10 passi. 10 è il valore usato dagli autori di LatentMAS su GSM8K. |
| **Senza pensieri, 0 passi** | Come la telepatia, ma senza i passi di pensiero: si passa solo la memoria della lettura. È il gruppo di controllo che dice se i passi servono. |

In tutti e tre i modi scrive solo il risolutore. Le regole di contorno erano fissate prima di misurare, nel README:
- decodifica deterministica, cioè lo stesso input dà la stessa uscita;
- thinking spento;
- un solo giro.

## Le metriche e le soglie

Erano fissate **prima** di misurare, e nel README.

| Metrica | Cosa misura | Soglia per passare |
|---|---|---|
| **Memoria** | Il motore (Qwen3-14B) e l'agente principale (Qwen3.6-35B-A3B su vLLM) girano insieme sulla stessa scheda senza errori di memoria. | Nessun errore |
| **Token generati** | Quanti token scrivono gli agenti in telepatia rispetto al testo. È il costo: ogni token generato è tempo di GPU. | Almeno il **50% in meno** |
| **Precisione** | Percentuale di problemi con la risposta giusta. Si confronta la telepatia (10 passi) con il testo. | Tre zone, sotto |

Le tre zone della precisione, telepatia meno testo:
- **entro 3 punti:** *dimostrato*;
- **da 3 a 10 punti sotto:** si va avanti, e decidono G2 e l'eval del Consiglio;
- **più di 10 punti sotto:** ci si ferma e si passa al pavimento a testo.

## I risultati

Giro completo sui 100 problemi, dalle 16:34 alle 17:52 (ora italiana).

| Modo | Risposte giuste | Token generati | Secondi per problema |
|---|---|---|---|
| Testo | **97** su 100 | 124.790 | 34,3 |
| Telepatia, 10 passi | **96** su 100 | 23.697 (**−81%**) | 7,6 |
| Senza pensieri, 0 passi | **98** su 100 | 16.135 (−87%) | 4,7 |

| Metrica | Risultato | Esito |
|---|---|---|
| Memoria | Due modelli insieme: 138 GB usati su 206. Pesi 99,9 GB, picco del motore 37,9 GB. | ✓ |
| Token generati | −81% rispetto al testo | ✓ (soglia −50%) |
| Precisione | 96% contro 97%: **−1,0 punti** | ✓ zona **dimostrato** |

**G1 passa.**

### Cosa vuol dire, in parole semplici

1. **Funziona sull'hardware vero.** Non è più un esperimento da Mac: gira sulla MI300X con il modello vero, in bf16, con i kernel di attenzione veloci di ROCm.
2. **Costa molto meno.** Per arrivare alla stessa risposta gli agenti scrivono un quinto dei token e ci mettono meno di un quarto del tempo: 7,6 secondi contro 34,3 a problema.
3. **Non perde precisione.** Un punto su 100 è dentro la soglia "dimostrato". Gli errori sono pochi in tutti e tre i modi:
   - testo: problemi 37, 58 e 62;
   - telepatia: problemi 12, 20, 21 e 62;
   - senza pensieri: problemi 37 e 62.
4. **I "pensieri" non sono il punto forte.** Senza i passi di pensiero la telepatia è persino un po' più precisa (98 contro 96) e più veloce (4,7 secondi contro 7,6). Il valore sta nel **passarsi la memoria di lavoro**, non nel pensiero in più. È lo stesso schema visto sul Mac col Consiglio. Quanti passi usare per il Consiglio lo decide la sua taratura.
5. **La MI300X serve davvero.** I due modelli insieme pesano 99,9 GB: su una scheda da 80 GB, come una H100, non ci starebbero.

### Un limite da dire onestamente

GSM8K è matematica facile per un modello da 14B: il risolutore potrebbe arrivare alla risposta giusta quasi da solo. G1 dimostra bene **costo, velocità e memoria**. Dice meno sul fatto che la memoria passata fra agenti migliori il ragionamento. Per quello conta l'eval del Consiglio sui contratti.

## Gli altri controlli

- **fp32 contro bf16**, 5 problemi. È un controllo di sicurezza: su ROCm i kernel di attenzione con maschere hanno avuto bug che davano numeri sbagliati senza errori. Le risposte coincidono 5 su 5, tutte giuste. I testi divergono un po', come previsto con i numeri arrotondati di bf16.
- **Messaggio latente da 4.103 token:**
  - pesa 0,67 GB;
  - la sua impronta di controllo si calcola in 0,45 secondi;
  - il ricalcolo dei pensieri in bf16 è identico.
- **Agente principale** (Qwen3.6 su vLLM, per Evolus): risponde in 0,8 secondi con una vera chiamata allo strumento `esamina_fattura` e senza pensiero.

## Cosa è cambiato rispetto alla procedura

1. **Il riferimento fp32 usa il backend "math" di PyTorch.**
   - **Il problema:** il primo tentativo si è fermato con `No available kernel`. In fp32 nessuno dei kernel veloci accetta il formato che Qwen3 usa per la memoria (8 teste invece di 40), e il codice vietava il backend lento e sicuro.
   - **La correzione:** ora il **solo** riferimento fp32 usa quel backend (`g1/esegui.py`, `vincolo_sdpa`, con 3 test in `tests/test_vincolo.py`). Il giro vero in bf16 resta con il divieto. Il riferimento così è anche indipendente dai kernel che controlla.
2. **`--max-num-seqs 256` a vLLM.** Senza il flag Qwen3.6 non parte con metà scheda. La memoria occupata non cambia. È già nel comando del README.
3. **Il nome della scheda risulta vuoto** (`"gpu": ""` in `ambiente.json`). La MI300X virtualizzata del cloud non lo espone. Architettura gfx942, 304 compute unit e 192 GB confermano che è una MI300X.
4. **Setup della macchina:**
   - `hf` va installato in un venv a parte, con `python3.12-venv`;
   - il repo copiato va passato a root, altrimenti git lo rifiuta;
   - il firewall limita le connessioni SSH ravvicinate, quindi conviene una connessione condivisa.

## Tempi veri

| Passo | Tempo |
|---|---|
| Download di modelli e immagine (circa 110 GB) | circa 2 minuti |
| Container e venv | circa 3 minuti |
| fp32 contro bf16 | circa 3 minuti |
| Avvio di vLLM | circa 4 minuti |
| Misura della memoria | circa 1 minuto |
| Tre giri su 100 problemi | 78 minuti |

Macchina: AMD Developer Cloud, 1× MI300X da 192 GB, ROCm 7.2. Software:
- immagine `vllm/vllm-openai-rocm:v0.30.0`;
- torch `2.12.0+git6bbd260` (HIP 7.2) e transformers 4.57.6;
- Qwen3-14B alla revisione `40c069824f4251a91eefaf281ebe4c544efd3e18`.
