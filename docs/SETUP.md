# Configure a real run

## Start locally

```sh
uv sync --extra dev
cp .env.example .env
docker build -f Dockerfile.sandbox -t leancode-sandbox:local .
uv run uvicorn leancode.api:create_app --factory --host 127.0.0.1 --port 8000
```

In another terminal run `cd frontend`, `npm ci`, then `npm run dev`. Open http://127.0.0.1:5173 and enter the generated `.leancode/access-token`, or the token you configured in `.env`. Use one backend worker. This is a local application; do not expose its ports publicly.

The default registered repository is the small confidential boundary fixture. With no model routes configured, tasks safely block and retain their session. To work on another repository, edit `LEANCODE_REPOSITORIES` in your local `.env`, for example:

```dotenv
LEANCODE_REPOSITORIES={"my-project":{"path":"/absolute/path/to/project","confidential":true}}
```

Back up your work and review each patch. Existing edits are preserved through hash preconditions; avoid concurrent editing of a file while its patch is being applied. The MVP supports UTF-8 files, up to 500 eligible files and a 4 MB sanitized execution snapshot. Its Docker image includes Python's standard library, not arbitrary project dependencies.

## Public repositories: Bifrost

Follow the official [Bifrost setup](https://docs.getbifrost.ai/quickstart/gateway/setting-up) and configure two providers you have access to. Keep provider keys in the gateway environment, not in the frontend or repository.

Set `BIFROST_URL` to its OpenAI-compatible endpoint and `BIFROST_KEY` if it requires authentication. Configure explicit provider-qualified model names, a single provider key per route, no automatic gateway routing overrides or fallbacks, and `network_config.max_retries=0`. LeanCode handles the bounded fallback sequence itself so it can reserve spending before each attempt. See [Bifrost retry behavior](https://docs.getbifrost.ai/features/retries-and-fallbacks).

Set `LEANCODE_GATEWAY_SINGLE_ATTEMPT=true` only after verifying those settings. Add at most three ordered routes to `LEANCODE_ROUTES`. Each cloud route needs these fields:

```json
{
  "name": "primary",
  "model": "provider/exact-model-id",
  "local": false,
  "primary": true,
  "tier": "strong",
  "bounded_output": true,
  "input_rate": null,
  "output_rate": null
}
```

Replace both nulls with verified non-negative integer rates in USD microdollars per million tokens. For example, $1 per million tokens is `1000000` in these units. Null or missing prices block requests. Verify that the model honors `max_tokens=2048` as a cap on all billed output, including reasoning, before setting `bounded_output=true`; unsupported models must remain disabled. The connector requires JSON responses and standard reported input/output usage.

An optional cheap route uses `primary:false` and `tier:small`. Baseline/context experiments use primary routes; optimized runs prefer small routes and escalate toward strong routes after test failures. Cloud routes only work for repositories explicitly marked `confidential:false`. Restart the backend after changing trusted configuration.

## Confidential repositories: local inference

Install a local model that fits your hardware and supports structured JSON responses. Ollama's [OpenAI-compatible API](https://docs.ollama.com/api/openai-compatibility) is supported. Use a literal loopback endpoint such as `http://127.0.0.1:11434/v1` and a local model ID without cloud features.

Disable cloud functionality with `OLLAMA_NO_CLOUD=1`, as documented in [Ollama's local FAQ](https://docs.ollama.com/faq), and enforce outbound-network isolation at the process/container/firewall layer. Pre-download model weights before isolating networking. Disable external tracing and content logging. Set an adequate context window and verify operation offline on synthetic code first.

Only then set `LEANCODE_LOCAL_OFFLINE=true` and configure a route such as:

```dotenv
LEANCODE_ROUTES=[{"name":"local-coder","model":"YOUR-INSTALLED-LOCAL-MODEL","url":"http://127.0.0.1:11434/v1","local":true,"input_rate":0,"output_rate":0}]
```

The flag is an operator confirmation, not automatic proof of local-model network isolation. Loopback routing alone cannot stop a misconfigured model server from contacting external services. Never enable confidential processing until isolation is actually verified. If no allowed local route exists, the session blocks; it never falls back to cloud. Tavily is disabled for confidential sessions.

## Tavily

Set `TAVILY_API_KEY` and a verified conservative positive `TAVILY_SEARCH_COST_MICRO` for one basic search. Keys stay in the backend. The agent can request only the fixed public topic `python-unittest`; it cannot send arbitrary repository content as a search query. Searches are restricted to configured documentation domains and two bounded results. Search costs use the configured upper-bound price rather than claiming exact invoice reconciliation. Public results are cached in process memory.

## Users, budgets, and unknown billing

The default local profile has a cumulative $1 spending limit. Configure separate tokens and limits with `LEANCODE_USERS`, as shown in `.env.example`. The authenticated token determines ownership; prompts cannot select another user. This provides separate local profiles, not production account management.

The application and benchmark runner share the SQLite spending ledger. For a named profile run benchmarks with `--user PROFILE`. Retries/failures with unknown usage retain their reservation, and missing usage is never treated as free. This is intentionally conservative. Inspect provider billing and the local reservations table before reconciling an uncertain attempt; do not delete the database or release reservations merely to continue a run.

Prices and maximum charge guarantees depend on correct gateway/model configuration. Cached-token discounts are not applied to the conservative cost ledger. Local compute power/hardware costs are not billed by the ledger.

## Verification

```sh
uv run python -m unittest discover -s backend/tests -v
LEANCODE_TEST_DOCKER=1 uv run python -m unittest discover -s backend/tests -p test_sandbox.py -v
uv run python benchmarks/run.py --mode smoke
```

Frontend:

```sh
cd frontend
npm run build
npx playwright install chromium
npm run test:e2e
```

Stop your development servers before running browser tests: they start their own servers on ports 8000 and 5173. The browser test uses scripted replies against a disposable fixture and real Docker execution; it does not contact a live model. Screenshots are saved under `frontend/test-results/`.
