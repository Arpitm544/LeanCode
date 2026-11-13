import contextlib
import importlib.util
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from dotenv import dotenv_values


class SetupTests(unittest.TestCase):
    def test_setup_keeps_keys_private_and_preserves_repository_policy(self):
        location = Path(__file__).resolve().parents[2] / "scripts" / "setup_gemini.py"
        spec = importlib.util.spec_from_file_location("setup_gemini", location)
        setup = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(setup)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            fixture = root / "benchmarks" / "tasks" / "boundary"
            fixture.mkdir(parents=True)
            (fixture / "maths.py").write_text("value = 0\n")
            (root / ".env").write_text('GEMINI_API_KEY=test-private-key\nLEANCODE_REPOSITORIES=\'{"private":{"path":"project","confidential":true}}\'\n')
            output = io.StringIO()
            with patch.object(setup, "ROOT", root), contextlib.redirect_stdout(output):
                setup.main()
                password = (root / ".leancode" / "bifrost" / "admin-password").read_text()
                setup.main()
            self.assertNotIn("test-private-key", output.getvalue())
            values = dotenv_values(root / ".env")
            repos = json.loads(values["LEANCODE_REPOSITORIES"])
            self.assertTrue(repos["private"]["confidential"])
            self.assertFalse(repos["cloud-demo"]["confidential"])
            config = json.loads((root / ".leancode" / "bifrost" / "config.json").read_text())
            self.assertEqual(config["providers"]["gemini"]["network_config"]["max_retries"], 0)
            self.assertEqual(config["providers"]["gemini"]["keys"][0]["value"], "env.GEMINI_API_KEY")
            self.assertNotIn("test-private-key", json.dumps(config))
            self.assertEqual((root / ".leancode" / "bifrost" / "gateway.env").stat().st_mode & 0o777, 0o600)
            self.assertEqual((root / ".leancode" / "bifrost" / "admin-password").read_text(), password)
