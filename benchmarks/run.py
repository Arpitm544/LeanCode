"""Run fixed isolated tasks. Smoke runs use scripted responses, never claim model savings."""

import argparse
import csv
import hashlib
import json
import shutil
import tempfile
import time
from pathlib import Path

from leancode.agent import Agent
from leancode.config import Settings
from leancode.context import Repository
from leancode.store import Store
from leancode.tools import sandbox

ROOT = Path(__file__).resolve().parent
TEST_COMMAND = ["python", "-m", "unittest", "discover", "-s", "tests", "-v"]


class SmokeGateway:
    """Known edits test plumbing only; this is not an AI solver or a token benchmark."""

    def __init__(self, fixture):
        operations = []
        for edit in fixture["edits"]:
            operations.extend([{"op": "read", "path": edit["path"]},
                               {"op": "edit", **edit, "reason": "Scripted fixture patch (not a model response)"}])
        operations.extend([{"op": "command", "command": TEST_COMMAND, "reason": "Run fixture tests"},
                           {"op": "finish", "reason": "Scripted smoke workflow complete"}])
        self.operations = iter(operations)

    def complete(self, session, messages):
        return next(self.operations)


def acceptance(workspace, fixture_id, image):
    with tempfile.TemporaryDirectory(prefix="leancode-acceptance-") as tmp:
        evaluation = Path(tmp) / "evaluation"
        shutil.copytree(workspace, evaluation)
        shutil.copyfile(ROOT / "acceptance" / fixture_id / "test_acceptance.py",
                        evaluation / "tests" / "test_acceptance.py")
        return sandbox(Repository(evaluation), TEST_COMMAND, image)


def run_fixture(settings, store, fixture, variant, smoke=False):
    start = time.monotonic()
    with tempfile.TemporaryDirectory(prefix="leancode-benchmark-") as tmp:
        workspace = Path(tmp) / "workspace"
        shutil.copytree(ROOT / "tasks" / fixture["id"], workspace)
        settings.repositories[fixture["id"]] = {"path": str(workspace), "confidential": False}
        if smoke and acceptance(workspace, fixture["id"], settings.sandbox_image)["exit_code"] == 0:
            raise RuntimeError("Fixture already passes acceptance before its required change")
        sid, _ = store.create_session(fixture["id"], fixture["task"], "optimized" if smoke else variant)
        agent = Agent(settings, store, gateway=SmokeGateway(fixture) if smoke else None)
        unchanged_tests = {p.relative_to(workspace).as_posix(): p.read_bytes() for p in (workspace / "tests").rglob("*.py")}
        while True:
            store.claim(sid)
            agent.run(sid)
            current = store.session(sid)
            if current["status"] != "awaiting_approval":
                break
            action = next(a for a in current["actions"] if a["status"] == "pending")
            if action["kind"] == "patch" and action["payload"]["path"].startswith("tests/"):
                store.decide(sid, action["id"], False)
                break
            if smoke:
                approve = True  # Simulated user for fixed, predefined fixture actions only.
            else:
                print(action["payload"].get("diff") or json.dumps(action["payload"].get("command")))
                approve = input(f"Approve exact {action['kind']} in isolated fixture? [y/N] ").strip().lower() == "y"
            store.decide(sid, action["id"], approve)
            if not approve:
                break
        current = store.session(sid)
        evaluation = acceptance(workspace, fixture["id"], settings.sandbox_image)
        tests_intact = all((workspace / path).read_bytes() == text for path, text in unchanged_tests.items())
        passed = current["status"] == "completed" and evaluation["exit_code"] == 0 and tests_intact
        state = current["state"]
        with store.connect() as db:
            holds = db.execute("SELECT COUNT(*),COALESCE(SUM(amount_micro),0) FROM reservations "
                               "WHERE session_id=? AND status='held'", (sid,)).fetchone()
        known_tokens = not smoke and not holds[0] and "input_tokens" in state and "output_tokens" in state
        result = {"task": fixture["id"], "variant": variant, "session_id": sid, "user_id": "local",
                  "outcome": "passed" if passed else current["status"] if current["status"] != "completed" else "failed_acceptance",
                  "tokens": state.get("input_tokens", 0) + state.get("output_tokens", 0) if known_tokens else None,
                  "input_tokens": state.get("input_tokens"), "output_tokens": state.get("output_tokens"),
                  "cost_micro": state.get("cost_micro", 0), "reserved_micro": holds[1], "unknown_usage": bool(holds[0]),
                  "elapsed_seconds": round(time.monotonic() - start, 3), "model_calls": state.get("model_calls", 0),
                  "cached_tokens": state.get("cached_tokens"),
                  "simulated": smoke, "fixture_hash": hashlib.sha256(json.dumps(fixture, sort_keys=True).encode()).hexdigest()}
        artifact = settings.data_dir / "benchmarks" / f"{sid}.json"
        artifact.parent.mkdir(parents=True, exist_ok=True)
        artifact.write_text(json.dumps({"result": result, "trace": current, "acceptance": evaluation}, indent=2))
        artifact.chmod(0o600)
        return result


def summarize(results):
    summary = {}
    for variant in dict.fromkeys(row["variant"] for row in results):
        rows = [r for r in results if r["variant"] == variant]
        successes = sum(row["outcome"] == "passed" for row in rows)
        unknown = any(row["tokens"] is None for row in rows)
        summary[variant] = {"attempts": len(rows), "successes": successes,
                            "tokens": None if unknown else sum(row["tokens"] for row in rows),
                            "reported_cost_micro": sum(row["cost_micro"] for row in rows),
                            "unresolved_reserved_micro": sum(row["reserved_micro"] for row in rows)}
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=["smoke", "live"], default="smoke")
    parser.add_argument("--task", default="all")
    parser.add_argument("--repeats", type=int, choices=range(1, 4), default=1)
    args = parser.parse_args()
    settings = Settings.load()
    store = Store(settings.data_dir / "benchmark.sqlite3")
    fixtures = json.loads((ROOT / "tasks.json").read_text())
    if args.task != "all":
        fixtures = [f for f in fixtures if f["id"] == args.task]
    if not fixtures:
        parser.error("Unknown task")
    if args.mode == "smoke":
        print("SCRIPTED SMOKE RUN: tests workflow only; tokens unknown; no AI or savings claim.")
    results = []
    variants = ["smoke"] if args.mode == "smoke" else ["baseline", "context", "optimized"]
    for repeat in range(args.repeats):
        for fixture in fixtures:
            for variant in variants:
                row = run_fixture(settings, store, fixture, variant, smoke=args.mode == "smoke")
                row["repeat"] = repeat + 1
                results.append(row)
                print(f"{fixture['id']:15} {variant:10} {row['outcome']:18} tokens={row['tokens']}")
    # Keep smoke plumbing checks out of the live benchmark dashboard.
    report_name = "smoke-results" if args.mode == "smoke" else "benchmark-results"
    report = settings.data_dir / f"{report_name}.json"
    temporary = report.with_suffix(".tmp")
    temporary.write_text(json.dumps(results, indent=2))
    temporary.chmod(0o600)
    temporary.replace(report)
    with (settings.data_dir / f"{report_name}.csv").open("w") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(results[0]))
        writer.writeheader()
        writer.writerows(results)
    print(json.dumps(summarize(results), indent=2))
    return 0 if all(row["outcome"] == "passed" for row in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
