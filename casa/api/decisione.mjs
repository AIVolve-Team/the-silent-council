// La scelta della persona verso il secondo workflow di Evolus, che chiama registra_decisione sul motore.
// Ogni giro Evolus costa crediti, e le prove dei giudici non passano da Evolus: la funzione è spenta finché
// EVOLUS_ATTIVO non vale 1, cosa che si fa solo per le riprese del video e per il palco. Da spenta risponde 503 e la
// pagina dice "decisione salvata in questo browser".
// Da verificare al kickoff (12/10): l'intestazione della chiave (EVOLUS_INTESTAZIONE) e il formato dell'ingresso.
import { Errore, corpo, gestisci, json, motore } from "../lib/comune.mjs";

const DECISIONI = ["approvato", "rifiutato", "segnalato"];
const ID_CASO = /^sportello-[0-9a-f]{12}$/;

export default {
  fetch: gestisci("POST", async (request) => {
    const { id_caso, decisione, nota = "" } = await corpo(request);
    if (process.env.EVOLUS_ATTIVO !== "1") throw new Errore(503, "Evolus è spento: la decisione resta in questo browser");
    if (typeof id_caso !== "string" || !ID_CASO.test(id_caso)) throw new Errore(400, "id_caso non valido");
    if (!DECISIONI.includes(decisione)) throw new Errore(400, `decisione: ${DECISIONI.join(", ")}`);
    if (typeof nota !== "string" || nota.length > 1000) throw new Errore(400, "nota: al massimo 1000 caratteri");

    // Prima il motore: il caso deve esistere, e la stessa decisione non riparte, perché ogni giro costa crediti.
    let caso;
    try {
      caso = await motore(`/casi/${id_caso}`, { secondi: 8 });
    } catch (e) {
      if (e instanceof Errore) throw e;
      throw new Errore(503, "il motore è spento: la decisione resta in questo browser");
    }
    if (caso.status === 404) throw new Errore(404, "il motore non conosce questo caso");
    if (!caso.ok) throw new Errore(502, "il motore non risponde come dovrebbe");
    const ultima = (await caso.json()).decisioni.at(-1);
    if (ultima && ultima.decisione === decisione && ultima.nota === nota.trim()) return json({ inviata: true, gia_registrata: true });

    const { EVOLUS_URL, EVOLUS_WORKFLOW, EVOLUS_API_KEY, EVOLUS_INTESTAZIONE } = process.env;
    if (!EVOLUS_URL || !EVOLUS_WORKFLOW || !EVOLUS_API_KEY) throw new Errore(503, "Evolus non configurato");
    const chiave = EVOLUS_INTESTAZIONE ? { [EVOLUS_INTESTAZIONE]: EVOLUS_API_KEY } : { Authorization: `Bearer ${EVOLUS_API_KEY}` };
    const r = await fetch(new URL(`/api/v1/workflows/${encodeURIComponent(EVOLUS_WORKFLOW)}/execute`, EVOLUS_URL), {
      method: "POST",
      headers: { ...chiave, "Content-Type": "application/json" },
      body: JSON.stringify({ input: { id_caso, decisione, chi: "persona sulla pagina del caso", nota: nota.trim() } }),
      signal: AbortSignal.timeout(15000),
    });
    if (!r.ok) throw new Errore(502, "Evolus non ha accettato la decisione");
    return json({ inviata: true }, 202);
  }),
};
