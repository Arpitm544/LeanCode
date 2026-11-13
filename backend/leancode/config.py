import json
import os
import secrets
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlsplit

from dotenv import load_dotenv


@dataclass
class Settings:
    data_dir: Path = field(default_factory=lambda: Path(os.getenv("LEANCODE_DATA_DIR", ".leancode")))
    token: str = field(default_factory=lambda: os.getenv("LEANCODE_TOKEN", ""))
    repositories: dict = field(default_factory=dict)
    routes: list = field(default_factory=list)
    sandbox_image: str = "leancode-sandbox:local"
    users: dict = field(default_factory=dict)
    allowed_hosts: list[str] = field(default_factory=lambda: ["127.0.0.1", "localhost"])
    browser_origins: list[str] = field(default_factory=list)
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
            allowed_hosts=json.loads(os.getenv("LEANCODE_ALLOWED_HOSTS", '["127.0.0.1", "localhost"]')),
            browser_origins=json.loads(os.getenv("LEANCODE_BROWSER_ORIGINS", "[]")),
        )
        if os.getenv("RENDER_EXTERNAL_HOSTNAME"):
            settings.allowed_hosts.append(os.environ["RENDER_EXTERNAL_HOSTNAME"])
        settings.validate_web_access()
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

    def validate_web_access(self):
        if not isinstance(self.allowed_hosts, list) or not self.allowed_hosts or any(
            not isinstance(host, str) or not host or any(c in host for c in "*/:@?# ")
            for host in self.allowed_hosts
        ):
            raise ValueError("Allowed hosts must be explicit hostnames without wildcards")
        if not isinstance(self.browser_origins, list):
            raise ValueError("Browser origins must be a JSON list")
        for origin in self.browser_origins:
            if not isinstance(origin, str):
                raise ValueError("Browser origins must be exact HTTPS origins")
            parsed = urlsplit(origin)
            if (parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password
                    or parsed.path or parsed.query or parsed.fragment or "*" in origin):
                raise ValueError("Browser origins must be exact HTTPS origins without a trailing slash")
