# Vercel + Render deployment

Deploy the `codex/leancode` branch. The source configuration is ready; a successful local check is not a claim that cloud resources are live.

| Component | Host | Configuration |
| --- | --- | --- |
| React frontend | Vercel | Root directory `frontend`, Vite, `npm run build`, output `dist` |
| FastAPI API + SQLite + registered repositories | Render web service | One instance, one worker, persistent disk `/var/data` |
| Bifrost | Render private service | Official pinned v2.4.0 image plus public configuration; provider secrets supplied at runtime |
| Approved commands | Render Sandboxes | Fresh microVM from a clean Docker snapshot; deny-all egress, then the existing read-only, non-root Docker test container |

The planned backend and gateway each use `0.5c-512mb` compute. At the published $7/month each plus $0.25 for a 1 GB disk, the baseline is about **$14.25/month**, excluding sandbox compute, snapshots, model/search usage, and usage overages. Confirm the actual Blueprint plan and [Render pricing](https://render.com/pricing) before provisioning. Free Render services cannot persist this SQLite spending ledger. Never reset spending reservations just to continue a demo.

## 1. Prepare cloud tests

Add `RENDER_API_KEY` and `RENDER_WORKSPACE_ID` to your private root `.env`. Install with `uv sync --extra cloud --extra dev`.

After approving the compute expenditure, run:

```sh
.venv/bin/python scripts/setup_render_sandbox.py
```

This creates a temporary sandbox containing only the trusted `Dockerfile.sandbox`, builds its Python image, saves a clean runtime snapshot, and terminates the bootstrap sandbox. It writes snapshot/group IDs to `.env` and expiration metadata to `.leancode/render-sandbox.json`. No repository or model credentials are uploaded. Confirm the expiration and renew the snapshot before it expires.

The bootstrap can access the network to pull the trusted base image. Every actual command sandbox explicitly uses `deny-all` networking and `--pull=never`. If the cached image or policy is unavailable, execution blocks. There is no host-process fallback. Each command sandbox is terminated in `finally` and has a 180-second runtime limit; Docker command execution retains its 60-second timeout and 32 KB output limit. Infrastructure charges are separate from the model/search ledger.

Confidential repositories cannot use cloud execution, even when a local model exists. The hosted confidential fixture demonstrates a block; offline completion still requires your local deployment.

## 2. Review the Render Blueprint

Create a Blueprint from the repository's `render.yaml` on `codex/leancode`. Preview and review its two new services and disk before approving. Existing services should remain unchanged. Blueprint auto-sync and service auto-deploys should remain disabled until the first deployment is verified.

Supply the requested private runtime values:

- Gateway: `GEMINI_API_KEY`.
- API: `TAVILY_API_KEY`, `RENDER_API_KEY`, `RENDER_WORKSPACE_ID`, the prepared snapshot and group IDs, and `LEANCODE_BROWSER_ORIGINS` as an exact JSON list of approved HTTPS frontend origins.

Render generates the API access token, gateway virtual key, dashboard password, and setup token. The API receives the gateway's internal address and virtual key by service reference. Bifrost is private; do not expose its admin dashboard publicly. Content logging and retries are disabled. The conservative search bound is $0.008 per request; model rates match the verified local Gemini route and must be rechecked when changing models.

The API generates only synthetic demo workspaces, once, under the persistent disk. Redeployment never replaces existing workspace files. SQLite stores sessions, approvals, costs and reservations on that same disk. Keep a single process/instance: startup recovery is not designed for multiple concurrent API workers. Take backups of the entire data directory with the API stopped; do not copy only the SQLite main file during writes.

## 3. Connect Vercel

Import this GitHub repository into Vercel with **Root Directory `frontend`** and branch `codex/leancode`. Use `frontend/vercel.json`. Set the public build variable `VITE_API_URL` to the actual Render API origin, for example `https://your-api.onrender.com`, with no `/api` suffix. Redeploy after changing it.

Add the actual stable Vercel production origin to the Render `LEANCODE_BROWSER_ORIGINS` JSON list. Allow additional preview origins individually only when needed. CORS permits authenticated GET/POST requests and authorization preflights for those exact origins; unknown hosts/origins remain rejected. Model keys and access tokens never belong in Vercel build variables.

Open the frontend and enter the Render-generated `LEANCODE_TOKEN` into its password field. Retrieve that token privately from the API service's environment settings. Do not publish it in a URL, demo video, or repository.

## 4. Verify before sharing

1. Confirm the gateway deploy is healthy and the Render API `/api/health` returns 200 over HTTPS.
2. Confirm unauthenticated `/api/bootstrap` is 401 and unapproved browser origins are rejected. Connect from the actual frontend and verify live events.
3. Run a synthetic public task, review the exact patch, approve its exact unittest command, and confirm real test output before the session reaches completed. This spends configured provider and sandbox credit.
4. Verify cloud sandbox isolation with synthetic files: no `.env` uploaded, non-root Docker user, no outbound network, read-only workspace, no provider keys. Hosted execution is not considered verified until these checks pass in Render itself.
5. Restart the API and confirm session history, workspace edits and the spending ledger persist. Do not delete or recreate the disk.

Local verification:

```sh
uv sync --extra dev --extra cloud
.venv/bin/python -m unittest discover -s backend/tests -v
LEANCODE_TEST_DOCKER=1 .venv/bin/python -m unittest discover -s backend/tests -p test_sandbox.py -v
npm --prefix frontend run build
```

Render SDK contract tests use mocks and do not prove that a live cloud sandbox works. See the official [sandbox lifecycle and networking docs](https://render.com/docs/sandboxes-creating) and [persistent disk requirements](https://render.com/docs/disks).
