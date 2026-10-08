// Prova locale della casa: serve public/ e le funzioni di api/ come le serve Vercel, senza la CLI di Vercel.
//   MOTORE_URL=http://127.0.0.1:8765 MOTORE_SEGRETO=… node locale.mjs      → http://localhost:3000
// Non va su Vercel (.vercelignore).
import { createServer } from "node:http";
import { readFile, stat } from "node:fs/promises";
import { extname, join, normalize, resolve } from "node:path";

import decisione from "./api/decisione.mjs";
import prova from "./api/prova.mjs";
import stato from "./api/stato.mjs";

const PUBBLICA = resolve("public");
const FUNZIONI = { "/api/stato": stato, "/api/prova": prova, "/api/decisione": decisione };
const TIPI = { ".html": "text/html; charset=utf-8", ".json": "application/json", ".pdf": "application/pdf", ".zip": "application/zip" };

createServer(async (req, res) => {
  const url = new URL(req.url, "http://localhost");
  const funzione = FUNZIONI[url.pathname];
  if (funzione) {
    const pezzi = [];
    for await (const p of req) pezzi.push(p);
    const corpo = req.method === "GET" || req.method === "HEAD" ? undefined : Buffer.concat(pezzi);
    const risposta = await funzione.fetch(new Request(url, { method: req.method, headers: req.headers, body: corpo }));
    res.writeHead(risposta.status, Object.fromEntries(risposta.headers));
    res.end(Buffer.from(await risposta.arrayBuffer()));
    return;
  }
  let file = join(PUBBLICA, normalize(decodeURIComponent(url.pathname)));
  if (!file.startsWith(PUBBLICA)) return res.writeHead(403).end();
  try {
    if ((await stat(file)).isDirectory()) file = join(file, "index.html");
    res.writeHead(200, { "Content-Type": TIPI[extname(file)] || "application/octet-stream" });
    res.end(await readFile(file));
  } catch {
    res.writeHead(404).end("non trovato");
  }
}).listen(Number(process.env.PORT || 3000), () => console.log(`casa su http://localhost:${process.env.PORT || 3000}`));
