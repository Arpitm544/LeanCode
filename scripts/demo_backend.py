"""Isolated recording instance: real model calls, synthetic repos, no changes to live app data."""

import json
import socket
import secrets
import shutil
import uuid
from pathlib import Path

import uvicorn
from fastapi.staticfiles import StaticFiles

from leancode.api import create_app
from leancode.config import Settings

ROOT = Path(__file__).resolve().parents[1]


def main():
    with socket.socket() as check:
        check.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            check.bind(("127.0.0.1", 8002))
        except OSError:
            raise SystemExit("Port 8002 is busy; stop the previous demo server before starting another")
    original = Settings.load()
    if not original.routes:
        raise SystemExit("Configure a real model before recording; this instance never uses mock responses")
    data = ROOT / ".leancode" / "demo-recording" / uuid.uuid4().hex
    data.mkdir(parents=True, mode=0o700)
    repositories = {}
    for name, confidential in [("demo-python", False), ("confidential-demo", True)]:
        workspace = data / name
        shutil.copytree(ROOT / "benchmarks" / "tasks" / "boundary", workspace)
        repositories[name] = {"path": str(workspace), "confidential": confidential}
    token, budget_token = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
    settings = Settings(data_dir=data, token=token, repositories=repositories, routes=original.routes,
                        sandbox_image=original.sandbox_image,
                        users={"local": {"token": token, "limit_micro": 100000},
                               "budget-demo": {"token": budget_token, "limit_micro": 0}})
    app = create_app(settings, browser_origins=("http://127.0.0.1:8002",))
    app.mount("/", StaticFiles(directory=ROOT / "frontend" / "dist", html=True), name="frontend")
    config = ROOT / ".leancode" / "demo-recording" / "runtime.json"
    config.write_text(json.dumps({"url": "http://127.0.0.1:8002", "token": token,
                                  "budget_token": budget_token, "data_dir": str(data)}))
    config.chmod(0o600)
    print("Recording instance ready on 127.0.0.1:8002; real providers, public synthetic data, $0.10 cap.", flush=True)
    uvicorn.run(app, host="127.0.0.1", port=8002, log_level="warning")


if __name__ == "__main__":
    main()
