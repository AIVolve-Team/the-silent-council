// What the judges' site functions need. The keys live only in Vercel's environment variables: the browser never
// sees them.

export class HttpError extends Error {
  constructor(status, message) {
    super(message);
    this.status = status;
  }
}

export const json = (data, status = 200) =>
  Response.json(data, { status, headers: { "Cache-Control": "no-store" } });

/** The request body: a small JSON object, or a 400/413 error. */
export async function body(request, maximum = 4096) {
  const text = await request.text();
  if (text.length > maximum) throw new HttpError(413, "request too large");
  let data;
  try {
    data = JSON.parse(text);
  } catch {
    throw new HttpError(400, "a JSON object is required");
  }
  if (!data || typeof data !== "object" || Array.isArray(data)) throw new HttpError(400, "a JSON object is required");
  return data;
}

function call(base, secret, name, path, { method = "GET", data, seconds = 10 } = {}) {
  if (!base || !secret) throw new HttpError(503, `${name} not configured`);
  return fetch(new URL(path, base), {
    method,
    headers: { Authorization: `Bearer ${secret}`, ...(data ? { "Content-Type": "application/json" } : {}) },
    body: data ? JSON.stringify(data) : undefined,
    signal: AbortSignal.timeout(seconds * 1000),
  });
}

/** A call to the council's server on the MI300X, with its secret. */
export const council = (path, options) =>
  call(process.env.COUNCIL_URL, process.env.COUNCIL_SECRET, "council", path, options);

/** The function's handler: expected errors with their status, the others as 500 without details. */
export const handle = (method, fn) => async (request) => {
  try {
    if (request.method !== method) throw new HttpError(405, `${method} only`);
    return await fn(request);
  } catch (e) {
    if (e instanceof HttpError) return json({ error: e.message }, e.status);
    console.error(e);
    return json({ error: "internal error" }, 500);
  }
};
