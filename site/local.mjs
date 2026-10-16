// Local trial of the site: serves public/ and the functions of api/ as Vercel serves them, without the Vercel CLI.
//   COUNCIL_URL=http://127.0.0.1:8001 COUNCIL_SECRET=… node local.mjs      → http://localhost:3000
// It does not go to Vercel (.vercelignore).
import { createServer } from "node:http";
import { readFile, stat } from "node:fs/promises";
import { extname, join, normalize, resolve } from "node:path";

import council from "./api/council.mjs";
import status from "./api/status.mjs";

const PUBLIC = resolve("public");
const FUNCTIONS = { "/api/status": status, "/api/council": council };
const TYPES = { ".html": "text/html; charset=utf-8", ".json": "application/json", ".pdf": "application/pdf", ".zip": "application/zip" };

createServer(async (req, res) => {
  const url = new URL(req.url, "http://localhost");
  const fn = FUNCTIONS[url.pathname];
  if (fn) {
    const chunks = [];
    for await (const c of req) chunks.push(c);
    const body = req.method === "GET" || req.method === "HEAD" ? undefined : Buffer.concat(chunks);
    const response = await fn.fetch(new Request(url, { method: req.method, headers: req.headers, body }));
    res.writeHead(response.status, Object.fromEntries(response.headers));
    res.end(Buffer.from(await response.arrayBuffer()));
    return;
  }
  let file = join(PUBLIC, normalize(decodeURIComponent(url.pathname)));
  if (!file.startsWith(PUBLIC)) return res.writeHead(403).end();
  try {
    if ((await stat(file)).isDirectory()) file = join(file, "index.html");
    res.writeHead(200, { "Content-Type": TYPES[extname(file)] || "application/octet-stream" });
    res.end(await readFile(file));
  } catch {
    res.writeHead(404).end("not found");
  }
}).listen(Number(process.env.PORT || 3000), () => console.log(`site on http://localhost:${process.env.PORT || 3000}`));
