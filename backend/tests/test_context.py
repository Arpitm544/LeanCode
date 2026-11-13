import json
import tempfile
import unittest
from pathlib import Path

from leancode.agent import Agent, Operation
from leancode.config import Settings
from leancode.context import Repository, context_packet
from leancode.store import Store


class ContextTests(unittest.TestCase):
    def test_repeated_reads_are_deduplicated_and_changed_files_invalidated(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "code.py").write_text("x = 1\n" + "# existing implementation detail\n" * 100)
            repo = Repository(root)
            store = Store(root / ".state" / "db.sqlite3")
            sid, _ = store.create_session("demo", "Fix the boundary in code.py")
            agent = Agent(Settings(repositories={"demo": {"path": tmp}}), store)
            op = Operation(op="read", path="code.py", start=1, end=2)
            first = agent.read(store.session(sid), repo, op)
            agent.remember(sid, {"op": "read", "result": first})
            second = agent.read(store.session(sid), repo, op)
            agent.remember(sid, {"op": "read", "result": second})
            session = store.session(sid)
            self.assertEqual(session["state"]["cache_hits"], 1)
            optimized = context_packet(session, repo)
            self.assertEqual(len(optimized["inspected_code"]), 1)
            self.assertNotIn("content", optimized["history"][0])
            session["state"]["mode"] = "baseline"
            baseline = context_packet(session, repo)
            self.assertLess(len(json.dumps(optimized)), len(json.dumps(baseline)))
            (root / "code.py").write_text("x = 2\n")
            session["state"]["mode"] = "optimized"
            self.assertEqual(context_packet(session, repo)["inspected_code"], [])
            updated = agent.read(store.session(sid), repo, op)
            self.assertIn("x = 2", updated["content"])

    def test_compaction_preserves_task_and_verification_evidence(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = Repository(tmp)
            session = {"task": "Preserve exact task constraints", "state": {"mode": "optimized", "edits": 1,
                       "verified_snapshot": {"old.py": "stale"}, "history": [{"error": f"failure {n}"} for n in range(20)]}}
            packet = context_packet(session, repo)
            self.assertEqual(packet["task"], session["task"])
            self.assertEqual(len(packet["history"]), 6)
            self.assertEqual(packet["history"][-1]["error"], "failure 19")
            self.assertFalse(packet["verification"]["tests_passed_on_current_files"])
