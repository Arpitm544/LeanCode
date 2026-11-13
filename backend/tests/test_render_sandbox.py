import importlib.util
import os
import shlex
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from leancode.context import Repository
from leancode.policy import PolicyError
from leancode.tools import sandbox


@unittest.skipUnless(importlib.util.find_spec("render"), "Install the cloud extra for Render SDK contract tests")
class RenderSandboxTests(unittest.TestCase):
    def setUp(self):
        from render.sandbox import SandboxExecExit, SandboxExecOutput
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        (self.root / "source.py").write_text("value = 1\n")
        (self.root / ".env").write_text("DO_NOT_UPLOAD=secret\n")
        self.repo = Repository(self.root)
        self.env = patch.dict(os.environ, {"LEANCODE_SANDBOX_BACKEND": "render", "RENDER_API_KEY": "test-only",
            "RENDER_WORKSPACE_ID": "tea-test", "LEANCODE_RENDER_SNAPSHOT_ID": "snp-test",
            "LEANCODE_RENDER_SANDBOX_GROUP_ID": "sbg-test"})
        self.env.start()
        self.factory = patch("render.Render")
        self.client = self.factory.start().return_value
        self.client.sandboxes.create.return_value = SimpleNamespace(id="sbx-test")
        self.client.sandboxes.wait_until_running.return_value = SimpleNamespace(network_policy=SimpleNamespace(type="deny-all"))
        self.client.sandboxes.exec.return_value = [SandboxExecOutput("stdout", "Ran 1 test\nOK\n"), SandboxExecExit(0)]
        self.output_type = SandboxExecOutput
        self.exit_type = SandboxExecExit

    def tearDown(self):
        self.factory.stop()
        self.env.stop()
        self.tmp.cleanup()

    def test_upload_is_sanitized_and_docker_constraints_and_quoting_are_preserved(self):
        def check_upload(_id, directory, _remote):
            self.assertEqual([p.name for p in Path(directory).iterdir()], ["source.py"])
        self.client.sandboxes.copy_to.side_effect = check_upload
        command = ["python", "-c", "print('literal; not a shell command')"]
        with patch("subprocess.Popen") as host:
            result = sandbox(self.repo, command, "leancode-sandbox:local")
        host.assert_not_called()
        self.assertEqual(result["exit_code"], 0)
        created = self.client.sandboxes.create.call_args.kwargs
        self.assertEqual(created["network_policy"], "deny-all")
        self.assertEqual(created["timeout_seconds"], 180)
        self.assertNotIn("env", created)
        args = shlex.split(self.client.sandboxes.exec.call_args.args[1])
        self.assertEqual(args[-len(command):], command)
        for flag in ["--network=none", "--read-only", "--cap-drop=ALL", "--user=65534:65534", "--memory=256m", "--pull=never"]:
            self.assertIn(flag, args)
        self.assertIn("type=bind,src=/home/render/leancode-workspace,dst=/workspace,readonly", args)
        self.client.sandboxes.terminate.assert_called_once_with("sbx-test")

    def test_stream_failures_limits_and_unconfirmed_network_never_fallback(self):
        cases = [([], "exit code"), ([self.output_type("stdout", "x" * 32_000)], "output limit"),
                 ([self.exit_type(124)], "time limit")]
        for events, message in cases:
            with self.subTest(message=message):
                self.client.sandboxes.exec.return_value = events
                with self.assertRaisesRegex(PolicyError, message), patch("subprocess.Popen") as host:
                    sandbox(self.repo, ["python", "-V"], "leancode-sandbox:local")
                host.assert_not_called()
        self.client.sandboxes.wait_until_running.return_value.network_policy.type = "allow-all"
        self.client.sandboxes.copy_to.reset_mock()
        with self.assertRaisesRegex(PolicyError, "deny-all"):
            sandbox(self.repo, ["python", "-V"], "leancode-sandbox:local")
        self.client.sandboxes.copy_to.assert_not_called()
        self.assertEqual(self.client.sandboxes.terminate.call_count, 4)

    def test_creation_and_transfer_failures_are_bounded_and_cleaned_up(self):
        self.client.sandboxes.copy_to.side_effect = RuntimeError("transfer failed")
        with self.assertRaisesRegex(PolicyError, "no host command fallback"):
            sandbox(self.repo, ["python", "-V"], "leancode-sandbox:local")
        self.client.sandboxes.terminate.assert_called_once_with("sbx-test")
        self.client.sandboxes.create.side_effect = RuntimeError("create unavailable")
        self.client.sandboxes.terminate.reset_mock()
        with self.assertRaisesRegex(PolicyError, "no host command fallback"):
            sandbox(self.repo, ["python", "-V"], "leancode-sandbox:local")
        self.client.sandboxes.terminate.assert_not_called()
