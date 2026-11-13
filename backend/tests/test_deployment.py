import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts.start_render import app


class DeploymentTests(unittest.TestCase):
    def test_render_restart_preserves_workspace_sessions_and_spend(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {
            "LEANCODE_DATA_DIR": directory, "LEANCODE_TOKEN": "test-token",
            "RENDER_EXTERNAL_HOSTNAME": "leancode-test.onrender.com",
            "LEANCODE_BROWSER_ORIGINS": '["https://leancode-test.vercel.app"]',
        }, clear=True), patch("leancode.config.load_dotenv"):
            first = app()
            workspace = Path(directory) / "demo-python" / "maths.py"
            workspace.write_text("user change\n")
            sid, _ = first.state.store.create_session("demo-python", "persist this task")
            with first.state.store.connect() as db:
                db.execute("UPDATE users SET spent_micro=17 WHERE id='local'")
            second = app()
            self.assertEqual(workspace.read_text(), "user change\n")
            self.assertEqual(second.state.store.session(sid)["task"], "persist this task")
            self.assertEqual(second.state.store.user()["spent_micro"], 17)
            self.assertIn("leancode-test.onrender.com", second.state.settings.allowed_hosts)
            self.assertFalse(second.state.settings.repositories["demo-python"]["confidential"])
            self.assertTrue(second.state.settings.repositories["confidential-demo"]["confidential"])
