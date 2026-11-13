import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

from leancode.context import Repository
from leancode.tools import apply_patch, patch_proposal

BENCHMARKS = Path(__file__).resolve().parents[2] / "benchmarks"


class BenchmarkTests(unittest.TestCase):
    def test_six_fixture_patches_match_and_task_names_are_unique(self):
        fixtures = json.loads((BENCHMARKS / "tasks.json").read_text())
        self.assertEqual(len(fixtures), 6)
        self.assertEqual(len({f["id"] for f in fixtures}), 6)
        import shutil
        for fixture in fixtures:
            with self.subTest(task=fixture["id"]), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp) / "workspace"
                shutil.copytree(BENCHMARKS / "tasks" / fixture["id"], root)
                repo = Repository(root)
                for edit in fixture["edits"]:
                    apply_patch(repo, patch_proposal(repo, edit["path"], edit["old"], edit["new"], "smoke"))
                self.assertTrue((BENCHMARKS / "acceptance" / fixture["id"] / "test_acceptance.py").is_file())

    def test_summary_does_not_turn_unknown_usage_into_zero(self):
        spec = importlib.util.spec_from_file_location("benchmark_run", BENCHMARKS / "run.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        result = module.summarize([{"variant": "baseline", "outcome": "failed", "tokens": None,
                                   "cost_micro": 12, "reserved_micro": 20}])
        self.assertIsNone(result["baseline"]["tokens"])
        self.assertEqual(result["baseline"]["successes"], 0)
        self.assertEqual(result["baseline"]["reported_cost_micro"], 12)
