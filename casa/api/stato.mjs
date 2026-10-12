// La MI300X è accesa? La casa dice "dal vivo adesso" oppure la prossima finestra. Lo Sportello e il Consiglio
// hanno ognuno il suo server: le prove dal vivo di ognuno si accendono quando risponde il suo.
import { consiglio, gestisci, json, motore } from "../lib/comune.mjs";

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
    const [s, c] = await Promise.all([salute(motore), salute(consiglio)]);
    return json({
      dal_vivo: s?.demo === true,
      esame_in_corso: s?.esame_in_corso === true,
      consiglio: { dal_vivo: c?.prove === true, occupato: c?.esame_in_corso === true },
    });
  }),
};
