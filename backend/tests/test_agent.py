import tempfile
import unittest
from pathlib import Path

from leancode.agent import Agent
from leancode.config import Settings
from leancode.context import Repository
from leancode.policy import PolicyError
from leancode.store import Store
from leancode.tools import apply_patch, patch_proposal


class ScriptedGateway:
    def __init__(self, operations):
        self.operations = iter(operations)

    def complete(self, session, messages):
        return next(self.operations)


class AgentTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        (self.root / "maths.py").write_text("def positive(n):\n    return n >= 0\n")
        self.settings = Settings(data_dir=self.root / ".data", token="test",
                                 repositories={"demo": {"path": str(self.root), "confidential": True}})
        self.store = Store(self.root / ".data" / "db.sqlite3")
        self.sid, _ = self.store.create_session("demo", "fix positive: zero is not positive")

    def tearDown(self):
        self.tmp.cleanup()

    def test_review_patch_test_finish_and_no_replay(self):
        gateway = ScriptedGateway([
            {"op": "read", "path": "maths.py"},
            {"op": "edit", "path": "maths.py", "old": "n >= 0", "new": "n > 0"},
            {"op": "command", "command": ["python", "-m", "unittest", "discover", "-s", "tests"]},
            {"op": "finish", "reason": "Fixed zero boundary and verified tests"},
        ])
        calls = []
        def executor(*args):
            calls.append(args)
            return {"exit_code": 0, "output": "Ran 3 tests in 0.001s\nOK"}
        agent = Agent(self.settings, self.store, gateway=gateway, executor=executor)
        self.store.claim(self.sid)
        agent.run(self.sid)
        self.assertIn(">=", (self.root / "maths.py").read_text())
        action = self.store.session(self.sid)["actions"][-1]
        self.store.decide(self.sid, action["id"], True)
        self.store.claim(self.sid)
        agent.run(self.sid)
        self.assertNotIn(">=", (self.root / "maths.py").read_text())
        action = self.store.session(self.sid)["actions"][-1]
        self.assertEqual(calls, [])
        self.store.decide(self.sid, action["id"], True)
        self.store.claim(self.sid)
        agent.run(self.sid)
        self.assertEqual(self.store.session(self.sid)["status"], "completed")
        self.assertEqual(len(calls), 1)
        self.assertTrue(all(a["status"] == "executed" for a in self.store.session(self.sid)["actions"]))

    def test_stale_patch_and_path_escapes_rejected(self):
        repo = Repository(self.root)
        payload = patch_proposal(repo, "maths.py", "n >= 0", "n > 0", "fix")
        (self.root / "maths.py").write_text("user edit\n")
        with self.assertRaises(PolicyError):
            apply_patch(repo, payload)
        for path in ("../outside.py", ".env", "/etc/passwd", ".data/db.sqlite3"):
            with self.assertRaises(PolicyError):
                repo.path(path)
        (self.root / "link.py").symlink_to(self.root / "maths.py")
        with self.assertRaises(PolicyError):
            repo.read("link.py")
        self.assertEqual((self.root / "maths.py").read_text(), "user edit\n")

    def test_finish_without_tests_cannot_claim_success(self):
        agent = Agent(self.settings, self.store, gateway=ScriptedGateway([{"op": "finish"}]))
        self.store.claim(self.sid)
        agent.run(self.sid)
        self.assertEqual(self.store.session(self.sid)["status"], "blocked")
