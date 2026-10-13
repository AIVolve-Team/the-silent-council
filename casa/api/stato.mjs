// La MI300X è accesa? La casa dice "dal vivo adesso" oppure la prossima finestra: le prove dal vivo del Consiglio
// si accendono quando risponde il suo server.
import { consiglio, gestisci, json } from "../lib/comune.mjs";

async function salute(chiama) {
  try {
    const r = await chiama("/salute", { secondi: 4 });
    if (r.ok) return await r.json();
  } catch {
    // spento, irraggiungibile o non configurato: per il giudice è la stessa cosa
  }
  return null;
}

export default {
  fetch: gestisci("GET", async () => {
    const c = await salute(consiglio);
    return json({ consiglio: { dal_vivo: c?.prove === true, occupato: c?.esame_in_corso === true } });
  }),
};
