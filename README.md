# LeanCode

A local coding agent that measures token use, reviews changes before execution, and keeps confidential code local.

Stack: React + TypeScript + Vite + Tailwind CSS; Python + FastAPI; SQLite; Bifrost; Ollama; Tavily; Docker.

The Workbench uses the supplied Cue Minimal AI Dev Workspace design with live agent sessions and exact action approvals. See the [frontend component and integration guide](frontend/README.md).

For Vercel frontend + Render backend deployment, see the [deployment guide](docs/DEPLOYMENT.md) and `render.yaml`. Cloud command execution uses managed Render Sandboxes; it never runs approved repository commands inside the API process.

## Development

Requires Python 3.11+, Node 22+, and Docker for agent execution.

```sh
uv sync --extra dev
cp .env.example .env
uv run uvicorn leancode.api:create_app --factory --host 127.0.0.1 --port 8000
```

In another terminal:

```sh
cd frontend
npm ci
npm run dev
```

Open http://127.0.0.1:5173. The backend generates a local access token in `.leancode/access-token` unless `LEANCODE_TOKEN` is set. No API keys are sent to the frontend.

## Checks

```sh
uv run python -m unittest discover -s backend/tests -v
cd frontend
npm run build
```

## Milestones

- [x] 1. Foundation: web/backend scaffolding, persisted store, environment configuration
- [x] 2. Task dashboard
- [x] 3. Backend sessions and live events
- [x] 4. Safe coding-agent execution (real-provider validation pending configuration)
- [x] 5. Reliability, budgets, privacy (fault-injection tests; live failover pending configuration)
- [x] 6. Token efficiency (context reduction checked; live token savings not yet measured)
- [x] 7. Benchmark fixtures and runner (live results pending model configuration)
- [x] 8. Browser verification, setup instructions, and demo guide
- [ ] Live provider validation, measured savings, and final hackathon submission

Integration availability and real-provider completion are tracked separately from implementation. No savings results are claimed before measurement. See [IMPLEMENTATION_PLAN.md](IMPLEMENTATION_PLAN.md).

See [setup and model configuration](docs/SETUP.md), [benchmark instructions](benchmarks/README.md), and the [demo guide and remaining validation](docs/DEMO.md).
