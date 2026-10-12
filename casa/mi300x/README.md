# casa/mi300x — la MI300X a finestre

Codice, come deciso in "Dove gira l'app per i giudici": la MI300X nasce da uno snapshot quando serve e si distrugge quando non serve, **perché anche spenta si paga**.
Le prove dal vivo della casa per i giudici funzionano solo a macchina accesa; i casi registrati funzionano sempre.

| File | Cosa fa |
|---|---|
| `mi300x.sh` | conto, stato, crea, distruggi, snapshot, finestre: le chiamate all'API, provate contro un'API finta |
| `../../.github/workflows/mi300x.yml` | ogni mezz'ora: accesa dentro le finestre di `../finestre.json`, distrutta fuori |
| `../test/mi300x.test.mjs` | i test, con un'API di DigitalOcean finta (`npm test` in `casa/`) |

## Cosa sappiamo di AMD Developer Cloud

Ricerca del 9/10 sulle pagine di DigitalOcean e AMD; ciò che nessuna pagina conferma è da provare il 12/10.

- **È DigitalOcean:** console su devcloud.amd.com, stessa API `/v2` con un token personale ([DigitalOcean, AMD](https://docs.digitalocean.com/products/amd/), [creare una macchina](https://docs.digitalocean.com/products/amd/how-to/create/)). Il token si crea dalla console AMD, voce "API". *Da provare:* se il token AMD va su `api.digitalocean.com` o su `api.devcloud.amd.com` (`DO_API`): lo dice `mi300x.sh conto`.
- **La macchina:** `gpu-mi300x1-192gb`, solo nella regione `atl1`; disco di avvio da 720 GB, che sta negli snapshot, e scratch da 5 TB, che **non** ci sta e si perde quando la macchina si distrugge ([dettagli](https://docs.digitalocean.com/products/amd/details/features/), [scratch](https://docs.digitalocean.com/products/amd/how-to/use-scratch-disk/)). Per questo modelli e codice vanno sul disco di avvio.
- **Costi:** 2,59 $ l'ora; **spenta si paga lo stesso**, solo distrutta no ([prezzi](https://docs.digitalocean.com/products/amd/details/pricing/), [FAQ AMD](https://www.amd.com/en/developer/resources/cloud-access/amd-developer-cloud.html)). Gli snapshot costano 0,06 $ per GB al mese e non sono incrementali.
- **Crediti:** 100 $ a persona, circa 38 ore di MI300X. Si chiedono dalla pagina AMD ("Member Perks" › "Request Cloud Credits"), arrivano in **2-3 giorni lavorativi**, scadono **30 giorni** dopo l'attivazione e serve una carta registrata ([AMD, 22/6/2026](https://www.amd.com/en/developer/resources/technical-articles/2026/how-to-claim-amd-cloud-credits.html), [crediti](https://docs.digitalocean.com/products/amd/details/credits/)). Se il credito finisce senza carta, AMD distrugge la macchina e i suoi dati.
- **Una trappola dell'API:** l'elenco delle macchine nasconde le GPU se non si chiede `type=gpus`, e quel filtro non si combina con il tag ([droplets](https://docs.digitalocean.com/reference/api/reference/droplets/)). `mi300x.sh` elenca le GPU e filtra il tag da sé, distrugge per id e poi ricontrolla: se ne resta una accesa, esce con un errore.

## Comandi

```bash
export DIGITALOCEAN_ACCESS_TOKEN=… # mai nel repo
casa/mi300x/mi300x.sh conto # il token va? quanto si è speso?
casa/mi300x/mi300x.sh stato
MI300X_SSH=<impronta> casa/mi300x/mi300x.sh crea aspetta # dall'ultimo snapshot golden-*, con i tempi
casa/mi300x/mi300x.sh distruggi
casa/mi300x/mi300x.sh snapshot # spegne e fotografa la macchina accesa (golden-AAAAMMGG-HHMM)
```

- **Crea non ne accende mai due:** se ce n'è già una con il tag, si ferma lì.
- **Le macchine a mano** (tag `sportello-mi300x`) e **quelle delle finestre** (tag `sportello-finestra`) sono separate: l'automatico non spegne mai una macchina su cui qualcuno sta lavorando, per esempio l'esame della notte fra il 15 e il 16/10.
- `crea aspetta` scrive quanti secondi servono per essere attiva e, con `MI300X_SALUTE=https://<motore>/salute`, per avere il motore pronto: è il **tempo di nascita da snapshot** che chiede.

## Il 12/10: la macchina d'oro

1. **Si prepara una macchina** come nel runbook di G1 (`g1/README.md`), con modelli e codice sul **disco di avvio**.
2. **I servizi ripartono da soli** quando una macchina nasce dallo snapshot: container con `--restart unless-stopped`.
   - vLLM come al passo 5 del runbook di G1, sulla porta 8000;
   - il server del motore (`sportello/servizio`, `--demo`) sulla porta **8100**, perché la 8000 è di vLLM;
   - Caddy davanti, per TLS: `motore.<dominio>` → `127.0.0.1:8100`, `vllm.<dominio>` → `127.0.0.1:8000`.
   - I segreti (`SPORTELLO_SEGRETO`, `VLLM_API_KEY`) in un file del disco di avvio con permessi 600, letto dai container con `--env-file`.
3. **Prima dello snapshot Caddy deve aver già preso il certificato.** Let's Encrypt dà al massimo 5 certificati a settimana per lo stesso nome: se ogni macchina nuova ne chiedesse uno, dal sesto giorno il motore resterebbe senza TLS. Con il certificato nello snapshot, le macchine nuove lo riusano (vale 90 giorni).
4. **Lo snapshot:** `mi300x.sh snapshot`. Ci vogliono circa **1-3 minuti per GB usato**, e intanto la macchina si paga: con circa 130 GB fra modelli, immagine e codice, da 2 a 6 ore. Conviene lanciarlo a fine giornata e poi distruggere la macchina.
5. **Il tempo di nascita** si misura la mattina dopo con `crea aspetta` e si scrive, accanto a quello di riscaricare i modelli da capo sullo scratch, per scegliere il più veloce.

## Il nome del motore

Ogni macchina nuova ha un IP nuovo, mentre Evolus e Vercel hanno bisogno di un nome fisso.
Se il dominio sta nel DNS di DigitalOcean, con `MI300X_DNS_DOMINIO` e `MI300X_DNS_NOME` lo script punta il record A al nuovo IP (TTL 60 s).
Con un dominio altrove basta delegare a DigitalOcean un sottodominio, per esempio `mi300x.<dominio>`. Quale dominio usare è una scelta del team, ancora aperta.

## Le finestre

- `../finestre.json` è lo stesso file che legge la home: `[{"inizio": "2026-10-19T09:00:00+02:00", "fine": "2026-10-19T19:00:00+02:00"}, …]`.
- I giorni si fissano il 12/10, quando si sa cosa dà l'organizzazione e fino a quando.
- **Il workflow** gira ogni mezz'ora, a:13 e:43, solo dal ramo principale. Accende la macchina 45 minuti prima di una finestra e la distrugge alla fine; se GitHub salta un giro, quello dopo rimette a posto.
  - Segreti del repo: `DIGITALOCEAN_ACCESS_TOKEN`, `MI300X_SSH`.
  - Variabili facoltative: `DO_API`, `MI300X_DNS_DOMINIO`, `MI300X_DNS_NOME`.
- **A mano**, da "Actions" › "MI300X a finestre" › "Run workflow": `stato`, `crea`, `distruggi`, e `distruggi-tutto`, che spegne anche le macchine accese a mano.
