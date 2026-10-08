// La MI300X è accesa? La casa dice "dal vivo adesso" oppure la prossima finestra.
import { gestisci, json, motore } from "../lib/comune.mjs";

export default {
  fetch: gestisci("GET", async () => {
    try {
      const r = await motore("/salute", { secondi: 4 });
      if (r.ok) {
        const s = await r.json();
        return json({ dal_vivo: s.demo === true, esame_in_corso: s.esame_in_corso === true });
      }
    } catch {
      // spento, irraggiungibile o non configurato: per il giudice è la stessa cosa
    }
    return json({ dal_vivo: false, esame_in_corso: false });
  }),
};
