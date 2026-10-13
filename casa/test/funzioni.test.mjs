// Le funzioni della casa con un server del Consiglio finto al posto di fetch.
import assert from "node:assert/strict";
import { afterEach, beforeEach, test } from "node:test";

import consiglio from "../api/consiglio.mjs";
import stato from "../api/stato.mjs";

const veroFetch = globalThis.fetch;
let chiamate;

function finto(risposte) {
  chiamate = [];
  globalThis.fetch = async (url, opzioni = {}) => {
    const u = new URL(url);
    chiamate.push({ url: u, opzioni });
    const r = risposte(u, opzioni);
    if (r instanceof Error) throw r;
    return Response.json(r.dati ?? {}, { status: r.stato ?? 200 });
  };
}

const post = (url, dati) => new Request(url, { method: "POST", body: JSON.stringify(dati) });

beforeEach(() => {
  process.env.CONSIGLIO_URL = "https://consiglio.example";
  process.env.CONSIGLIO_SEGRETO = "segreto-del-consiglio";
});
afterEach(() => {
  globalThis.fetch = veroFetch;
});

test("la prova dal vivo del Consiglio porta solo la chiave del contratto, con il segreto del Consiglio", async () => {
  finto((u) => (u.pathname === "/prove/contratti" ? { dati: [{ chiave: "cuad:X", titolo: "X" }] } : { stato: 409, dati: { errore: "riprova fra un minuto" } }));

  const elenco = await consiglio.fetch(new Request("https://casa.example/api/consiglio"));
  const occupato = await consiglio.fetch(post("https://casa.example/api/consiglio", { contratto: "cuad:X" }));

  assert.deepEqual(await elenco.json(), [{ chiave: "cuad:X", titolo: "X" }]);
  assert.equal(occupato.status, 409);
  assert.equal(chiamate[1].url.href, "https://consiglio.example/prove/contratto");
  assert.equal(chiamate[1].opzioni.headers.Authorization, "Bearer segreto-del-consiglio");
  assert.deepEqual(JSON.parse(chiamate[1].opzioni.body), { contratto: "cuad:X", modalita: "telepatia" });
  assert.doesNotMatch(await occupato.text(), /segreto-del-consiglio/);
});

test("un testo al posto del contratto, o una modalità sconosciuta, non arriva al Consiglio", async () => {
  finto(() => ({ dati: {} }));

  const testo = await consiglio.fetch(post("https://casa.example/api/consiglio", { contratto: "cuad:X", testo: "il mio contratto" }));
  const modalita = await consiglio.fetch(post("https://casa.example/api/consiglio", { contratto: "cuad:X", modalita: "urlo" }));
  const vuoto = await consiglio.fetch(post("https://casa.example/api/consiglio", {}));

  assert.deepEqual([testo.status, modalita.status, vuoto.status], [400, 400, 400]);
  assert.equal(chiamate.length, 0);
});

test("a Consiglio spento la prova è un 503, e lo stato dice che non si è dal vivo", async () => {
  finto(() => new TypeError("fetch failed"));

  const r = await consiglio.fetch(post("https://casa.example/api/consiglio", { contratto: "cuad:X" }));
  const s = await (await stato.fetch(new Request("https://casa.example/api/stato"))).json();

  assert.equal(r.status, 503);
  assert.deepEqual(s, { consiglio: { dal_vivo: false, occupato: false } });
});

test("a Consiglio acceso lo stato dice dal vivo, e occupato se c'è un esame in corso", async () => {
  finto(() => ({ dati: { prove: true, esame_in_corso: true } }));

  const s = await (await stato.fetch(new Request("https://casa.example/api/stato"))).json();

  assert.deepEqual(s, { consiglio: { dal_vivo: true, occupato: true } });
  assert.equal(chiamate[0].url.href, "https://consiglio.example/salute");
});
