import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient
from leancode.api import create_app
from leancode.config import Settings


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
