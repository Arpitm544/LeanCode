import asyncio
import json
import os
import secrets
from contextlib import asynccontextmanager
from typing import Literal

from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, ConfigDict, Field, StrictBool
from starlette.middleware.trustedhost import TrustedHostMiddleware

from .agent import Agent
from .config import Settings
from .store import Store


class TaskRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    repository: str = Field(min_length=1, max_length=100)
    task: str = Field(min_length=5, max_length=12000)
    mode: Literal["baseline", "context", "optimized"] = "optimized"
    request_id: str = Field(min_length=16, max_length=64)


class Decision(BaseModel):
    model_config = ConfigDict(extra="forbid")
    approve: StrictBool


def create_app(settings=None, runner=None):
    settings = settings or Settings.load()
    store = Store(settings.data_dir / "leancode.sqlite3")
    runner = runner or Agent(settings, store).run
    workers = set()

    @asynccontextmanager
    async def lifespan(app):
        store.recover()
        yield
        # Workers are bounded; an in-progress action remains uncertain after restart.
        for worker in workers:
            worker.cancel()

    app = FastAPI(title="LeanCode", lifespan=lifespan, docs_url=None, redoc_url=None)
    app.state.settings, app.state.store = settings, store
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=["127.0.0.1", "localhost"])

    @app.middleware("http")
    async def local_origin(request, call_next):
        origin = request.headers.get("origin")
        if origin and origin not in {"http://127.0.0.1:5173", "http://localhost:5173",
                                     "http://127.0.0.1:8000", "http://localhost:8000"}:
            return JSONResponse({"detail": "Untrusted browser origin"}, status_code=403)
        if request.headers.get("sec-fetch-site") == "cross-site":
            return JSONResponse({"detail": "Cross-site requests are forbidden"}, status_code=403)
        return await call_next(request)

    def authenticate(authorization: str = Header(default="")):
        if not secrets.compare_digest(authorization, f"Bearer {settings.token}"):
            raise HTTPException(401, "Enter your local backend access token")
        return "local"

    def owned(session_id, user):
        try:
            return store.session(session_id, user)
        except LookupError:
            raise HTTPException(404, "Session not found") from None

    async def work(session_id):
        if not store.claim(session_id):
            return
        try:
            await asyncio.to_thread(runner, session_id)
        except Exception:
            store.event(session_id, "error", {"message": "Worker failed; session saved. Check local backend logs."})
            store.update(session_id, status="failed")

    def schedule(session_id):
        worker = asyncio.create_task(work(session_id))
        workers.add(worker)
        worker.add_done_callback(workers.discard)

    @app.get("/api/health")
    def health():
        return {"status": "ok", "service": "leancode", "version": "0.1.0"}

    @app.get("/api/bootstrap")
    def bootstrap(user=Depends(authenticate)):
        return {
            "repositories": [{"id": key, "name": key, "confidential": repo.get("confidential", True)}
                             for key, repo in settings.repositories.items()],
            "user": store.user(user), "sessions": store.sessions(user),
            "integrations": [
                {"name": "Bifrost", "configured": any(not r.get("local") for r in settings.routes),
                 "detail": "Cloud gateway · configuration only"},
                {"name": "Ollama", "configured": any(r.get("local") for r in settings.routes),
                 "detail": "Local inference · configuration only"},
                {"name": "Tavily", "configured": bool(os.getenv("TAVILY_API_KEY")),
                 "detail": "Public documentation search"},
            ],
        }

    @app.post("/api/sessions", status_code=201)
    async def create_session(task: TaskRequest, user=Depends(authenticate)):
        if task.repository not in settings.repositories:
            raise HTTPException(400, "Select a registered repository")
        if not task.task.strip():
            raise HTTPException(422, "Task cannot be blank")
        try:
            session_id, created = store.create_session(task.repository, task.task, task.mode, user, task.request_id)
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from None
        if created:
            schedule(session_id)
        return owned(session_id, user)

    @app.get("/api/sessions/{session_id}")
    def session(session_id: str, user=Depends(authenticate)):
        return owned(session_id, user)

    @app.post("/api/sessions/{session_id}/actions/{action_id}/decision")
    async def decide(session_id: str, action_id: str, decision: Decision, user=Depends(authenticate)):
        owned(session_id, user)
        try:
            store.decide(session_id, action_id, decision.approve)
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from None
        if decision.approve:
            schedule(session_id)
        return {"approved": decision.approve}

    @app.post("/api/sessions/{session_id}/resume")
    async def resume(session_id: str, user=Depends(authenticate)):
        owned(session_id, user)
        try:
            store.resume(session_id)
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from None
        schedule(session_id)
        return owned(session_id, user)

    @app.get("/api/sessions/{session_id}/events")
    async def events(session_id: str, request: Request, after: int = 0, user=Depends(authenticate)):
        owned(session_id, user)

        async def stream():
            cursor = max(0, after)
            while not await request.is_disconnected():
                page = store.events(session_id, cursor)
                for event in page:
                    cursor = event["id"]
                    yield f"id: {cursor}\ndata: {json.dumps(event)}\n\n"
                if not page:
                    yield ": keep-alive\n\n"
                if not page and store.session(session_id)["status"] in {
                    "completed", "failed", "rejected", "blocked", "interrupted"
                }:
                    return
                await asyncio.sleep(0.5)

        return StreamingResponse(stream(), media_type="text/event-stream",
                                 headers={"Cache-Control": "no-cache, no-store", "X-Accel-Buffering": "no"})

    @app.get("/api/benchmarks")
    def benchmarks(user=Depends(authenticate)):
        report = settings.data_dir / "benchmark-results.json"
        return json.loads(report.read_text()) if report.exists() else []

    return app
