import tempfile
import unittest
from pathlib import Path

from leancode.store import Store


class StoreTests(unittest.TestCase):
    def test_events_survive_reopen_and_replay(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "state.sqlite3"
            store = Store(path)
            store.event("one", "started", {"message": "hello"})
            store.event("two", "started", {})
            reopened = Store(path)
            events = reopened.events("one")
            self.assertEqual(events[0]["data"]["message"], "hello")
            self.assertEqual(reopened.events("one", events[0]["id"]), [])
