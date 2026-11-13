import difflib
import os
import selectors
import shutil
import subprocess
import tempfile
import time
import uuid
from pathlib import Path

from .policy import PolicyError


def patch_proposal(repo, path, old, new, reason):
    destination = repo.path(path)
    before = repo.text(path) if destination.exists() else ""
    if old:
        if before.count(old) != 1:
            raise PolicyError("The exact old text must occur once; read the file again")
        after = before.replace(old, new, 1)
    elif destination.exists():
        raise PolicyError("Empty old text can only create a new file")
    else:
        after = new
    if after == before or len(after.encode()) > 96_000:
        raise PolicyError("Patch is empty or exceeds the supported file size")
    diff = "".join(difflib.unified_diff(before.splitlines(True), after.splitlines(True),
                                        fromfile=f"a/{path}", tofile=f"b/{path}"))
    return {"path": path, "before_hash": repo.hash(path), "after": after, "diff": diff, "reason": reason}


def apply_patch(repo, payload):
    path = repo.path(payload["path"])
    if repo.hash(payload["path"]) != payload["before_hash"]:
        raise PolicyError("File changed since approval was requested; propose a fresh patch")
    if not path.parent.is_dir():
        raise PolicyError("Create files only in existing directories in this MVP")
    with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent, delete=False) as handle:
        temp_path = Path(handle.name)
        try:
            handle.write(payload["after"])
            handle.flush()
            os.fsync(handle.fileno())
            temp_path.chmod(path.stat().st_mode & 0o777 if path.exists() else 0o644)
            if repo.hash(payload["path"]) != payload["before_hash"]:
                raise PolicyError("Concurrent edit detected; fresh review required")
            os.replace(temp_path, repo.path(payload["path"]))
        finally:
            temp_path.unlink(missing_ok=True)
    return {"message": f"Applied reviewed patch to {payload['path']}"}


def sandbox(repo, command, image, timeout=60):
    backend = os.getenv("LEANCODE_SANDBOX_BACKEND", "docker")
    if backend not in {"docker", "render"}:
        raise PolicyError("Unknown sandbox backend; execution blocked")
    if not command or len(command) > 30 or sum(map(len, command)) > 2000:
        raise PolicyError("Invalid command")
    name = f"leancode-{uuid.uuid4().hex}"
    with tempfile.TemporaryDirectory(prefix="leancode-sandbox-") as directory:
        total = 0
        for relative in repo.inventory():
            source = repo.path(relative)
            total += source.stat().st_size
            if total > 4_000_000:
                raise PolicyError("Sandbox snapshot exceeds the 4 MB MVP limit")
            destination = Path(directory) / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, destination)
            destination.chmod(0o644)
        Path(directory).chmod(0o755)
        args = ["docker", "run", "--rm", "--name", name, "--network=none", "--read-only",
                "--cap-drop=ALL", "--security-opt=no-new-privileges", "--pids-limit=64", "--memory=256m",
                "--cpus=1", "--user=65534:65534", "--tmpfs=/tmp:rw,noexec,nosuid,size=32m",
                "--mount", f"type=bind,src={directory},dst=/workspace,readonly", "--workdir=/workspace",
                "--env=PYTHONDONTWRITEBYTECODE=1", "--env=HOME=/tmp", image, *command]
        if backend == "render":
            from .render_sandbox import execute
            return execute(directory, args, timeout)
        process = None
        try:
            process = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                       env={"PATH": os.environ.get("PATH", "/usr/bin:/bin"),
                                            "HOME": os.environ.get("HOME", "")})
            selector = selectors.DefaultSelector()
            selector.register(process.stdout, selectors.EVENT_READ)
            output = bytearray()
            deadline = time.monotonic() + timeout
            while time.monotonic() < deadline:
                if selector.select(timeout=0.2):
                    chunk = os.read(process.stdout.fileno(), 4096)
                    if not chunk:
                        break
                    output.extend(chunk)
                    if len(output) >= 32_000:
                        raise PolicyError("Command output limit reached; container stopped")
                elif process.poll() is not None:
                    break
            else:
                raise PolicyError("Command time limit reached; container stopped")
            code = process.wait(timeout=5)
            return {"exit_code": code, "output": output.decode("utf-8", errors="replace")}
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise PolicyError("Docker sandbox unavailable; no host command fallback is allowed") from exc
        finally:
            if process and process.poll() is None:
                process.kill()
                process.wait(timeout=5)
            if process:
                process.stdout.close()
            if "selector" in locals():
                selector.close()
            try:
                subprocess.run(["docker", "rm", "-f", name], stdout=subprocess.DEVNULL,
                               stderr=subprocess.DEVNULL, timeout=10, check=False)
            except (OSError, subprocess.TimeoutExpired):
                pass
