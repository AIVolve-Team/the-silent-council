# site — the link for the judges

Built as decided in "Where the judges' app runs".
An **always-on** showcase on Vercel for the **Silent Council**: the verdicts recorded on the MI300X always work, the live reviews when the MI300X is on.
The Help Desk was removed from the repo on 13/10: it is excluded from the hackathon, and stays in the git history and in the tag `archivio/sportello`.

| File | What it does |
|---|---|
| `src/index.html` | the home page: the demonstration at the top (the same agents writing to each other and handing over their memory, with the counters of `<project>/numbers.json`), the projects, "live now" or the next window, how to check a case |
| `src/council/live.html` | the council's live review: the judge picks a CUAD contract from the server's list and has it reviewed now; the reviews stay in their browser, and each one opens as a verdict (`verdict.html?live=<case_id>`) |
| `api/status.mjs` | is the MI300X on? (asks the council's server for `/health`) |
| `api/council.mjs` | the council's live review: the list of contracts and a review, to the council's server with its key; 409 if busy |
| `lib/common.mjs` | responses, request body, call to the council's server |
| `windows.json` | the live windows after 18/10, `[{"start": "<ISO time>", "end": "<ISO time>"}, …]`, to be set on 12/10 |
| `build.py` | writes `public/`: the home page and the council's pages |
| `local.mjs` | serves `public/` and the functions locally, without the Vercel CLI |
| `mi300x/` | the MI300X in windows: it is born from a snapshot when needed and destroyed when not (README there) |
| `test/` | the tests of the functions, with a fake council server, and of `mi300x/` with a fake DigitalOcean API |

## Build and publish

```bash
# from the repo root: Python 3 is enough, without dependencies
python3 site/build.py --council <verdict pages> [--repo https://github.com/…]
cd site && vercel deploy --prod                # the CLI: the free plan does not link an organization's repos
```

`<verdict pages>` is the output folder of `python -m review.showcase` (`council/review`). `build.py` writes
`public/projects.json` (`{"projects": [{id, name, en, it, cases, live, numbers}], "repo"}`) and copies `windows.json`.

- **No whole IBAN** leaves the PDFs: `build.py` checks every HTML and JSON file of `public/` and stops if it finds one.
- **The judges' choices stay in their browser**.

## Environment variables on Vercel

| Variable | For | Notes |
|---|---|---|
| `COUNCIL_URL` | status, the council's live review | the public address of the council's server, with TLS, started with `--live` |
| `COUNCIL_SECRET` | status, the council's live review | the same `COUNCIL_SECRET` as the server |

The keys live only here: the browser never sees them, and no function sends them back (the tests check it).

## The functions

| Path | Method | Request | Response |
|---|---|---|---|
| `/api/status` | GET | | `{"council": {"live": bool, "busy": bool}}` |
| `/api/council` | GET | | the server's `/live/contracts`: `[{key, title, benchmark, subset}]` |
| `/api/council` | POST | `{"contract": "<benchmark>:<id>", "mode": "telepathy" \| "text"}` | the server's `/live/contract` response; 409 busy, 503 off |

Errors are `{"error": "…"}`.

## Live reviews

The council's server starts with `--live` (see `council/service`): the judge picks a contract from the server's list, never a text of their own, and has it reviewed now. One review at a time: if the council is busy, 409.

## Try it locally

```bash
python3 site/build.py --council <verdict pages>
cd site && COUNCIL_URL=http://127.0.0.1:8001 COUNCIL_SECRET=$COUNCIL_SECRET node local.mjs    # http://localhost:3000
npm test                                                                                       # the functions
```

## What is missing

- **The windows after 18/10** (`windows.json`) and **the MI300X born from a snapshot in the morning and destroyed in the evening** (`mi300x/mi300x.sh windows windows.json`): decided on 12/10, when we know what the organisers provide.
- **The verdicts recorded** on the MI300X, by 17/10.
- **Publishing on Vercel** (the team's account and project).
