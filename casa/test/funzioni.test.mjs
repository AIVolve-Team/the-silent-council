// Le funzioni della casa con un motore e un Evolus finti al posto di fetch.
import assert from "node:assert/strict";
import { afterEach, beforeEach, test } from "node:test";

import decisione from "../api/decisione.mjs";
import prova from "../api/prova.mjs";
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
  process.env.MOTORE_URL = "https://motore.example";
  process.env.MOTORE_SEGRETO = "segreto-del-motore";
  delete process.env.EVOLUS_ATTIVO;
  Object.assign(process.env, { EVOLUS_URL: "https://evolus.example", EVOLUS_WORKFLOW: "wf-2", EVOLUS_API_KEY: "chiave-evolus" });
});
afterEach(() => {
  globalThis.fetch = veroFetch;
});

test("una prova va al motore con il segreto, e il 409 di un esame in corso arriva al giudice", async () => {
  finto(() => ({ stato: 409, dati: { errore: "c'è già una prova in corso" } }));

  const r = await prova.fetch(post("https://casa.example/api/prova", { tipo: "attacco", numero: 2, livello2: false }));

  assert.equal(r.status, 409);
  assert.equal(chiamate[0].url.href, "https://motore.example/prove/attacco");
  assert.equal(chiamate[0].opzioni.headers.Authorization, "Bearer segreto-del-motore");
  assert.deepEqual(JSON.parse(chiamate[0].opzioni.body), { numero: 2, livello2: false });
  assert.doesNotMatch(await r.text(), /segreto-del-motore/);
});

test("una prova con un campo in più o un tipo sconosciuto non arriva al motore", async () => {
  finto(() => ({ dati: {} }));

  const inPiu = await prova.fetch(post("https://casa.example/api/prova", { tipo: "fattura", id: "x", url: "file:///" }));
  const tipo = await prova.fetch(post("https://casa.example/api/prova", { tipo: "__proto__" }));

  assert.equal(inPiu.status, 400);
  assert.equal(tipo.status, 400);
  assert.equal(chiamate.length, 0);
});

test("a motore spento la prova è un 503 e lo stato dice che non si è dal vivo", async () => {
  finto(() => new TypeError("fetch failed"));

  const r = await prova.fetch(post("https://casa.example/api/prova", { tipo: "fattura", id: "sviluppo-0007" }));
  const s = await (await stato.fetch(new Request("https://casa.example/api/stato"))).json();

  assert.equal(r.status, 503);
  assert.deepEqual(s, { dal_vivo: false, esame_in_corso: false });
});

test("la decisione è spenta di base e non tocca né il motore né Evolus", async () => {
  finto(() => ({ dati: {} }));

  const r = await decisione.fetch(post("https://casa.example/api/decisione", { id_caso: "sportello-0123456789ab", decisione: "approvato" }));

  assert.equal(r.status, 503);
  assert.equal(chiamate.length, 0);
});

test("accesa, la decisione parte verso Evolus solo per un caso che il motore conosce e solo se è nuova", async () => {
  process.env.EVOLUS_ATTIVO = "1";
  const decisioni = { "sportello-0123456789ab": [{ decisione: "segnalato", nota: "" }] };
  finto((u) => {
    if (u.host === "evolus.example") return { stato: 202, dati: { id: "esecuzione-1" } };
    const id = u.pathname.split("/").at(-1);
    return id in decisioni ? { dati: { vista: {}, decisioni: decisioni[id] } } : { stato: 404, dati: {} };
  });
  const decidi = (id_caso, scelta) => decisione.fetch(post("https://casa.example/api/decisione", { id_caso, decisione: scelta }));

  const sconosciuto = await decidi("sportello-ffffffffffff", "approvato");
  const ripetuta = await decidi("sportello-0123456789ab", "segnalato");
  const nuova = await decidi("sportello-0123456789ab", "approvato");

  assert.equal(sconosciuto.status, 404);
  assert.deepEqual(await ripetuta.json(), { inviata: true, gia_registrata: true });
  assert.equal(nuova.status, 202);
  const aEvolus = chiamate.filter((c) => c.url.host === "evolus.example");
  assert.equal(aEvolus.length, 1);
  assert.equal(aEvolus[0].url.pathname, "/api/v1/workflows/wf-2/execute");
  assert.equal(aEvolus[0].opzioni.headers.Authorization, "Bearer chiave-evolus");
  assert.doesNotMatch(await nuova.text(), /chiave-evolus/);
});
