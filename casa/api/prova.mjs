// Le prove dal vivo dello Sportello: vanno dritte al motore, mai a Evolus. Una alla volta: se il motore sta
// già esaminando risponde 409, e la pagina dice di riprovare fra un minuto.
import { Errore, corpo, gestisci, json, motore } from "../lib/comune.mjs";

const CAMPI = {
  fattura: ["id", "modalita", "livello2"],
  attacco: ["numero", "modalita", "livello2"],
  inganna: ["id", "testo", "modalita", "livello2"],
};

export default {
  fetch: gestisci("POST", async (request) => {
    const { tipo, ...campi } = await corpo(request);
    if (!Object.hasOwn(CAMPI, tipo)) throw new Errore(400, "tipo: fattura, attacco o inganna");
    const inPiu = Object.keys(campi).filter((k) => !CAMPI[tipo].includes(k));
    if (inPiu.length) throw new Errore(400, `campi non previsti: ${inPiu.join(", ")}`);
    let r;
    try {
      r = await motore(`/prove/${tipo}`, { method: "POST", dati: campi, secondi: 280 });
    } catch (e) {
      if (e instanceof Errore) throw e;
      throw new Errore(503, "il motore è spento o non risponde");
    }
    if (r.status === 401) {
      console.error("il motore rifiuta il segreto della casa");
      throw new Errore(502, "la casa non è autorizzata dal motore");
    }
    const dati = await r.json().catch(() => ({ errore: "risposta non valida dal motore" }));
    return json(dati, [200, 400, 404, 409].includes(r.status) ? r.status : 502);
  }),
};
