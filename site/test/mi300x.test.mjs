// The MI300X in windows: mi300x.sh against a fake DigitalOcean API, with no real tokens or machines.
// The fake API behaves like the real one where it matters: without type=gpus the list hides the GPUs, a freshly
// created machine becomes active with its IP, the snapshot finishes after a few checks.
import assert from "node:assert/strict";
import { execFile } from "node:child_process";
import { mkdtempSync, writeFileSync } from "node:fs";
import { createServer } from "node:http";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { test } from "node:test";
import { fileURLToPath } from "node:url";

const SCRIPT = fileURLToPath(new URL("../mi300x/mi300x.sh", import.meta.url));

function fakeApi({ brokenList = false, neverDeleted = false, running = [] } = {}) {
  const s = {
    droplets: running.map((tags, i) => ({ id: 900 + i, name: `by-hand-${i}`, status: "active", tags, networks: { v4: [] } })),
    snapshots: [
      { id: "111", name: "golden-20261012-1800", created_at: "2026-10-12T18:00:00Z" },
      { id: "222", name: "golden-20261013-1800", created_at: "2026-10-13T18:00:00Z" },
      { id: "333", name: "another-one", created_at: "2026-10-14T00:00:00Z" },
    ],
    creations: [], deleted: [], actions: {}, records: [], requests: [],
  }; // prettier-ignore
  let next = 1000;
  const server = createServer(async (req, res) => {
    const url = new URL(req.url, "http://api");
    let body = "";
    for await (const chunk of req) body += chunk;
    s.requests.push(`${req.method} ${url.pathname}`);
    const reply = (code, data) => {
      res.writeHead(code, { "content-type": "application/json" });
      res.end(data === undefined ? "" : JSON.stringify(data));
    };
    if (req.headers.authorization !== "Bearer fake") return reply(401, { id: "Unauthorized" });
    const p = url.pathname;
    let m;
    if (req.method === "GET" && p === "/v2/account") return reply(200, { account: { email: "team@example.org", status: "active" } });
    if (req.method === "GET" && p === "/v2/droplets") {
      if (brokenList) return reply(500, { id: "server_error" });
      return reply(200, { droplets: url.searchParams.get("type") === "gpus" ? s.droplets : [] });
    }
    if (req.method === "POST" && p === "/v2/droplets") {
      const c = JSON.parse(body);
      s.creations.push(c);
      s.droplets.push({ id: next, name: c.name, status: "new", tags: c.tags, networks: { v4: [] } });
      return reply(202, { droplet: { id: next++ } });
    }
    if ((m = p.match(/^\/v2\/droplets\/(\d+)$/))) {
      const d = s.droplets.find((x) => x.id === Number(m[1]));
      if (!d) return reply(404, { id: "not_found" });
      if (req.method === "DELETE") {
        s.deleted.push(d.id);
        if (!neverDeleted) s.droplets = s.droplets.filter((x) => x !== d);
        return reply(204);
      }
      if (d.status === "new") {
        d.status = "active";
        d.networks.v4 = [{ type: "private", ip_address: "10.0.0.5" }, { type: "public", ip_address: "203.0.113.7" }];
      }
      return reply(200, { droplet: d });
    }
    if (req.method === "GET" && p === "/v2/snapshots") return reply(200, { snapshots: s.snapshots });
    if (req.method === "POST" && (m = p.match(/^\/v2\/droplets\/(\d+)\/actions$/))) {
      const a = JSON.parse(body);
      if (a.type === "shutdown") s.droplets.find((x) => x.id === Number(m[1])).status = "off";
      s.actions[next] = { ...a, reads: 0 };
      return reply(201, { action: { id: next++, status: "in-progress" } });
    }
    if ((m = p.match(/^\/v2\/actions\/(\d+)$/))) {
      const a = s.actions[m[1]];
      a.reads += 1;
      return reply(200, { action: { id: Number(m[1]), status: a.reads >= 3 ? "completed" : "in-progress" } });
    }
    if (p === "/v2/domains/example.org/records") {
      if (req.method === "GET") return reply(200, { domain_records: s.records });
      s.records.push({ id: 7, ...JSON.parse(body) });
      return reply(201, {});
    }
    if (req.method === "PUT" && p === "/v2/domains/example.org/records/7") {
      Object.assign(s.records[0], JSON.parse(body));
      return reply(200, {});
    }
    reply(404, { id: "not_found" });
  });
  return { server, s };
}

async function withApi(options, check) {
  const { server, s } = fakeApi(options);
  await new Promise((done) => server.listen(0, "127.0.0.1", done));
  const environment = {
    PATH: process.env.PATH, DIGITALOCEAN_ACCESS_TOKEN: "fake", DO_API: `http://127.0.0.1:${server.address().port}`,
    MI300X_POLL: "0", MI300X_RETRIES: "0", MI300X_SSH: "aa:bb:cc",
  }; // prettier-ignore
  const run = (args, extra = {}) =>
    new Promise((done) =>
      execFile("bash", [SCRIPT, ...args], { env: { ...environment, ...extra } }, (error, stdout, stderr) =>
        done({ code: error ? error.code : 0, stdout, stderr }),
      ),
    );
  try {
    await check(run, s);
  } finally {
    server.close();
  }
}

test("creates from the latest golden snapshot, waits for the IP and does not create a second one", () =>
  withApi({}, async (run, s) => {
    const first = await run(["create", "wait"]);
    assert.equal(first.code, 0, first.stderr);
    assert.deepEqual(s.creations.map(({ image, size, region, tags, ssh_keys }) => ({ image, size, region, tags, ssh_keys })), [
      { image: 222, size: "gpu-mi300x1-192gb", region: "atl1", tags: ["council-mi300x"], ssh_keys: ["aa:bb:cc"] },
    ]); // the snapshot id goes as a number
    assert.match(s.creations[0].name, /^council-\d{8}-\d{4}$/);
    assert.match(first.stdout, /IP 203\.0\.113\.7/);
    const second = await run(["create"]);
    assert.equal(second.code, 0);
    assert.match(second.stdout, /already running/);
    assert.equal(s.creations.length, 1);
  }));

test("if the list does not answer it creates nothing", () =>
  withApi({ brokenList: true }, async (run, s) => {
    const r = await run(["create"]);
    assert.notEqual(r.code, 0);
    assert.ok(!s.requests.includes("POST /v2/droplets"));
  }));

test("destroys by id the machines with the tag, and exits with an error if one stays running", async () => {
  await withApi({ running: [["council-mi300x"], ["other-project"]] }, async (run, s) => {
    const r = await run(["destroy"]);
    assert.equal(r.code, 0, r.stderr);
    assert.deepEqual(s.deleted, [900]); // the one of another project is not touched
  });
  await withApi({ running: [["council-mi300x"]], neverDeleted: true }, async (run) => {
    const r = await run(["destroy"]);
    assert.equal(r.code, 1);
    assert.match(r.stderr, /still running/);
  });
});

test("machines with the legacy tags of the old code are seen and destroyed, each with its own new tag", async () => {
  const machines = [["sportello-mi300x"], ["sportello-finestra"], ["council-window"], ["other-project"]];
  await withApi({ running: machines }, async (run, s) => {
    const status = await run(["status"]);
    assert.equal(status.code, 0, status.stderr);
    assert.match(status.stdout, /^900 by-hand-0 active/m);
    assert.doesNotMatch(status.stdout, /by-hand-[123]/);
    const created = await run(["create"]);
    assert.match(created.stdout, /already running/); // no second machine next to an old one
    assert.equal(s.creations.length, 0);
    const r = await run(["destroy"]);
    assert.equal(r.code, 0, r.stderr);
    assert.deepEqual(s.deleted, [900]);
  });
  await withApi({ running: machines }, async (run, s) => {
    const r = await run(["destroy"], { MI300X_TAG: "council-window" });
    assert.equal(r.code, 0, r.stderr);
    assert.deepEqual(s.deleted, [901, 902]); // the hand-started machines stay
  });
});

test("the snapshot powers the machine off first and waits for the end", () =>
  withApi({ running: [["council-mi300x"]] }, async (run, s) => {
    const r = await run(["snapshot"]);
    assert.equal(r.code, 0, r.stderr);
    assert.deepEqual(
      Object.values(s.actions).map((a) => a.type),
      ["shutdown", "snapshot"],
    );
    assert.match(Object.values(s.actions)[1].name, /^golden-\d{8}-\d{4}$/);
    assert.match(r.stdout, /must be destroyed/);
  }));

test("windows: inside it starts, outside it destroys only the windows machine", async () => {
  const folder = mkdtempSync(join(tmpdir(), "windows-"));
  const now = Date.now();
  const iso = (ms) => new Date(ms).toISOString().replace(/\.\d{3}Z$/, "+00:00");
  const inside = join(folder, "inside.json");
  writeFileSync(inside, JSON.stringify([{ start: iso(now + 30 * 60e3), end: iso(now + 5 * 3600e3) }])); // in 30 minutes
  const outside = join(folder, "outside.json");
  writeFileSync(outside, JSON.stringify([{ start: iso(now - 5 * 3600e3), end: iso(now - 3600e3) }]));
  await withApi({}, async (run, s) => {
    const r = await run(["windows", inside]);
    assert.equal(r.code, 0, r.stderr);
    assert.deepEqual(s.creations[0].tags, ["council-window"]);
  });
  await withApi({ running: [["council-window"], ["council-mi300x"], ["sportello-finestra"]] }, async (run, s) => {
    const r = await run(["windows", outside]);
    assert.equal(r.code, 0, r.stderr);
    assert.deepEqual(s.deleted, [900, 902]); // the machine started by hand to work on stays
  });
});

test("with the domain in DigitalOcean's DNS the name points at the new IP", () =>
  withApi({}, async (run, s) => {
    const dns = { MI300X_DNS_DOMAIN: "example.org", MI300X_DNS_NAME: "engine" };
    const r = await run(["create", "wait"], dns);
    assert.equal(r.code, 0, r.stderr);
    assert.deepEqual(s.records, [{ id: 7, type: "A", name: "engine", data: "203.0.113.7", ttl: 60 }]);
  }));
