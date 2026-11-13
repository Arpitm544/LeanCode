"""Prepare a code-free Docker snapshot for cloud tests; this consumes Render compute."""

import json
import os
import shlex
import shutil
import tempfile
from pathlib import Path

from dotenv import load_dotenv, set_key
from render import Render
from render.sandbox import SandboxExecExit, SandboxExecOutput

ROOT = Path(__file__).resolve().parents[1]


def main():
    load_dotenv(ROOT / ".env")
    if not os.getenv("RENDER_API_KEY") or not os.getenv("RENDER_WORKSPACE_ID"):
        raise SystemExit("Set RENDER_API_KEY and RENDER_WORKSPACE_ID in the private .env first")
    client, sandbox_id = Render(), None
    try:
        box = client.sandboxes.create(network_policy="allow-all", timeout_seconds=600, idle_timeout_seconds=300)
        sandbox_id = box.id
        client.sandboxes.wait_until_running(sandbox_id, timeout_seconds=60)
        with tempfile.TemporaryDirectory() as directory:
            shutil.copyfile(ROOT / "Dockerfile.sandbox", Path(directory) / "Dockerfile")
            client.sandboxes.copy_to(sandbox_id, directory, "/home/render/leancode-image")
        command = shlex.join(["timeout", "180", "docker", "build", "--pull", "-t", "leancode-sandbox:local", "/home/render/leancode-image"])
        exit_code = None
        for event in client.sandboxes.exec(sandbox_id, command):
            if isinstance(event, SandboxExecOutput):
                print(event.data, end="", flush=True)
            elif isinstance(event, SandboxExecExit):
                exit_code = event.exit_code
        if exit_code != 0:
            raise SystemExit("Docker image preparation failed; no snapshot was configured")
        snapshot = client.sandboxes.snapshots.create(sandbox_id, kind="runtime", wait=True)
        values = {"LEANCODE_RENDER_SNAPSHOT_ID": snapshot.id,
                  "LEANCODE_RENDER_SANDBOX_GROUP_ID": snapshot.sandbox_group_id}
        for key, value in values.items():
            set_key(str(ROOT / ".env"), key, value)
        (ROOT / ".env").chmod(0o600)
        data = ROOT / ".leancode"
        data.mkdir(exist_ok=True, mode=0o700)
        metadata = data / "render-sandbox.json"
        metadata.write_text(json.dumps({**values, "expires_at": snapshot.expires_at.isoformat()}, indent=2))
        metadata.chmod(0o600)
        print("Prepared a clean Docker runtime snapshot. IDs are saved privately; no repository or credentials were uploaded.")
    finally:
        if sandbox_id:
            client.sandboxes.terminate(sandbox_id)


if __name__ == "__main__":
    main()
