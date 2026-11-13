import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient
from leancode.api import create_app
from leancode.config import Settings
from leancode.agent import Agent


class ApiTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        settings = Settings(data_dir=Path(self.tmp.name), token="test-access-token",
                            repositories={"demo": {"path": self.tmp.name, "confidential": True}})
        self.app = create_app(settings)
        self.client = TestClient(self.app, base_url="http://localhost")
        self.auth = {"Authorization": "Bearer test-access-token"}

    def tearDown(self):
        self.client.close()
        self.tmp.cleanup()

    def test_auth_origin_and_host_enforced(self):
        self.assertEqual(self.client.get("/api/bootstrap").status_code, 401)
        self.assertEqual(self.client.get("/api/bootstrap", headers=self.auth).status_code, 200)
        self.assertEqual(self.client.get("/api/bootstrap", headers={**self.auth, "Origin": "https://evil.test"}).status_code, 403)
        self.assertEqual(self.client.get("/api/bootstrap", headers={**self.auth, "Host": "evil.test"}).status_code, 400)

    def test_vercel_origin_preflight_stream_and_host_are_explicit(self):
        settings = self.app.state.settings
        settings.allowed_hosts = ["leancode-api.onrender.com"]
        settings.browser_origins = ["https://leancode.vercel.app"]
        app = create_app(settings)
        headers = {**self.auth, "Origin": settings.browser_origins[0], "Sec-Fetch-Site": "cross-site"}
        sid, _ = app.state.store.create_session("demo", "fix bug")
        app.state.store.update(sid, status="blocked")
        with TestClient(app, base_url="https://leancode-api.onrender.com") as client:
            preflight = client.options("/api/sessions", headers={"Origin": settings.browser_origins[0],
                "Sec-Fetch-Site": "cross-site", "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "authorization,content-type"})
            self.assertEqual(preflight.status_code, 200)
            self.assertEqual(preflight.headers["access-control-allow-origin"], settings.browser_origins[0])
            self.assertEqual(client.get("/api/bootstrap", headers=headers).status_code, 200)
            stream = client.get(f"/api/sessions/{sid}/events", headers=headers)
            self.assertEqual(stream.status_code, 200)
            self.assertIn("data:", stream.text)
            self.assertEqual(client.get("/api/bootstrap", headers={"Origin": settings.browser_origins[0]}).status_code, 401)
            self.assertEqual(client.get("/api/bootstrap", headers={**headers, "Origin": "https://evil.vercel.app"}).status_code, 403)
            self.assertEqual(client.get("/api/health", headers={"Host": "evil.onrender.com"}).status_code, 400)

    def test_deployment_wildcards_and_non_https_origins_are_rejected(self):
        settings = self.app.state.settings
        for origin in ["*", "https://*.vercel.app", "http://leancode.vercel.app", "https://leancode.vercel.app/", "https://user:password@leancode.vercel.app"]:
            settings.browser_origins = [origin]
            with self.assertRaises(ValueError):
                create_app(settings)
        settings.browser_origins = []
        settings.allowed_hosts = ["*"]
        with self.assertRaises(ValueError):
            create_app(settings)

    def test_task_validation_and_session_ownership(self):
        response = self.client.post("/api/sessions", headers=self.auth,
                                    json={"repository": "../../private", "task": "fix a bug", "request_id": "a" * 20})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(self.client.get("/api/sessions/missing", headers=self.auth).status_code, 404)
        sid, _ = self.app.state.store.create_session("demo", "fix bug", user_id="another")
        self.assertEqual(self.client.get(f"/api/sessions/{sid}", headers=self.auth).status_code, 404)

    def test_approval_is_bound_to_action_and_resolved_once(self):
        store = self.app.state.store
        sid, _ = store.create_session("demo", "fix bug")
        aid = store.propose(sid, "patch", {"diff": "example"})
        url = f"/api/sessions/{sid}/actions/{aid}/decision"
        bad = self.client.post(url, headers=self.auth, json={"approve": "yes"})
        self.assertEqual(bad.status_code, 422)
        self.assertEqual(self.client.post(url, headers=self.auth, json={"approve": False}).status_code, 200)
        self.assertEqual(self.client.post(url, headers=self.auth, json={"approve": True}).status_code, 409)
        self.assertEqual(store.session(sid)["actions"][0]["status"], "rejected")

    def test_replay_after_terminal_session(self):
        store = self.app.state.store
        sid, _ = store.create_session("demo", "fix bug")
        store.update(sid, status="blocked")
        response = self.client.get(f"/api/sessions/{sid}/events?after=0", headers=self.auth)
        self.assertEqual(response.status_code, 200)
        self.assertIn("data:", response.text)
        self.assertIn("text/event-stream", response.headers["content-type"])

    def test_request_id_deduplicates_and_active_repository_is_locked(self):
        store = self.app.state.store
        sid, created = store.create_session("demo", "fix bug", request_id="unique")
        duplicate, created_again = store.create_session("demo", "fix bug", request_id="unique")
        self.assertTrue(created)
        self.assertFalse(created_again)
        self.assertEqual(sid, duplicate)
        with self.assertRaises(ValueError):
            store.create_session("demo", "other task")
        store.claim(sid)
        store.recover()
        self.assertEqual(store.session(sid)["status"], "interrupted")

    def test_separate_tokens_enforce_profile_ownership_and_limits(self):
        settings = self.app.state.settings
        settings.users = {"alice": {"token": "alice-private-token", "limit_micro": 100},
                          "bob": {"token": "bob-private-token", "limit_micro": 200}}
        app = create_app(settings)
        sid, _ = app.state.store.create_session("demo", "fix alice bug", user_id="alice")
        app.state.store.propose(sid, "patch", {"diff": "review"})
        with TestClient(app, base_url="http://localhost") as client:
            bob = {"Authorization": "Bearer bob-private-token"}
            self.assertEqual(client.get(f"/api/sessions/{sid}", headers=bob).status_code, 404)
            bootstrap = client.get("/api/bootstrap", headers=bob).json()
            self.assertEqual(bootstrap["sessions"], [])
            self.assertEqual(bootstrap["user"]["limit_micro"], 200)

    def test_non_local_worker_reaches_budget_policy_and_owned_event_replay(self):
        settings = self.app.state.settings
        settings.users = {"alice": {"token": "alice-private-token", "limit_micro": 0}}
        settings.repositories["demo"]["confidential"] = False
        settings.routes = [{"model": "test", "bounded_output": True, "input_rate": 1, "output_rate": 1}]
        app = create_app(settings)
        store = app.state.store
        sid, _ = store.create_session("demo", "fix alice bug", user_id="alice")
        from unittest.mock import patch
        with patch.dict("os.environ", {"LEANCODE_GATEWAY_SINGLE_ATTEMPT": "true"}):
            Agent(settings, store).run(sid)
        session = store.session(sid, "alice")
        self.assertEqual(session["status"], "blocked")
        self.assertTrue(any("Budget exhausted" in e["data"].get("message", "") for e in session["events"]))
        self.assertEqual(session["state"].get("model_calls", 0), 0)
        with TestClient(app, base_url="http://localhost") as client:
            auth = {"Authorization": "Bearer alice-private-token"}
            self.assertEqual(client.get(f"/api/sessions/{sid}/events", headers=auth).status_code, 200)
        with self.assertRaises(LookupError):
            store.session(sid, "bob")
