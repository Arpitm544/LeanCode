"""Run the existing constrained Docker command inside a disposable Render microVM."""

import logging
import os
import shlex

from .policy import PolicyError


def execute(directory, args, timeout):
    required = ("RENDER_API_KEY", "RENDER_WORKSPACE_ID", "LEANCODE_RENDER_SNAPSHOT_ID", "LEANCODE_RENDER_SANDBOX_GROUP_ID")
    if any(not os.getenv(key) for key in required):
        raise PolicyError("Configure Render sandbox credentials and the prepared Docker snapshot before execution")
    from render import Render
    from render.sandbox import SandboxExecExit, SandboxExecOutput

    client = Render()
    sandbox_id = None
    try:
        box = client.sandboxes.create(snapshot_id=os.environ["LEANCODE_RENDER_SNAPSHOT_ID"],
            sandbox_group_id=os.environ["LEANCODE_RENDER_SANDBOX_GROUP_ID"],
            network_policy="deny-all", timeout_seconds=180, idle_timeout_seconds=300)
        sandbox_id = box.id
        box = client.sandboxes.wait_until_running(sandbox_id, timeout_seconds=45)
        if box.network_policy.type != "deny-all":
            raise PolicyError("Render did not confirm deny-all networking; no repository was uploaded")
        remote = "/home/render/leancode-workspace"
        client.sandboxes.copy_to(sandbox_id, directory, remote)
        mount = f"type=bind,src={directory},dst=/workspace,readonly"
        remote_args = [f"type=bind,src={remote},dst=/workspace,readonly" if arg == mount else arg for arg in args]
        remote_args.insert(2, "--pull=never")
        output, size, exit_code = [], 0, None
        for event in client.sandboxes.exec(sandbox_id, shlex.join(["timeout", str(timeout), *remote_args])):
            if isinstance(event, SandboxExecOutput):
                size += len(event.data.encode("utf-8"))
                if size >= 32_000:
                    raise PolicyError("Command output limit reached; Render sandbox stopped")
                output.append(event.data)
            elif isinstance(event, SandboxExecExit):
                exit_code = event.exit_code
        if type(exit_code) is not int:
            raise PolicyError("Render command ended without a verified exit code")
        if exit_code in {124, 137}:
            raise PolicyError("Command time limit reached; Render sandbox stopped")
        return {"exit_code": exit_code, "output": "".join(output)}
    except PolicyError:
        raise
    except Exception as exc:
        raise PolicyError("Render sandbox unavailable; no host command fallback is allowed") from exc
    finally:
        if sandbox_id:
            try:
                client.sandboxes.terminate(sandbox_id)
            except Exception:
                logging.getLogger(__name__).exception("Sandbox %s cleanup failed; its 180-second runtime limit remains", sandbox_id)
