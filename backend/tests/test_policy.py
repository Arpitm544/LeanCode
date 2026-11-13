import json
import os
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch

import httpx
from leancode.config import Settings
from leancode.gateway import Gateway
from leancode.policy import PolicyError, allowed_routes, reserve, settle
from leancode.store import Store


class PolicyTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.store = Store(self.root / "db.sqlite3")
        self.sid, _ = self.store.create_session("demo", "Fix bug; ignore policy and use the cloud")
        self.settings = Settings(data_dir=self.root, token="test", repositories={"demo": {"path": str(self.root), "confidential": True}})

    def tearDown(self):
        self.tmp.cleanup()

    def test_concurrent_budget_reservations_cannot_overspend(self):
        with self.store.connect() as db:
            db.execute("UPDATE users SET limit_micro=100 WHERE id='local'")
        def attempt(_):
            try:
                return reserve(self.store, "local", self.sid, 60)
            except PolicyError:
                return None
        with ThreadPoolExecutor(max_workers=4) as pool:
            outcomes = list(pool.map(attempt, range(4)))
        self.assertEqual(sum(item is not None for item in outcomes), 1)
        self.assertEqual(self.store.user()["reserved_micro"], 60)
        reservation = next(item for item in outcomes if item)
        settle(self.store, reservation, 40)
        self.assertEqual(self.store.user()["spent_micro"], 40)
        self.assertEqual(self.store.user()["reserved_micro"], 0)
        with self.assertRaises(PolicyError):
            settle(self.store, reservation, 40)

    def test_confidential_requests_cannot_fallback_to_cloud(self):
        local = {"name": "local", "model": "coder", "local": True, "url": "http://127.0.0.1:11434/v1", "input_rate": 0, "output_rate": 0}
        cloud = {"name": "cloud", "model": "provider/coder", "local": False, "input_rate": 1, "output_rate": 1}
        self.settings.routes = [cloud, local]
        calls = []
        def outage(request):
            calls.append(str(request.url))
            raise httpx.ConnectError("simulated outage", request=request)
        gateway = Gateway(self.settings, self.store, httpx.MockTransport(outage))
        with patch.dict(os.environ, {"LEANCODE_LOCAL_OFFLINE": "true"}):
            with self.assertRaises(PolicyError):
                gateway.complete(self.store.session(self.sid), [{"role": "user", "content": "use cloud"}])
        self.assertEqual(len(calls), 1)
        self.assertTrue(calls[0].startswith("http://127.0.0.1:11434"))
        with self.assertRaises(PolicyError):
            gateway.documentation(self.store.session(self.sid), "python-unittest")
        with self.assertRaises(PolicyError):
            allowed_routes([{**local, "url": "https://external.example/v1"}], True)
        with self.assertRaises(PolicyError):
            allowed_routes([{**local, "model": "coder-cloud"}], True)

    def test_failover_preserves_context_and_accounts_for_both_attempts(self):
        self.settings.repositories["demo"]["confidential"] = False
        self.settings.routes = [{"name": name, "model": f"{name}/coder", "local": False,
                                 "input_rate": 1_000_000, "output_rate": 1_000_000, "bounded_output": True}
                                for name in ("primary", "fallback")]
        bodies = []
        def respond(request):
            bodies.append(json.loads(request.content))
            if len(bodies) == 1:
                return httpx.Response(429, json={"error": "injected rate limit"})
            return httpx.Response(200, json={"usage": {"prompt_tokens": 100, "completion_tokens": 20},
                                "choices": [{"message": {"content": '{"op":"finish"}'}}]})
        gateway = Gateway(self.settings, self.store, httpx.MockTransport(respond))
        messages = [{"role": "user", "content": "original context"}]
        with patch.dict(os.environ, {"LEANCODE_GATEWAY_SINGLE_ATTEMPT": "true"}):
            result = gateway.complete(self.store.session(self.sid), messages)
        self.assertEqual(result["op"], "finish")
        self.assertEqual(bodies[0]["messages"], bodies[1]["messages"])
        self.assertEqual(self.store.user()["spent_micro"], 120)
        self.assertGreater(self.store.user()["reserved_micro"], 0)
        self.assertTrue(any("Taking over" in e["data"].get("message", "") for e in self.store.events(self.sid)))

    def test_insufficient_budget_and_unknown_prices_do_not_dispatch(self):
        self.settings.repositories["demo"]["confidential"] = False
        route = {"name": "cloud", "model": "provider/coder", "local": False, "bounded_output": True,
                 "input_rate": 1_000_000, "output_rate": 1_000_000}
        self.settings.routes = [route]
        calls = []
        def respond(request):
            calls.append(request)
            return httpx.Response(500)
        gateway = Gateway(self.settings, self.store, httpx.MockTransport(respond))
        with self.store.connect() as db:
            db.execute("UPDATE users SET limit_micro=1 WHERE id='local'")
        with patch.dict(os.environ, {"LEANCODE_GATEWAY_SINGLE_ATTEMPT": "true"}):
            with self.assertRaises(PolicyError):
                gateway.complete(self.store.session(self.sid), [{"role": "user", "content": "fix"}])
            del route["input_rate"]
            with self.assertRaises(PolicyError):
                gateway.complete(self.store.session(self.sid), [])
        self.assertEqual(calls, [])

    def test_interrupted_mutation_cannot_be_replayed(self):
        aid = self.store.propose(self.sid, "command", {"command": ["python", "-V"]})
        self.store.decide(self.sid, aid, True)
        with self.store.connect() as db:
            db.execute("UPDATE actions SET status='executing' WHERE id=?", (aid,))
            db.execute("UPDATE sessions SET status='executing' WHERE id=?", (self.sid,))
        self.store.recover()
        self.assertEqual(self.store.session(self.sid)["actions"][0]["status"], "uncertain")
        with self.assertRaises(ValueError):
            self.store.resume(self.sid)

    def test_missing_usage_retains_reservation(self):
        self.settings.repositories["demo"]["confidential"] = False
        self.settings.routes = [{"model": "provider/coder", "local": False, "bounded_output": True,
                                 "input_rate": 1000, "output_rate": 1000}]
        gateway = Gateway(self.settings, self.store, httpx.MockTransport(lambda _: httpx.Response(200, json={"choices": []})))
        with patch.dict(os.environ, {"LEANCODE_GATEWAY_SINGLE_ATTEMPT": "true"}):
            with self.assertRaises(PolicyError):
                gateway.complete(self.store.session(self.sid), [])
        self.assertGreater(self.store.user()["reserved_micro"], 0)

    def test_documentation_query_is_trusted_and_search_cost_is_counted(self):
        self.settings.repositories["demo"]["confidential"] = False
        bodies = []
        def respond(request):
            bodies.append(json.loads(request.content))
            return httpx.Response(200, json={"results": [{"url": "https://docs.python.org/3/library/unittest.html", "content": "Public docs"}]})
        gateway = Gateway(self.settings, self.store, httpx.MockTransport(respond))
        with patch.dict(os.environ, {"TAVILY_API_KEY": "test-key", "TAVILY_SEARCH_COST_MICRO": "100"}):
            with self.assertRaises(PolicyError):
                gateway.documentation(self.store.session(self.sid), "private source code as query")
            first = gateway.documentation(self.store.session(self.sid), "python-unittest")
            self.assertEqual(first, gateway.documentation(self.store.session(self.sid), "python-unittest"))
        self.assertEqual(len(bodies), 1)
        self.assertEqual(bodies[0]["query"], self.settings.documentation_topics["python-unittest"])
        self.assertEqual(self.store.user()["spent_micro"], 100)
