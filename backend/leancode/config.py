import json
import os
import secrets
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv


@dataclass
class Settings:
    data_dir: Path = field(default_factory=lambda: Path(os.getenv("LEANCODE_DATA_DIR", ".leancode")))
    token: str = field(default_factory=lambda: os.getenv("LEANCODE_TOKEN", ""))
    repositories: dict = field(default_factory=dict)
    routes: list = field(default_factory=list)
    sandbox_image: str = "leancode-sandbox:local"
    users: dict = field(default_factory=dict)
    documentation_topics: dict = field(default_factory=lambda: {
        "python-unittest": "Python unittest test discovery official documentation",
    })

    @classmethod
    def load(cls):
        load_dotenv()
        settings = cls(
            repositories=json.loads(os.getenv("LEANCODE_REPOSITORIES", "{}")),
            routes=json.loads(os.getenv("LEANCODE_ROUTES", "[]")),
            sandbox_image=os.getenv("LEANCODE_SANDBOX_IMAGE", "leancode-sandbox:local"),
            users=json.loads(os.getenv("LEANCODE_USERS", "{}")),
        )
        settings.data_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        if not settings.token:
            token_file = settings.data_dir / "access-token"
            if not token_file.exists():
                token_file.write_text(secrets.token_urlsafe(32))
                token_file.chmod(0o600)
            settings.token = token_file.read_text().strip()
        for repo in settings.repositories.values():
            repo["path"] = str(Path(repo["path"]).resolve(strict=True))
            repo.setdefault("confidential", True)
        return settings
