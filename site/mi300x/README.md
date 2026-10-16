# site/mi300x — the MI300X in windows

Built as decided in "Where the app for the judges runs": the MI300X is born from a snapshot when needed and destroyed when not, **because even powered off it is billed**.
The live reviews on the judges' site only work while the machine is running; the recorded cases always work.

| File | What it does |
|---|---|
| `mi300x.sh` | account, status, create, destroy, snapshot, windows: the API calls, tested against a fake API |
| `../../.github/workflows/mi300x.yml` | every half hour: running inside the windows of `../windows.json`, destroyed outside |
| `../test/mi300x.test.mjs` | the tests, with a fake DigitalOcean API (`npm test` in `site/`) |

## What we know about AMD Developer Cloud

Research of 9/10 on the DigitalOcean and AMD pages; what no page confirms is to be tried on 12/10.

- **It is DigitalOcean:** console on devcloud.amd.com, same `/v2` API with a personal token ([DigitalOcean, AMD](https://docs.digitalocean.com/products/amd/), [creating a machine](https://docs.digitalocean.com/products/amd/how-to/create/)). The token is created from the AMD console, "API" entry. *To be tried:* whether the AMD token works on `api.digitalocean.com` or on `api.devcloud.amd.com` (`DO_API`): `mi300x.sh account` tells.
- **The machine:** `gpu-mi300x1-192gb`, only in the `atl1` region; a 720 GB boot disk, which goes into the snapshots, and a 5 TB scratch disk, which does **not** and is lost when the machine is destroyed ([details](https://docs.digitalocean.com/products/amd/details/features/), [scratch](https://docs.digitalocean.com/products/amd/how-to/use-scratch-disk/)). That is why models and code go on the boot disk.
- **Costs:** $2.59 an hour; **powered off it is billed all the same**, only destroyed it is not ([pricing](https://docs.digitalocean.com/products/amd/details/pricing/), [AMD FAQ](https://www.amd.com/en/developer/resources/cloud-access/amd-developer-cloud.html)). Snapshots cost $0.06 per GB per month and are not incremental.
- **Credits:** $100 per person, about 38 hours of MI300X. They are requested from the AMD page ("Member Perks" › "Request Cloud Credits"), arrive in **2-3 business days**, expire **30 days** after activation and need a registered card ([AMD, 22/6/2026](https://www.amd.com/en/developer/resources/technical-articles/2026/how-to-claim-amd-cloud-credits.html), [credits](https://docs.digitalocean.com/products/amd/details/credits/)). If the credit runs out without a card, AMD destroys the machine and its data.
- **An API trap:** the machine list hides the GPUs unless `type=gpus` is asked, and that filter does not combine with the tag ([droplets](https://docs.digitalocean.com/reference/api/reference/droplets/)). `mi300x.sh` lists the GPUs and filters the tag itself, destroys by id and then checks again: if one is still running, it exits with an error.

## Commands

```bash
export DIGITALOCEAN_ACCESS_TOKEN=…            # never in the repo
site/mi300x/mi300x.sh account                  # does the token work? how much has been spent?
site/mi300x/mi300x.sh status
MI300X_SSH=<fingerprint> site/mi300x/mi300x.sh create wait   # from the latest golden-* snapshot, with the timings
site/mi300x/mi300x.sh destroy
site/mi300x/mi300x.sh snapshot                 # powers off and snapshots the running machine (golden-YYYYMMDD-HHMM)
```

- **Create never starts two:** if one with the tag is already running, it stops there.
- **The machines started by hand** (tag `council-mi300x`) and **those of the windows** (tag `council-window`) are separate, so the automation never powers off a machine someone is working on, for example the eval in the night between 15 and 16/10. New machines are named `council-YYYYMMDD-HHMM`.
- **The legacy tags.** The old code tagged the machines with the name of the Help Desk: `sportello-mi300x` (by hand) and `sportello-finestra` (windows). Every command also sees the legacy tag that matches its own (`LEGACY_TAGS` in `mi300x.sh`), so `status` shows them and `destroy` destroys them: nothing started before the rename is left running and billed. New machines only get the new tag.
- `create wait` prints how many seconds it takes to be active and, with `MI300X_HEALTH=https://<engine>/health`, to have the engine ready: it is the **boot time from a snapshot** that G1 asks for.

## On 12/10: the golden machine

1. **Prepare a machine** as in the G1 runbook (`g1/README.md`), with models and code on the **boot disk**.
2. **The services restart on their own** when a machine is born from the snapshot: containers with `--restart unless-stopped`.
   - vLLM as in step 5 of the G1 runbook, on port 8000;
   - the council server (`council/service`, `--live`) on port **8001**, because 8000 belongs to vLLM;
   - Caddy in front, for TLS: `council.<domain>` → `127.0.0.1:8001`, `vllm.<domain>` → `127.0.0.1:8000`.
   - The secrets (`COUNCIL_SECRET`, `VLLM_API_KEY`) in a file on the boot disk with permissions 600, read by the containers with `--env-file`.
3. **Before the snapshot Caddy must already have its certificate.** Let's Encrypt gives at most 5 certificates a week for the same name: if every new machine asked for one, from the sixth day the engine would be left without TLS. With the certificate in the snapshot, new machines reuse it (it lasts 90 days).
4. **The snapshot:** `mi300x.sh snapshot`. It takes about **1-3 minutes per GB used**, and meanwhile the machine is billed: with about 130 GB of models, image and code, from 2 to 6 hours. Better to launch it at the end of the day and then destroy the machine.
5. **The boot time** is measured the next morning with `create wait` and written down, next to the time to download the models again from scratch onto the scratch disk, to pick the faster one.

## The engine's name

Every new machine has a new IP, while Evolus and Vercel need a fixed name.
If the domain is in DigitalOcean's DNS, with `MI300X_DNS_DOMAIN` and `MI300X_DNS_NAME` the script points the A record at the new IP (TTL 60 s).
With a domain elsewhere it is enough to delegate a subdomain to DigitalOcean, for example `mi300x.<domain>`. Which domain to use is a team choice, still open.

## The windows

- `../windows.json` is the same file the home page reads: `[{"start": "2026-10-19T09:00:00+02:00", "end": "2026-10-19T19:00:00+02:00"}, …]`.
- The days are set on 12/10, when we know what the organisers provide and until when.
- **The workflow** runs every half hour, at :13 and :43, only from the main branch. It starts the machine 45 minutes before a window and destroys it at the end; if GitHub skips a run, the next one puts things right.
  - Repo secrets: `DIGITALOCEAN_ACCESS_TOKEN`, `MI300X_SSH`.
  - Optional variables: `DO_API`, `MI300X_DNS_DOMAIN`, `MI300X_DNS_NAME`.
- **By hand**, from "Actions" › "MI300X in windows" › "Run workflow": `status`, `create`, `destroy`, and `destroy-all`, which also powers off the machines started by hand.

## Other variables of `mi300x.sh`

`MI300X_TAG` (overrides the tag), `MI300X_CLOUD_INIT` (a cloud-init file passed at birth), `MI300X_POLL` (seconds between two checks, 15), `MI300X_LEAD` (minutes ahead of a window, 45), `MI300X_RETRIES` (retries of a failed read, 3).
