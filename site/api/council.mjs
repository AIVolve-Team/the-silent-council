// The council's live reviews: the judge picks a contract from the server's list, never a text of their own.
// GET gives the list, POST has it reviewed now. One review at a time: if the council is busy the server answers 409
// and the page says to try again in a minute.
import { HttpError, body, council, json } from "../lib/common.mjs";

const MODES = ["telepathy", "text"];

async function forward(path, options) {
  let r;
  try {
    r = await council(path, options);
  } catch (e) {
    if (e instanceof HttpError) throw e;
    throw new HttpError(503, "the council is off or does not answer");
  }
  if (r.status === 401) {
    console.error("the council rejects the site's secret");
    throw new HttpError(502, "the site is not authorised by the council");
  }
  if (r.status === 404) throw new HttpError(503, "the council's live reviews are off");
  const data = await r.json().catch(() => ({ error: "invalid response from the council" }));
  return json(data, [200, 400, 409].includes(r.status) ? r.status : 502);
}

export default {
  async fetch(request) {
    try {
      if (request.method === "GET") return await forward("/live/contracts", { seconds: 10 });
      if (request.method !== "POST") throw new HttpError(405, "GET or POST only");
      const data = await body(request);
      const extra = Object.keys(data).filter((k) => !["contract", "mode"].includes(k));
      if (extra.length) throw new HttpError(400, `unexpected fields: ${extra.join(", ")}`);
      if (typeof data.contract !== "string" || !data.contract || data.contract.length > 300) throw new HttpError(400, "contract: the key of a contract in the list");
      const mode = data.mode ?? "telepathy";
      if (!MODES.includes(mode)) throw new HttpError(400, "mode: telepathy or text");
      return await forward("/live/contract", { method: "POST", data: { contract: data.contract, mode }, seconds: 290 });
    } catch (e) {
      if (e instanceof HttpError) return json({ error: e.message }, e.status);
      console.error(e);
      return json({ error: "internal error" }, 500);
    }
  },
};
