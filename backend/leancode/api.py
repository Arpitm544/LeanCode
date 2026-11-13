from contextlib import asynccontextmanager

from fastapi import FastAPI

from .config import Settings
from .store import Store


def create_app(settings=None):
    settings = settings or Settings.load()
    store = Store(settings.data_dir / "leancode.sqlite3")

    @asynccontextmanager
    async def lifespan(app):
        yield

    app = FastAPI(title="LeanCode", lifespan=lifespan)
    app.state.settings = settings
    app.state.store = store

    @app.get("/api/health")
    def health():
        return {"status": "ok", "service": "leancode", "version": "0.1.0"}

    return app
