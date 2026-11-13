"""Browser-test backend with explicitly scripted model replies. Never run against user repositories."""

import shutil
import tempfile
from pathlib import Path

import uvicorn
from leancode.agent import Agent
from leancode.api import create_app
from leancode.config import Settings
from leancode.store import Store


class BrowserTestGateway:
    def __init__(self):
        self.operations = iter([
            {"op": "read", "path": "maths.py"},
            {"op": "edit", "path": "maths.py", "old": "value >= 0", "new": "value > 0",
             "reason": "Scripted browser-test patch; no model inference"},
            {"op": "command", "command": ["python", "-m", "unittest", "discover", "-s", "tests", "-v"],
             "reason": "Verify the approved boundary fix"},
            {"op": "finish", "reason": "Scripted browser-test workflow completed"},
        ])

    def complete(self, session, messages):
        return next(self.operations)


def main():
    root = Path(__file__).resolve().parents[1]
    with tempfile.TemporaryDirectory(prefix="leancode-browser-test-") as tmp:
        workspace = Path(tmp) / "workspace"
        shutil.copytree(root / "benchmarks" / "tasks" / "boundary", workspace)
        settings = Settings(data_dir=Path(tmp) / "data", token="e2e-local-token",
                            repositories={"browser-test": {"path": str(workspace), "confidential": True}})
        store = Store(settings.data_dir / "leancode.sqlite3")
        agents = {}

        def run(session_id):
            if session_id not in agents:
                agents[session_id] = Agent(settings, store, gateway=BrowserTestGateway())
            store.update(session_id, model="Scripted browser test")
            agents[session_id].run(session_id)

        uvicorn.run(create_app(settings, runner=run, browser_origins=("http://127.0.0.1:5174",)),
                    host="127.0.0.1", port=8001, log_level="warning")


if __name__ == "__main__":
    main()
