"""Start one persisted Render API instance; never reset existing workspaces or budgets."""

import json
import os
import shutil
from pathlib import Path

import uvicorn
from leancode.api import create_app
from leancode.config import Settings

ROOT = Path(__file__).resolve().parents[1]


def app():
    data = Path(os.environ["LEANCODE_DATA_DIR"])
    data.mkdir(parents=True, exist_ok=True, mode=0o700)
    for name in ("demo-python", "confidential-demo"):
        workspace = data / name
        if not workspace.exists():
            temporary = data / f".{name}-seed"
            shutil.rmtree(temporary, ignore_errors=True)
            shutil.copytree(ROOT / "benchmarks" / "tasks" / "boundary", temporary)
            temporary.rename(workspace)
    os.environ.setdefault("LEANCODE_REPOSITORIES", json.dumps({
        "demo-python": {"path": str(data / "demo-python"), "confidential": False},
        "confidential-demo": {"path": str(data / "confidential-demo"), "confidential": True},
    }))
    if os.getenv("BIFROST_HOSTPORT"):
        os.environ["BIFROST_URL"] = f"http://{os.environ['BIFROST_HOSTPORT']}/openai"
    if os.getenv("LEANCODE_BIFROST_VIRTUAL_KEY"):
        os.environ["BIFROST_KEY"] = os.environ["LEANCODE_BIFROST_VIRTUAL_KEY"]
    return create_app(Settings.load())


if __name__ == "__main__":
    uvicorn.run(app(), host="0.0.0.0", port=int(os.getenv("PORT", "10000")),
                proxy_headers=True, forwarded_allow_ips="127.0.0.1", workers=1)
