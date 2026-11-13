import os
import tempfile
import unittest
from pathlib import Path

from leancode.context import Repository
from leancode.tools import sandbox


@unittest.skipUnless(os.getenv("LEANCODE_TEST_DOCKER") == "1", "Set LEANCODE_TEST_DOCKER=1 for real Docker checks")
class SandboxTests(unittest.TestCase):
    def test_real_container_has_no_network_secrets_or_workspace_writes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "source.py").write_text("value = 1\n")
            (root / ".env").write_text("DO_NOT_MOUNT=private\n")
            code = """
import os, pathlib, socket
assert os.getuid() == 65534
assert not pathlib.Path('/workspace/.env').exists()
assert 'BIFROST_KEY' not in os.environ
assert pathlib.Path('/workspace/source.py').read_text() == 'value = 1\\n'
try:
    pathlib.Path('/workspace/source.py').write_text('overwrite')
except OSError:
    pass
else:
    raise AssertionError('Workspace is writable')
sock = socket.socket()
sock.settimeout(0.3)
try:
    sock.connect(('1.1.1.1', 53))
except OSError:
    pass
else:
    raise AssertionError('External network is available')
finally:
    sock.close()
print('Sandbox isolation verified')
"""
            result = sandbox(Repository(root), ["python", "-c", code], "leancode-sandbox:local")
            self.assertEqual(result["exit_code"], 0, result["output"])
            self.assertIn("Sandbox isolation verified", result["output"])
            self.assertEqual((root / "source.py").read_text(), "value = 1\n")
