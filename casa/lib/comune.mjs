// Ciò che serve alle funzioni della casa per i giudici. Le chiavi stanno solo nelle variabili d'ambiente di
// Vercel: il browser non le vede mai.

export class Errore extends Error {
  constructor(stato, messaggio) {
    super(messaggio);
    this.stato = stato;
  }
}

export const json = (dati, stato = 200) =>
  Response.json(dati, { status: stato, headers: { "Cache-Control": "no-store" } });

/** Il corpo della richiesta: un oggetto JSON piccolo, o un errore 400/413. */
export async function corpo(request, massimo = 4096) {
  const testo = await request.text();
  if (testo.length > massimo) throw new Errore(413, "richiesta troppo grande");
  let dati;
  try {
    dati = JSON.parse(testo);
  } catch {
    throw new Errore(400, "serve un oggetto JSON");
  }
  if (!dati || typeof dati !== "object" || Array.isArray(dati)) throw new Errore(400, "serve un oggetto JSON");
  return dati;
}

/** Una chiamata al server del motore sulla MI300X, con il segreto. */
export function motore(percorso, { method = "GET", dati, secondi = 10 } = {}) {
  const base = process.env.MOTORE_URL;
  const segreto = process.env.MOTORE_SEGRETO;
  if (!base || !segreto) throw new Errore(503, "motore non configurato");
  return fetch(new URL(percorso, base), {
    method,
    headers: { Authorization: `Bearer ${segreto}`, ...(dati ? { "Content-Type": "application/json" } : {}) },
    body: dati ? JSON.stringify(dati) : undefined,
    signal: AbortSignal.timeout(secondi * 1000),
  });
}

/** Il gestore della funzione: gli errori previsti con il loro stato, gli altri come 500 senza dettagli. */
export const gestisci = (metodo, fn) => async (request) => {
  try {
    if (request.method !== metodo) throw new Errore(405, `solo ${metodo}`);
    return await fn(request);
  } catch (e) {
    if (e instanceof Errore) return json({ errore: e.message }, e.stato);
    console.error(e);
    return json({ errore: "errore interno" }, 500);
  }
};
