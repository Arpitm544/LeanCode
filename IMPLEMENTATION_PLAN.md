# LeanCode: implementation plan

## 1. Product and objective

Build a local web-based coding agent that fixes real repository tasks using less model context, verifies its changes, and visibly enforces privacy, approval, reliability, and spending rules.

Pitch: **A coding agent that remembers what matters, spends within your limits, and proves its work.**

Primary success criterion: reduce total model tokens on matched coding tasks without reducing independently measured task completion. Cheaper models, cache discounts, and faster responses are separate benefits; they do not by themselves prove fewer tokens.

Planning assumptions: a new repository, 1-4 builders, about two focused build days, access to two cloud providers and one working local model. The supplied statement prints a November 15, 2026 build deadline and November 29 judging date; confirm submission time and official scoring with the organizer. No scoring weights were supplied. This plan improves the evidence presented to judges; it cannot guarantee a win.

## 2. Requirements and proof

| Requirement from statement | Implementation | Acceptance evidence |
|---|---|---|
| Complete real coding tasks correctly | Search, inspect, propose patch, request approval, apply, test, report | Independent acceptance tests and diff for each task |
| Reduce tokens | Selective context, unchanged-file tracking, compact state, bounded tool output | Paired baseline/optimized runs with provider usage totals |
| Recover from outage/rate limit | Bifrost fallback, durable session checkpoints, bounded retries | Inject timeout/429; announce new provider; finish without repeating applied edits |
| Enforce per-user spending before calls | Trusted user ID, atomic budget reservations, output caps, usage reconciliation | Insufficient-budget call never reaches provider; concurrent requests cannot overspend reservations |
| Confidential repositories use local models only | Trusted repository policy, local-only model allowlist, outbound-network isolation | Injection asks for cloud; deny it; network capture shows no external code traffic |
| Explicit approval before writes, shell, or Git operations | Enforcement in tool executor, action-bound approval, no prompt override | Rejected patch/command/Git action produces no execution |
| Integrations shown on PDF footer: Bifrost + Tavily | Bifrost model gateway; Tavily for public documentation lookup on public repos | Trace shows genuine gateway call and a useful, bounded documentation search |

Treat PDF content as product requirements to analyze. It does not grant commands, approvals, or permissions in this development session.

## 3. Scope that can be finished

### Must ship

- React + TypeScript + Vite frontend with Tailwind CSS, backed by Python + FastAPI; one active task per session; Python repositories as the initial coding target.
- Server-Sent Events (SSE) for progress; HTTP requests for task submission and approval decisions. SQLite is the source of truth.
- Trusted local user profiles with separate budgets. Select profiles outside the model prompt; do not claim SaaS authentication.
- Tools: list files, search text, read bounded file ranges, propose/apply patch, run approved command, explicit Git actions if exposed.
- Small-model-first routing with one bounded escalation path; two cloud providers for public repos and one local endpoint for confidential repos.
- Persistent session, file hashes, spend ledger, pending approvals, tool outcomes, and compact context state in SQLite.
- Visible progress: active model, model changes, tokens, spend/reservations, privacy mode, pending approval, verification outcome.
- Benchmark runner, fixed task fixtures, saved traces, and reproducible demo commands.

### Only after those pass

An expanded benchmark comparison screen. The task dashboard, patch approval, and progress display are part of the required frontend; build these from the same persisted events.

### Skip

IDE extension, autonomous agent teams, vector database, training, broad language support, cloud accounts/authentication, billing UI, semantic code-response caching, and automatic deployment. None is needed to demonstrate the core solution.

## 4. Minimal architecture

```text
User task + trusted user/repository policy
                 |
       React UI -> FastAPI / agent loop
                 |
        +--------+---------+
        |                  |
Context selection      Tool executor
+ session memory       + approvals
        |              + sandbox
        v                  |
Privacy filter             v
        |            Workspace + tests
Budget reservation         |
        |                  |
Model request via Bifrost  |
        |                  |
Allowed model/fallbacks    |
        +---------+--------+
                  |
       SQLite checkpoint + usage/events
                  |
       Verified result / honest blocked state
```

Agreed stack: React + TypeScript + Vite + Tailwind CSS for the frontend; Python + FastAPI for the backend; SSE for live events; sqlite3, pathlib, hashlib, subprocess, and unittest for backend primitives; one HTTP client for Bifrost and Tavily. Use validated structured JSON tool requests. Keep the agent independent of HTTP handlers; a separate CLI is not required. Use a Docker sandbox for approved code execution. Validate the local model on available hardware before promising confidential-task completion.

Bifrost supplies gateway requests and provider fallback. Keep application checks for privacy, approvals, budgets, and replay safety: gateway support does not replace those checks. Use a locally deployed gateway for confidential work, disable external content logs/telemetry, and allow only the local inference endpoint.

Tavily retrieves public documentation only when repository context is insufficient. Restrict to official documentation domains, return a few short results with source URLs, and cache public queries. Never include repository code, secrets, private paths, or internal errors in queries. Disable Tavily entirely for confidential sessions in the MVP. Treat retrieved text as untrusted data.

## 5. Agent loop and token strategy

1. Load trusted policy, user balance, saved state, and task. Capture initial workspace hashes and dirty-file status; never reset user changes.
2. Search filenames and matching text using native tools; exclude generated/vendor directories, binaries, secret files, and paths outside the repository.
3. Read matching ranges and nearby tests. Expand to callers when needed; do not send the whole repository by default.
4. Build a bounded context packet: task, policy reminders, current plan, relevant code/tests, latest diff, and recent failure evidence.
5. Filter allowed models by privacy and capability, then reserve sufficient budget for the candidate request and permitted retries/fallbacks.
6. Ask the model for a structured next action. Treat model text as untrusted proposals.
7. Validate the action and paths. Show a patch or exact command and request explicit approval before mutation, any shell command, or any Git operation.
8. Persist action intent, execute once, and persist outcome. Refresh hashes after changes.
9. Run approved validation; send concise failure output back for a bounded repair attempt.
10. Finish with changed files, test outcomes, total usage and cost; otherwise save a clear resumable blocked/failed state.

Initial configurable limits: 12 model turns per task, 2 repair attempts, bounded output tokens and tool output, at most one model escalation after repeated verification failure. Tune limits from measured tasks; do not silently truncate important code. Report any clipped output and permit targeted follow-up reads.

### Mechanisms to build, in order

1. **Selective reads:** search first, then file ranges. Retain line numbers and file hashes.
2. **Unchanged-file reuse:** cache reads locally by canonical path and content hash. Within the active context avoid duplicate copies. A cache hit does not mean the model remembers omitted content: include required source again if it has left the active context.
3. **Compact state:** keep task, decisions, touched paths/hashes, latest patch, unresolved errors, and test outcomes; remove redundant historical output. Use deterministic compaction first so summaries do not add hidden model calls.
4. **Bounded tools:** send concise search results and failure excerpts with a way to retrieve more. Advertise only tools available in the current state.
5. **Model routing:** use the smaller model initially; escalate after concrete failure or complexity evidence. Count all routing/repair calls in results. This primarily saves money, and may increase tokens.

Avoid semantic patch caching: similar tasks can require different edits. Avoid embedding indexes until plain search fails on measured fixtures.

## 6. Mandatory controls: exact behavior

### Budget

- Store money as integer micro-units with a documented currency and dated provider rate configuration.
- Before dispatch, estimate input with the appropriate tokenizer plus a conservative margin; cap maximum billed output and any reasoning tokens. Reject models whose maximum charge cannot be bounded.
- In one SQLite transaction reserve the upper-bound charge against the trusted user's balance. Include every retry, fallback, and paid auxiliary call, either in an overall envelope or through a check before each attempt.
- Bifrost automatic retries/fallbacks must remain inside that reserved envelope; disable unbounded hidden retries. Apply compatible gateway per-user limits as another guard, not the sole proof of strict pre-call limits.
- Reconcile actual reported usage after completion. Retain reservation for ambiguous timeout/unknown usage until resolved; do not assume failed requests are free.
- Unknown pricing fails closed. Tavily usage gets a separate quota/cost entry. Local inference still has token/turn limits even when cloud billing is zero.
- When balance is insufficient: do not dispatch, checkpoint, and explain what remains. Do not silently raise limits or switch to an unapproved route.

### Privacy and approvals

- Store privacy settings outside model-editable repository content. Default an unclassified repository to confidential until the user classifies it through the trusted interface.
- Filter the entire route and fallback chain. No local model available means pause, never cloud fallback.
- Keep code-bearing logs, context, caches, checkpoints, and embeddings local; no external tracing for confidential sessions. Block outbound networking in its tool sandbox, including approved tests.
- Canonicalize paths and check symlinks/traversal on reads and writes; deny secret paths and traversal outside the workspace. Sandbox mounting must not expose unrelated home-directory files or credentials.
- Implement free reads as dedicated constrained tools. A shell command that happens to read files still needs approval. Apply the same rule to all Git subprocesses.
- Approval binds to exact patch/command, working directory, and affected file hashes. Changed action or stale files requires fresh approval; rejection means no effect. Keep the approval UI inaccessible to the model.
- Show meaningful effects in approvals, including network access or file deletion. Reject shell escape routes around the tool policy. Run approved commands with time/output limits and without host secrets.
- No automatic commit, push, deletion, or reset. Tests are code execution and require approval too.

### Failover and recovery

- Checkpoint before model calls and actions. Persist provider/tool-call IDs and completed outcomes.
- Retry only retryable failures with a small time/attempt limit. Never bypass a budget/privacy denial through another provider.
- Announce old provider, new provider, reason, and retained session state. Validate fallback tool-call compatibility during setup.
- Do not execute incomplete streamed tool calls. On recovery, inspect action status and current file hashes instead of replaying mutations.
- An interrupted shell command with unknown outcome requires inspection and explicit rerun approval; do not automatically repeat it.
- If all allowed models fail, retain the session and report a resumable failure. Reliability does not mean falsely claiming success.

## 7. Files and responsibilities

```text
frontend/
  src/
    App.tsx        # task dashboard and repository selection
    api.ts         # HTTP requests and SSE subscriptions
    components/    # task form, timeline, diff approval, usage, test results
backend/
  leancode/
    api.py         # FastAPI routes and SSE; backend modules below live here
    agent.py         # bounded task loop and routing decisions
    context.py       # repository search, ranges, hashes, compact context
    gateway.py       # Bifrost requests, usage extraction, Tavily docs lookup
    policy.py        # trusted privacy policy and budget reservations
    tools.py         # validated tools, approvals, sandbox execution
    store.py         # SQLite sessions, ledger, events, action status
benchmarks/
  tasks/           # small pinned repository fixtures and task descriptions
  acceptance/      # hidden-to-agent acceptance checks
  run.py           # matched isolated runs and result export
  README.md        # experiment procedure and limitations
tests/             # control tests, malformed inputs, recovery checks
README.md
.env.example
```

Keep these as modules in one application. No microservices. Keys belong in the environment and must never be committed or passed to tool sandboxes.

## 8. Benchmark that supports the pitch

Start with six fixed tasks: boundary-condition bug, multi-caller API change, small validation feature, refactor preserving behavior, cross-file bug, and a public-library task that benefits from Tavily documentation. Include tests, manifests, and pinned starting commits. Ensure tests exercise behavior beyond the model's own generated tests.

Compare on isolated copies with identical task text, initial files, acceptance checks, sandbox resources, and approval policy:

- Baseline: same agent tools and primary model, but naive full-file context/history; no selective-memory optimizations.
- Context-only optimization: same model, selective reads and compact state. This isolates the token contribution.
- Full optimization: context optimization plus smaller-model routing and bounded escalation. This measures the final product.

Use a practically viable baseline within the model context limit; do not deliberately make it incompetent or flood it with irrelevant files. Keep public-doc lookup availability the same across variants. Separate cold-start and warm-session trials. Run each task three times if time allows; if not, report the actual sample count and variability limitation. No cherry-picking successful runs.

Report task success, input/output/other billed tokens, cached tokens separately, total cost including retries and failed attempts, latency, model calls, and repeated-read counts. Use provider usage where available; label estimates and missing usage. Count local-model tokens too. Cross-model token totals are tokenizer-dependent, so emphasize the same-model context comparison.

Formulas:

- Success rate = independently passing tasks / attempted tasks.
- Token reduction = 1 - optimized total tokens / baseline total tokens on matched attempts.
- Cost per success = total experiment spend, including failures / successful tasks.

If there are no successes, cost per success is undefined. Show failed-task token totals so stopping early cannot masquerade as efficiency. Also report matched-success comparisons, without hiding the full success rate.

Working targets, not results: all six task types pass, at least 30% fewer tokens in the same-model comparison, every mandatory control scenario passes. No percentage belongs in the pitch until measured.

## 9. Build order and exit gates

Budget about 22 focused person-hours across two days, with rest and submission time separate. This estimate includes the agreed frontend; it is a planning estimate, not a guarantee. Preserve the final buffer; cut optional benchmark visuals first.

| Phase | Hours | Deliverable and exit gate |
|---|---:|---|
| Integration spike | 0-2 | Cloud calls through Bifrost, working second provider, local tool-capable model, public Tavily result; settle credentials/hardware now |
| Web foundation and one safe end-to-end task | 2-9 | React task form, FastAPI routes, SSE, search/read, structured action, approval, sandboxed patch/test, persistent state; one real task independently passes |
| Mandatory controls | 9-13 | User budgets, local-only privacy, bounded failover and recovery; negative tests pass before adding polish |
| Token optimization | 13-16 | Selective context, hashes, compaction, bounded tools; compare same-model baseline on two tasks |
| Evaluation | 16-20 | Six-task benchmark, control scenarios, exported traces/results; honest results table |
| Submission and demo | 20-22 | Reproducible setup, README, short recording, architecture slide, practiced live demo; optional results view only if stable |

For four people: split context/agent, policy/tools, gateway/recovery, and benchmark/demo work with agreed request/event schemas. For one person: follow the phase order, keep the web UI to one page, and reduce benchmark repetitions before dropping required controls.

## 10. Minimum meaningful checks

- Correct patches pass independent acceptance tests and preserve unrelated user edits.
- Malformed tool request and path/symlink escape are rejected without effects.
- Approve/reject/stale-patch cases; direct and nested shell/Git attempts require approval.
- Confidential prompt injection cannot enable cloud fallback, Tavily, external logs, or tool-network leakage.
- Low balance, simultaneous reservations, retry/fallback cost, unknown price, and unknown timeout usage cannot bypass spending policy.
- Timeout/429 triggers allowed fallback and visible notification; all-provider failure preserves the session.
- Restart after patch application does not apply twice; ambiguous command is not rerun automatically.
- Changed source invalidates cached reads; compaction retains required task constraints and failure evidence.

Use deterministic fake providers for control tests and fault injection, plus real-provider smoke tests. Explicitly label simulated outages in the demo.

## 11. Five-minute demonstration

1. **0:00-0:40:** State the problem and show a real failing task with its acceptance test.
2. **0:40-2:00:** Run the agent: targeted reads, visible token counter, reviewed patch, approved test, passing result.
3. **2:00-2:45:** Show recorded matched benchmark traces and measured results, including failures and sample counts.
4. **2:45-3:30:** Inject a provider timeout, show announced takeover and preserved progress.
5. **3:30-4:30:** Show three short controls: insufficient budget blocks dispatch; confidential policy rejects a cloud request; rejected write produces no change.
6. **4:30-5:00:** Explain Bifrost and Tavily roles, limitations, and the next concrete improvement suggested by measurements.

Keep a local recording and saved run artifacts if external APIs fail during judging. A recording is a backup, not evidence that every live integration is working.

## 12. Evidence and open decisions

Source problem statement: `/Users/arpit/Downloads/problem_explanation_q2jha91frd9.pdf` (single supplied PDF page, printed page marker 01/05). Other challenge pages and official scoring rules were not supplied.

Verified technical references:
- Bifrost retries/fallbacks: https://docs.getbifrost.ai/features/retries-and-fallbacks
- Bifrost virtual keys: https://docs.getbifrost.ai/features/governance/virtual-keys
- Tavily search request/options: https://docs.tavily.com/documentation/api-reference/endpoint/search

Before implementation, confirm team size, actual hours remaining, available API credits/providers, and local RAM/model capability. Choose exact model IDs and prices through the integration spike, based on access and measured correctness rather than a speculative model ranking. Confirm whether sponsor integration usage has additional submission requirements.

Implementation update: the web app, agent loop, controls, benchmark runner, and browser checks are implemented. Six scripted Docker workflows pass. Live provider completion and token savings remain unmeasured. See docs/DEMO.md for remaining validation. Main risks are local model capability, strict budget accounting across provider retries, and execution sandbox setup; validate those before spending time on presentation polish.


## 13. Implementation parts with completion gates

Build in this order. Parts are milestones, not separate services.

### Part 1: Foundation and integration checks

Create frontend/ and backend/; document local startup and environment variables. Establish SQLite tables for users, repositories, sessions, actions, events, and spend reservations. Define validated task, action, usage, and event payloads shared by API and UI. Smoke-test Bifrost, the fallback provider, Ollama, and Tavily before building around them. Use fake credentials/provider responses only in explicitly labeled development fixtures.

Done: React reaches backend health endpoint, database persists across restart, and integration availability is recorded. If local inference is unavailable, confidential mode reports blocked rather than using cloud.

### Part 2: Task dashboard

One page with registered repository selection, task input, budget/privacy indicators, session timeline, patch/command approval panel, and final test results. Use labeled development events initially, then replace them with real persisted events. Include loading, disconnected, empty, rejected, and failed states, keyboard-accessible buttons, and readable diffs.

Done: user can submit a task, see its status, and review an action without navigating between multiple screens. Never render secrets or accept a model-provided event as an approval.

### Part 3: Backend sessions and live events

Implement POST /sessions, GET /sessions/{id}, GET /sessions/{id}/events (SSE), and POST /sessions/{id}/actions/{action_id}/decision. Use a persisted monotonic event ID, reconnect replay, bounded background work, and one active worker per session. Closing the browser must not cancel or duplicate the task. Approval writes are atomic and can resolve a pending action only once.

Bind the MVP server to localhost; validate browser Origin/Host, restrict CORS, require a per-launch session credential, and authorize session ownership on every route. Do not expose arbitrary host paths through the API: select registered repository IDs. This is a local application, not a publicly hosted multi-user service.

Done: refresh/reconnect restores progress; a duplicate submit/approval cannot start duplicate execution; another profile cannot inspect or approve the session. No API credentials enter the frontend bundle.

### Part 4: Safe agent execution

Implement search/read tools, bounded agent loop, patch proposal, backend approval enforcement, sandboxed execution, and verified completion. Put trusted privacy and pre-call budget checks in place before sending any repository content to a provider. Persist action intent and outcome to support restart recovery. Preserve pre-existing edits.

Done: a real task produces a reviewed patch and passes independently defined tests; a rejected action never executes. The UI shows success only after backend verification.

### Part 5: Reliability, budgets, and privacy completion

Complete atomic spending reservations, output/retry caps, reconciliation, policy-filtered fallback, takeover notifications, local-only confidential routing, egress restrictions, and resume behavior. Use the exact requirements in section 6; this part hardens the checks introduced in part 4 rather than adding safety after unsafe execution.

Done: outage, low-balance, prompt-injection, unauthorized approval, concurrent reservation, and crash-recovery checks pass. An unavailable allowed route creates a resumable blocked state.

### Part 6: Token efficiency

Add selective context, read deduplication, hash invalidation, deterministic history compaction, bounded tool results, and small-model routing. Display actual input/output tokens, cost, and reserved balance; distinguish estimates from reported usage. Do not invent a live savings percentage without a matched baseline.

Done: same-model baseline comparison shows measured token usage and independently verified correctness. Report regressions before tuning.

### Part 7: Benchmarks and results

Implement six pinned tasks and paired baseline/context-only/full runs. Export results as JSON/CSV and show a compact frontend comparison table using real results. Include failed attempts, retries, sample sizes, and local-model tokens. Add one public-doc task to demonstrate useful Tavily integration.

Done: another person can reproduce the experiment; savings shown in the UI reconcile with stored run records.

### Part 8: Demo and submission

Polish the existing one-page UI, verify fresh setup, document limitations and secret handling, prepare the five-minute demo, and record a backup. Run real-provider smoke tests separately from fault-injection tests. Keep all application components local for the initial demo; public deployment would require an explicit authentication and sandbox-hosting design.

Done: the demo shows a completed task, honest token comparison, visible provider takeover, budget denial, local-only confidentiality, and rejected execution.

Dependency order: 1 -> 2 -> 3 -> 4 -> 5 -> 6 -> 7 -> 8. UI layout and API development can overlap once payloads are agreed, but never connect live execution before backend policy enforcement exists.
