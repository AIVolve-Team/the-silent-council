// The site's functions with a fake council server in place of fetch.
import assert from "node:assert/strict";
import { afterEach, beforeEach, test } from "node:test";

import council from "../api/council.mjs";
import status from "../api/status.mjs";

const realFetch = globalThis.fetch;
let calls;

function fake(responses) {
  calls = [];
  globalThis.fetch = async (url, options = {}) => {
    const u = new URL(url);
    calls.push({ url: u, options });
    const r = responses(u, options);
    if (r instanceof Error) throw r;
    return Response.json(r.data ?? {}, { status: r.status ?? 200 });
  };
}

const post = (url, data) => new Request(url, { method: "POST", body: JSON.stringify(data) });

beforeEach(() => {
  process.env.COUNCIL_URL = "https://council.example";
  process.env.COUNCIL_SECRET = "council-secret";
});
afterEach(() => {
  globalThis.fetch = realFetch;
});

test("the council's live review carries only the contract key, with the council's secret", async () => {
  fake((u) => (u.pathname === "/live/contracts" ? { data: [{ key: "cuad:X", title: "X" }] } : { status: 409, data: { error: "try again in a minute" } }));

  const listing = await council.fetch(new Request("https://site.example/api/council"));
  const busy = await council.fetch(post("https://site.example/api/council", { contract: "cuad:X" }));

  assert.deepEqual(await listing.json(), [{ key: "cuad:X", title: "X" }]);
  assert.equal(busy.status, 409);
  assert.equal(calls[1].url.href, "https://council.example/live/contract");
  assert.equal(calls[1].options.headers.Authorization, "Bearer council-secret");
  assert.deepEqual(JSON.parse(calls[1].options.body), { contract: "cuad:X", mode: "telepathy" });
  assert.doesNotMatch(await busy.text(), /council-secret/);
});

test("a text instead of the contract, or an unknown mode, does not reach the council", async () => {
  fake(() => ({ data: {} }));

  const text = await council.fetch(post("https://site.example/api/council", { contract: "cuad:X", text: "my contract" }));
  const mode = await council.fetch(post("https://site.example/api/council", { contract: "cuad:X", mode: "shout" }));
  const empty = await council.fetch(post("https://site.example/api/council", {}));

  assert.deepEqual([text.status, mode.status, empty.status], [400, 400, 400]);
  assert.equal(calls.length, 0);
});

test("with the council off the live review is a 503, and the status says it is not live", async () => {
  fake(() => new TypeError("fetch failed"));

  const r = await council.fetch(post("https://site.example/api/council", { contract: "cuad:X" }));
  const s = await (await status.fetch(new Request("https://site.example/api/status"))).json();

  assert.equal(r.status, 503);
  assert.deepEqual(s, { council: { live: false, busy: false } });
});

test("with the council on the status says live, and busy if a review is in progress", async () => {
  fake(() => ({ data: { live: true, review_in_progress: true } }));

  const s = await (await status.fetch(new Request("https://site.example/api/status"))).json();

  assert.deepEqual(s, { council: { live: true, busy: true } });
  assert.equal(calls[0].url.href, "https://council.example/health");
});
