# Taratura del Consiglio sulla MI300X (12/10/2026)

**In breve: vincono 0 passi latenti.**
Sul set di sviluppo la telepatia batte il testo in qualità (F1 71,4 contro 52,6 su CUAD) e costa meno: meno della metà dei token generati e circa un terzo di tempo in meno.
L'accordo con i giri del Mac è fra il 96 e il 100%, quindi il test pre-registrato può partire dopo il congelamento.

Qui ci sono solo numeri aggregati. I `.jsonl` del set dimostrativo contengono frasi dei contratti e restano privati.

## Cosa abbiamo tarato

La taratura mette a punto **due cose** prima del test, sul set di **sviluppo**. Si sceglie su un set e si misura su un altro, una volta sola: così il risultato del test non si può "aggiustare".

1. **I passi latenti**, la manopola della telepatia. Ogni agente legge la sua sezione del contratto e passa al collega la sua memoria di lavoro (la cache KV). Prima di passarla può "pensare in silenzio" per qualche passo: ogni passo è una parola che il modello aggiunge alla memoria senza scriverla. Si provano 0, 10, 20 e 40 passi.
   - **Regola** (pre-registrazione): sul set di sviluppo di CUAD vince l'F1 più alto e, sotto 1 punto di differenza, il valore con meno passi.
2. **Le soglie di confidenza.** Per ogni clausola il Consiglio dice anche quanto è sicuro, una probabilità da 0 a 1. La pagina del verdetto mostra un'etichetta, alta, media o bassa. La taratura controlla se le etichette dicono il vero: quando dice "alta" dovrebbe avere ragione almeno 9 volte su 10.

## Le metriche

Per ogni contratto c'è la lista delle clausole da segnalare, con la risposta giusta (CUAD: annotazioni di esperti; set dimostrativo: le nostre). Per ogni clausola il Consiglio dice sì o no.

| Metrica | Cosa misura |
|---|---|
| **Precisione (P)** | Delle clausole segnalate, quante erano davvero da segnalare: i falsi allarmi |
| **Richiamo (R)** | Delle clausole da segnalare, quante ne ha trovate: quelle sfuggite |
| **F1** | La media fra precisione e richiamo, da 0 a 100: il voto di qualità |
| **MCC** | Correlazione fra risposte e verità, da −1 a 1; tiene conto anche dei "no" giusti |
| **Note come verdetto** | L'F1 se si usassero le note dei singoli agenti invece del verdetto finale |

## I risultati

Qwen3-14B in bf16 con riallineamento W_a spento, come deciso dalla diagnosi.

### CUAD (pubblico, 5 contratti di sviluppo)

| Modo | Passi | F1 | P | R | MCC | Token generati per contratto | Secondi per contratto |
|---|---|---|---|---|---|---|---|
| telepatia | **0** | **71,4** | 71,4 | 71,4 | 0,63 | 1.217 | 70 |
| telepatia | 10 | 65,1 | 63,6 | 66,7 | 0,55 | | |
| telepatia | 20 | 58,5 | 60,0 | 57,1 | 0,47 | | |
| telepatia | 40 | 61,5 | 66,7 | 57,1 | 0,52 | | |
| testo | | 52,6 | 58,8 | 47,6 | 0,41 | 2.776 | 103 |

Con 40 passi un verdetto su 5 non è valido.

### Set dimostrativo (italiano, privato, 4 contratti)

| Modo | Passi | F1 | P | R | MCC | Token generati per contratto | Secondi per contratto |
|---|---|---|---|---|---|---|---|
| telepatia | 0, 10, 20, 40 | **98,2** | 96,6 | 100 | 0,97 | 1.438 (0 passi) | 67 (0 passi) |
| testo | | 76,6 | 94,7 | 64,3 | 0,69 | 2.894 | 101 |

### Passi scelti: **0**

Con la regola della pre-registrazione vince 0 passi (F1 71,4 su CUAD). Sul set dimostrativo i passi non cambiano niente.
Per, con 0 passi le prove sui pensieri non si fanno e per la giuria vale la frase di riserva.

È lo stesso schema visto altrove:
- sul Mac, CUAD: 68,8 con 0 passi contro 56,2 con 10;
- G1 su GSM8K: 98 su 100 con 0 passi contro 96 con 10 ([g1/RESULTS-MI300X.md](../g1/RESULTS-MI300X.md)).

**Il valore della telepatia sta nel passarsi la memoria della lettura, non nel pensiero in più.** Vale per il modello così com'è, senza addestramento: addestrarlo a usare i passi è la proposta, per dopo l'hackathon.

### Qualità, non solo costo

Con 0 passi la telepatia **trova molte più clausole rischiose** del testo:
- **richiamo:** 71 contro 48 su CUAD, 100 contro 64 sul dimostrativo;
- **precisione:** non scende, anzi sale un po'.

Una spiegazione possibile: a testo ogni agente riassume e perde dettagli, in telepatia il collega riceve tutta la memoria della lettura.

### Confidenza: il modello è troppo sicuro di sé

Decisioni (verdetti e note) di telepatia e testo, con 0 passi:

| Confidenza | CUAD: decisioni | CUAD: giuste | Dimostrativo: decisioni | Dimostrativo: giuste |
|---|---|---|---|---|
| 0,50–0,60 | 2 | 100% | | |
| 0,60–0,70 | 4 | 75% | | |
| 0,70–0,80 | 9 | 67% | 1 | 100% |
| 0,80–0,85 | 1 | 100% | | |
| 0,85–0,90 | 4 | 75% | | |
| 0,90–0,95 | 7 | 86% | 1 | 100% |
| 0,95–0,99 | 14 | 64% | 2 | 100% |
| 0,99–1,00 | 149 | 89% | 148 | 97% |

- **Su CUAD nessuna soglia arriva a 9 decisioni giuste su 10:** anche sopra 0,99 sono giuste l'89%. Quasi tutte le decisioni stanno sopra 0,99, quindi l'etichetta "alta" non distingue le decisioni sicure da quelle dubbie.
- **Sul dimostrativo** lo script propone 0,60 per tutte e due le soglie, ma con 4 casi sotto 0,99 il dato non regge.
- **Soglie confermate** prima della taratura: 0,9 per "alta" e 0,7 per "media". Nella pre-registrazione la taratura della confidenza è una **misura senza soglia**: si riporta, non decide il verdetto. Va scritto chiaro che oggi "alta" non vuol dire "fidati senza controllare".

## Accordo con il Mac

Stesso codice, stessi contratti, sì/no del verdetto confrontati clausola per clausola fra i giri del Mac (diagnosi del 12/10) e quelli della MI300X:

| Giro | Contratti in comune | Coppie | Accordo |
|---|---|---|---|
| CUAD, telepatia 0 passi | 4 | 76 | 98,7% |
| CUAD, telepatia 10 passi | 4 | 76 | 96,1% |
| CUAD, testo | 4 | 76 | 98,7% |
| Dimostrativo, telepatia 0 passi | 4 | 76 | 100% |
| Dimostrativo, telepatia 10 passi | 4 | 76 | 100% |
| Dimostrativo, telepatia 40 passi | 4 | 76 | 100% |

Le divergenze sono poche e coerenti con hardware diverso (MPS in fp32 sul Mac, ROCm in bf16 sulla MI300X). Nessun motivo di fermarsi prima del test.

## Cautele

- **Pochi contratti:** è il set di sviluppo, che serve a tarare, non a dimostrare. Il numero ufficiale esce dal **test**: CUAD, ContractNLI e CLAUDETTE, con le regole congelate prima.
- **Il set dimostrativo l'abbiamo scritto noi**, quindi è indicativo. Il dato solido è CUAD.

## Prossimi passi

1. **Congelamento** su questo ramo:
   - i passi a 0;
   - le soglie;
   - la sezione "Taratura sulla MI300X" della pre-registrazione, da questo documento;
   - qualcuno del team rilegge le definizioni operative;
   - `Stato: congelata`, commit e push.
2. **Test**, una volta sola: `PASSI=0./consiglio/mi300x.sh test` (vedi MI300X.md, passo 5).

## Macchina e tempi

- **Macchina:** AMD Developer Cloud, 1× MI300X da 192 GB, ROCm 7.2.
- **Software:** immagine `vllm/vllm-openai-rocm:v0.30.0`, torch `2.12.0+git6bbd260`, transformers 4.57.6.
- **Codice:** ramo `feat/eval` al commit `1ad3b02`.
- **Prova veloce:** `Fatto.`, `GPU: cuda`, pesi in bfloat16; telepatia con 10 passi sul dimostrativo F1 98,2, come sul Mac.
- **Taratura:** dalle 17:59 alle 18:59 (ora italiana), circa un'ora per 45 revisioni.
