// La scelta della persona verso il secondo workflow di Evolus, che chiama registra_decisione sul motore.
// Ogni giro Evolus costa crediti, e le prove dei giudici non passano da Evolus: la funzione è spenta finché
// EVOLUS_ATTIVO non vale 1, cosa che si fa solo per le riprese del video e per il palco. Da spenta risponde 503 e la
// pagina dice "decisione salvata in questo browser".
// La chiamata segue la pagina per sviluppatori di Evolus (https://evolus.ai/en/developers, letta il 9/10): multipart,
// X-ApiKey e X-Application-Id (lo "Space ID"), i parametri dichiarati nel workflow in "parameters", niente callbackUrl.
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

    const { EVOLUS_URL = "https://api.evolus.ai", EVOLUS_WORKFLOW, EVOLUS_API_KEY, EVOLUS_SPAZIO } = process.env;
    if (!EVOLUS_WORKFLOW || !EVOLUS_API_KEY || !EVOLUS_SPAZIO) throw new Errore(503, "Evolus non configurato");
    const modulo = new FormData();
    const parametri = { id_caso, decisione, chi: "persona sulla pagina del caso", nota: nota.trim() };
    modulo.set("input", `Decisione della persona sul caso ${id_caso}: ${decisione}`);
    modulo.set("parameters", JSON.stringify(parametri));
    const r = await fetch(new URL(`/api/v1/workflows/${encodeURIComponent(EVOLUS_WORKFLOW)}/execute`, EVOLUS_URL), {
      method: "POST",
      headers: { "X-ApiKey": EVOLUS_API_KEY, "X-Application-Id": EVOLUS_SPAZIO },
      body: modulo,
      signal: AbortSignal.timeout(15000),
    });
    if (!r.ok) throw new Errore(502, "Evolus non ha accettato la decisione");
    return json({ inviata: true }, 202);
  }),
};
