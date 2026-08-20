import json
import tempfile
import unittest
from pathlib import Path

from evidence_alpha.demo import run_demo
from evidence_alpha.pipeline import config_from_cutoff


class PipelineTests(unittest.TestCase):
    def test_demo_produces_traceable_inconclusive_run(self):
        with tempfile.TemporaryDirectory() as directory:
            report = run_demo(directory)
            self.assertEqual(report["decision"], "INCONCLUSIVE")
            self.assertGreater(report["counts"]["signals"], 0)
            self.assertTrue(report["paper_oms"]["reconciliation"]["closed_to_cent"])
            signals = json.loads((Path(directory) / "signals.json").read_text(encoding="utf-8"))
            self.assertTrue(all(item["event_version"] == 2 or item["event_id"] == "EVT-20260115-002" for item in signals))
            self.assertTrue((Path(directory) / "ledger.sqlite3").exists())
            validation = json.loads(
                (Path(directory) / "independent_validation.json").read_text(
                    encoding="utf-8"
                )
            )
            self.assertEqual(validation["decision"], "INCONCLUSIVE")
            self.assertFalse(
                next(
                    gate
                    for gate in validation["gates"]
                    if gate["name"] == "real_data_classification"
                )["passed"]
            )
