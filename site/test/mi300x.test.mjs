// La MI300X a finestre: mi300x.sh contro un'API di DigitalOcean finta, senza token veri né macchine vere.
// L'API finta fa come quella vera dove conta: senza type=gpus l'elenco nasconde le GPU, la macchina appena creata
// diventa attiva con il suo IP, lo snapshot finisce dopo qualche controllo.
import assert from "node:assert/strict";
import { execFile } from "node:child_process";
import { mkdtempSync, writeFileSync } from "node:fs";
import { createServer } from "node:http";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { test } from "node:test";
import { fileURLToPath } from "node:url";

const SCRIPT = fileURLToPath(new URL("../mi300x/mi300x.sh", import.meta.url));

function apiFinta({ elencoRotto = false, nonSiCancella = false, accese = [] } = {}) {
  const s = {
    droplets: accese.map((tags, i) => ({ id: 900 + i, name: `a-mano-${i}`, status: "active", tags, networks: { v4: [] } })),
    snapshots: [
      { id: "111", name: "golden-20261012-1800", created_at: "2026-10-12T18:00:00Z" },
      { id: "222", name: "golden-20261013-1800", created_at: "2026-10-13T18:00:00Z" },
      { id: "333", name: "un-altro", created_at: "2026-10-14T00:00:00Z" },
    ],
    creazioni: [], cancellate: [], azioni: {}, record: [], richieste: [],
  }; // prettier-ignore
  let prossimo = 1000;
  const server = createServer(async (req, res) => {
    const url = new URL(req.url, "http://api");
    let corpo = "";
    for await (const pezzo of req) corpo += pezzo;
    s.richieste.push(`${req.method} ${url.pathname}`);
    const rispondi = (codice, dati) => {
      res.writeHead(codice, { "content-type": "application/json" });
      res.end(dati === undefined ? "" : JSON.stringify(dati));
    };
    if (req.headers.authorization !== "Bearer finto") return rispondi(401, { id: "Unauthorized" });
    const p = url.pathname;
    let m;
    if (req.method === "GET" && p === "/v2/account") return rispondi(200, { account: { email: "team@example.org", status: "active" } });
    if (req.method === "GET" && p === "/v2/droplets") {
      if (elencoRotto) return rispondi(500, { id: "server_error" });
      return rispondi(200, { droplets: url.searchParams.get("type") === "gpus" ? s.droplets : [] });
    }
    if (req.method === "POST" && p === "/v2/droplets") {
      const c = JSON.parse(corpo);
      s.creazioni.push(c);
      s.droplets.push({ id: prossimo, name: c.name, status: "new", tags: c.tags, networks: { v4: [] } });
      return rispondi(202, { droplet: { id: prossimo++ } });
    }
    if ((m = p.match(/^\/v2\/droplets\/(\d+)$/))) {
      const d = s.droplets.find((x) => x.id === Number(m[1]));
      if (!d) return rispondi(404, { id: "not_found" });
      if (req.method === "DELETE") {
        s.cancellate.push(d.id);
        if (!nonSiCancella) s.droplets = s.droplets.filter((x) => x !== d);
        return rispondi(204);
      }
      if (d.status === "new") {
        d.status = "active";
        d.networks.v4 = [{ type: "private", ip_address: "10.0.0.5" }, { type: "public", ip_address: "203.0.113.7" }];
      }
      return rispondi(200, { droplet: d });
    }
    if (req.method === "GET" && p === "/v2/snapshots") return rispondi(200, { snapshots: s.snapshots });
    if (req.method === "POST" && (m = p.match(/^\/v2\/droplets\/(\d+)\/actions$/))) {
      const a = JSON.parse(corpo);
      if (a.type === "shutdown") s.droplets.find((x) => x.id === Number(m[1])).status = "off";
      s.azioni[prossimo] = { ...a, letture: 0 };
      return rispondi(201, { action: { id: prossimo++, status: "in-progress" } });
    }
    if ((m = p.match(/^\/v2\/actions\/(\d+)$/))) {
      const a = s.azioni[m[1]];
      a.letture += 1;
      return rispondi(200, { action: { id: Number(m[1]), status: a.letture >= 3 ? "completed" : "in-progress" } });
    }
    if (p === "/v2/domains/example.org/records") {
      if (req.method === "GET") return rispondi(200, { domain_records: s.record });
      s.record.push({ id: 7, ...JSON.parse(corpo) });
      return rispondi(201, {});
    }
    if (req.method === "PUT" && p === "/v2/domains/example.org/records/7") {
      Object.assign(s.record[0], JSON.parse(corpo));
      return rispondi(200, {});
    }
    rispondi(404, { id: "not_found" });
  });
  return { server, s };
}

async function conApi(opzioni, prova) {
  const { server, s } = apiFinta(opzioni);
  await new Promise((fatto) => server.listen(0, "127.0.0.1", fatto));
  const ambiente = {
    PATH: process.env.PATH, DIGITALOCEAN_ACCESS_TOKEN: "finto", DO_API: `http://127.0.0.1:${server.address().port}`,
    MI300X_ATTESA: "0", MI300X_RITENTA: "0", MI300X_SSH: "aa:bb:cc",
  }; // prettier-ignore
  const esegui = (argomenti, altro = {}) =>
    new Promise((fatto) =>
      execFile("bash", [SCRIPT, ...argomenti], { env: { ...ambiente, ...altro } }, (errore, stdout, stderr) =>
        fatto({ codice: errore ? errore.code : 0, stdout, stderr }),
      ),
    );
  try {
    await prova(esegui, s);
  } finally {
    server.close();
  }
}

test("crea dall'ultimo snapshot golden, aspetta l'IP e non ne crea una seconda", () =>
  conApi({}, async (esegui, s) => {
    const prima = await esegui(["crea", "aspetta"]);
    assert.equal(prima.codice, 0, prima.stderr);
    assert.deepEqual(s.creazioni.map(({ image, size, region, tags, ssh_keys }) => ({ image, size, region, tags, ssh_keys })), [
      { image: 222, size: "gpu-mi300x1-192gb", region: "atl1", tags: ["sportello-mi300x"], ssh_keys: ["aa:bb:cc"] },
    ]); // l'id dello snapshot va come numero
    assert.match(prima.stdout, /IP 203\.0\.113\.7/);
    const seconda = await esegui(["crea"]);
    assert.equal(seconda.codice, 0);
    assert.match(seconda.stdout, /già accesa/);
    assert.equal(s.creazioni.length, 1);
  }));

test("se l'elenco non risponde non crea niente", () =>
  conApi({ elencoRotto: true }, async (esegui, s) => {
    const r = await esegui(["crea"]);
    assert.notEqual(r.codice, 0);
    assert.ok(!s.richieste.includes("POST /v2/droplets"));
  }));

test("distrugge per id quelle con il tag, e se una resta accesa esce con un errore", async () => {
  await conApi({ accese: [["sportello-mi300x"], ["altro-progetto"]] }, async (esegui, s) => {
    const r = await esegui(["distruggi"]);
    assert.equal(r.codice, 0, r.stderr);
    assert.deepEqual(s.cancellate, [900]); // quella di un altro progetto non si tocca
  });
  await conApi({ accese: [["sportello-mi300x"]], nonSiCancella: true }, async (esegui) => {
    const r = await esegui(["distruggi"]);
    assert.equal(r.codice, 1);
    assert.match(r.stderr, /ancora accese/);
  });
});

test("lo snapshot spegne prima la macchina e aspetta la fine", () =>
  conApi({ accese: [["sportello-mi300x"]] }, async (esegui, s) => {
    const r = await esegui(["snapshot"]);
    assert.equal(r.codice, 0, r.stderr);
    assert.deepEqual(
      Object.values(s.azioni).map((a) => a.type),
      ["shutdown", "snapshot"],
    );
    assert.match(Object.values(s.azioni)[1].name, /^golden-\d{8}-\d{4}$/);
    assert.match(r.stdout, /va distrutta/);
  }));

test("finestre: dentro accende, fuori distrugge solo la macchina delle finestre", async () => {
  const cartella = mkdtempSync(join(tmpdir(), "finestre-"));
  const ora = Date.now();
  const iso = (ms) => new Date(ms).toISOString().replace(/\.\d{3}Z$/, "+00:00");
  const dentro = join(cartella, "dentro.json");
  writeFileSync(dentro, JSON.stringify([{ inizio: iso(ora + 30 * 60e3), fine: iso(ora + 5 * 3600e3) }])); // fra 30 minuti
  const fuori = join(cartella, "fuori.json");
  writeFileSync(fuori, JSON.stringify([{ inizio: iso(ora - 5 * 3600e3), fine: iso(ora - 3600e3) }]));
  await conApi({}, async (esegui, s) => {
    const r = await esegui(["finestre", dentro]);
    assert.equal(r.codice, 0, r.stderr);
    assert.deepEqual(s.creazioni[0].tags, ["sportello-finestra"]);
  });
  await conApi({ accese: [["sportello-finestra"], ["sportello-mi300x"]] }, async (esegui, s) => {
    const r = await esegui(["finestre", fuori]);
    assert.equal(r.codice, 0, r.stderr);
    assert.deepEqual(s.cancellate, [900]); // la macchina accesa a mano per lavorare resta
  });
});

test("con il dominio nel DNS di DigitalOcean il nome punta al nuovo IP", () =>
  conApi({}, async (esegui, s) => {
    const dns = { MI300X_DNS_DOMINIO: "example.org", MI300X_DNS_NOME: "motore" };
    const r = await esegui(["crea", "aspetta"], dns);
    assert.equal(r.codice, 0, r.stderr);
    assert.deepEqual(s.record, [{ id: 7, type: "A", name: "motore", data: "203.0.113.7", ttl: 60 }]);
  }));
