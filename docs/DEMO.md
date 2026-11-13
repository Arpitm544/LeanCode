# Demonstration and remaining validation

## What has been checked

- Backend tests: approvals, ownership, paths, concurrent budgets, privacy filtering, simulated failover, restart protection, context preservation, and cache invalidation.
- Real Docker isolation: non-root execution, read-only sanitized workspace, absent .env secrets, and no outbound network.
- Six scripted workflows: original acceptance checks fail, known fixture patches are reviewed/applied, visible tests pass, then separate acceptance checks pass.
- Real browser workflow: reject a patch, submit again, approve a patch and test command, complete the task, refresh to recover the saved session, and view the diff on desktop/mobile.

The model replies in smoke/browser tests are scripted. These checks do not demonstrate live model accuracy or token savings. Keep their artifacts separate from live benchmark results.

## Before judging

1. Configure two cloud providers through Bifrost and verify their prices/output caps.
2. Configure Tavily and demonstrate a real public documentation lookup.
3. Install a local model, isolate its network, and verify a confidential task with outbound-traffic evidence.
4. Run `uv run python benchmarks/run.py --mode live --repeats 3`. Review each proposed action. Show all attempts, success rates, reported tokens, unknown usage, spending, and sample sizes.
5. Run a provider-outage exercise against the real deployment and confirm the takeover message and retained context. Label any injected failure explicitly.
6. Confirm the organizer's submission deadline, required assets, and judging rubric, then record a live backup demo.

## Five-minute demo

- 0:00-0:40: Show a real task and failing acceptance test.
- 0:40-2:00: Run the agent, review the patch, approve tests, and show the verified result.
- 2:00-2:45: Compare baseline versus context-only runs using the same model; then show the full routing variant. Explain failures and unknown usage.
- 2:45-3:30: Inject an outage and show allowed provider takeover without repeating the patch.
- 3:30-4:30: Demonstrate blocked over-budget dispatch, local-only confidentiality, and rejection without execution.
- 4:30-5:00: Explain sponsor integration roles and measured limitations.

No live model/provider credentials were present during implementation, and Ollama was not installed. Live model quality, real-provider fallback, local inference capability, actual savings, and final submission remain unverified. The integration code and evaluation tools are ready for those checks; results must not be invented.

## Integration progress: November 13, 2026

- A real Tavily basic search for public Python unittest documentation succeeded and returned two results. The application's ledger recorded the configured conservative $0.008 search cost; this is not an invoice claim. The key remains in the ignored local `.env`.
- The official Bifrost v2.4.0 Docker gateway is running with its published port bound to `127.0.0.1:8080`. `/health` and `/openai/v1/models` returned HTTP 200. Gateway data is stored in the ignored `.leancode/bifrost/` directory.
- Model routes remain empty. A real coding model, verified pricing, and bounded-request configuration are still required before live coding or token-savings benchmarks.

Tavily supplies documentation search; it does not replace the coding-model provider behind Bifrost.

### Gemini connection verified

The Gemini key passed the provider's read-only authentication check. A real synthetic JSON-generation request then succeeded through authenticated Bifrost using `gemini/gemini-3.5-flash-lite`: 16 input tokens, 13 output tokens, and 38 micro-USD in the conservative ledger. This is a connection check, not a coding benchmark or savings result.

Gateway admin authentication and a model-restricted inference virtual key are enabled. Raw/content logging is disabled, retries are zero, and one provider key is configured. Existing confidential repositories remain local-only. The separate public `cloud-demo` fixture can be used to review a real generated patch without uploading private code.

Live coding acceptance, token-reduction measurements, a second independent provider, and isolated local inference remain to be validated. Earlier failed setup requests retained conservative spending reservations; they are not claimed as successful or free generation.

A real agent task on the public boundary fixture inspected code and proposed changing `value >= 0` to `value > 0`. It used 1,716 reported tokens before pausing at explicit patch approval. The patch and subsequent test command still require user review; this is not yet a completed coding task.
