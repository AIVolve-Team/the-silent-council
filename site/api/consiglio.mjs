// Le prove dal vivo del Consiglio: il giudice sceglie un contratto dall'elenco del server, mai un testo suo.
// GET dà l'elenco, POST lo fa esaminare adesso. Una prova alla volta: se il Consiglio è occupato il server risponde 409
// e la pagina dice di riprovare fra un minuto.
import { Errore, consiglio, corpo, json } from "../lib/comune.mjs";

const MODALITA = ["telepatia", "testo"];

async function inoltra(percorso, opzioni) {
  let r;
  try {
    r = await consiglio(percorso, opzioni);
  } catch (e) {
    if (e instanceof Errore) throw e;
    throw new Errore(503, "il Consiglio è spento o non risponde");
  }
  if (r.status === 401) {
    console.error("il Consiglio rifiuta il segreto della casa");
    throw new Errore(502, "la casa non è autorizzata dal Consiglio");
  }
  if (r.status === 404) throw new Errore(503, "le prove dal vivo del Consiglio sono spente");
  const dati = await r.json().catch(() => ({ errore: "risposta non valida dal Consiglio" }));
  return json(dati, [200, 400, 409].includes(r.status) ? r.status : 502);
}

export default {
  async fetch(request) {
    try {
      if (request.method === "GET") return await inoltra("/prove/contratti", { secondi: 10 });
      if (request.method !== "POST") throw new Errore(405, "solo GET o POST");
      const dati = await corpo(request);
      const inPiu = Object.keys(dati).filter((k) => !["contratto", "modalita"].includes(k));
      if (inPiu.length) throw new Errore(400, `campi non previsti: ${inPiu.join(", ")}`);
      if (typeof dati.contratto !== "string" || !dati.contratto || dati.contratto.length > 300) throw new Errore(400, "contratto: la chiave di un contratto dell'elenco");
      const modalita = dati.modalita ?? "telepatia";
      if (!MODALITA.includes(modalita)) throw new Errore(400, "modalita: telepatia o testo");
      return await inoltra("/prove/contratto", { method: "POST", dati: { contratto: dati.contratto, modalita }, secondi: 290 });
    } catch (e) {
      if (e instanceof Errore) return json({ errore: e.message }, e.stato);
      console.error(e);
      return json({ errore: "errore interno" }, 500);
    }
  },
};
