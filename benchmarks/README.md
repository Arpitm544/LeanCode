# Evaluation

The six small Python repositories exercise a boundary bug, input validation, multi-caller change, refactor, shared mutable state, and documentation-assisted unittest arguments.

Build the sandbox first: `docker build -f Dockerfile.sandbox -t leancode-sandbox:local .`.

## Workflow smoke check (no model required)

```sh
uv run python benchmarks/run.py --mode smoke
```

This uses known scripted patches and a simulated approving user against disposable fixtures. It runs real Docker tests and separate acceptance checks. It proves the plumbing, not AI problem solving, token efficiency, Tavily connectivity, or model quality. It does not populate the live benchmark dashboard.

## Live comparison

Configure verified model routes, prices, and credentials, then:

```sh
uv run python benchmarks/run.py --mode live --repeats 3
```

Review each exact patch/command in the terminal and type `y` to approve. All variants start from fresh fixture copies and receive the same task, tools, and tests. Independent acceptance checks are added to a separate evaluation copy only after the agent stops. Source fixtures and original repositories are never edited.

- `baseline`: full source and accumulated history, primary model.
- `context`: selective reads and compact history, same primary model.
- `optimized`: selective context plus small-first routing/escalation.

Set `primary: false` on cheap-only routes and `tier: small` / `tier: strong` to define the comparison. Use an explicit provider-qualified model name for each Bifrost route. Maximum three configured routes are used. Pin model versions and prices, and retain environment metadata alongside results. These small fixtures establish proof of implementation; they are not a representative industry-wide benchmark.

JSON/CSV reports and per-run traces remain in `.leancode/`. Retry attempts, failures, unresolved billing reservations, and all measured model usage remain visible. Unknown usage is `null`, never zero. A local-only model still contributes tokens. Cross-model token totals use different tokenizers, so emphasize baseline versus context with the same model. Public-doc searches are bounded and their configured conservative cost is included.

Report all attempts and pass rates before comparing savings. Token reduction is `1 - optimized_tokens / baseline_tokens` on complete matched attempts. Do not report it if either side has unknown usage or zero baseline tokens. Also show paired successes separately; never hide failed runs. This runner does not calculate a savings percentage automatically.

Fault injection tests in `backend/tests/test_policy.py` verify privacy, budgets, and provider takeover separately. They simulate provider failure and do not constitute a real-provider outage test.
