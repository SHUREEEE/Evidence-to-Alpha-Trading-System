import json
import tempfile
import threading
import unittest
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from evidence_alpha.api import ArtifactHandler


class ApiTests(unittest.TestCase):
    def test_read_only_api_serves_legacy_orders_and_standard_fills(self):
        with tempfile.TemporaryDirectory() as directory:
            artifact_dir = Path(directory)
            (artifact_dir / "report.json").write_text(
                json.dumps({"run_id": "INT-TEST"}), encoding="utf-8"
            )
            (artifact_dir / "paper_orders.json").write_text(
                json.dumps([{"order_id": "ORDER-1"}]), encoding="utf-8"
            )
            (artifact_dir / "fills.json").write_text(
                json.dumps([{"fill_id": "FILL-1", "order_id": "ORDER-1"}]),
                encoding="utf-8",
            )
            (artifact_dir / "independent_validation.json").write_text(
                json.dumps({"decision": "INCONCLUSIVE"}),
                encoding="utf-8",
            )
            (artifact_dir / "readiness.json").write_text(
                json.dumps({"decision": "BLOCKED"}),
                encoding="utf-8",
            )
            (artifact_dir / "event_study.csv").write_text(
                "event_ref,ticker,window_days,status\n"
                "E1:v1,NVDA,1,ok\n",
                encoding="utf-8",
            )
            handler = type(
                "TestArtifactHandler", (ArtifactHandler,), {"artifact_dir": artifact_dir}
            )
            server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            base_url = f"http://127.0.0.1:{server.server_port}"
            try:
                with urlopen(f"{base_url}/api/v1/runs/latest/orders", timeout=5) as response:
                    orders = json.load(response)
                with urlopen(f"{base_url}/api/v1/runs/latest/fills", timeout=5) as response:
                    fills = json.load(response)
                self.assertEqual(orders[0]["order_id"], "ORDER-1")
                self.assertEqual(fills[0]["fill_id"], "FILL-1")
                with urlopen(
                    f"{base_url}/api/v1/runs/latest/independent-validation",
                    timeout=5,
                ) as response:
                    independent = json.load(response)
                self.assertEqual(independent["decision"], "INCONCLUSIVE")
                with urlopen(
                    f"{base_url}/api/v1/runs/latest/readiness",
                    timeout=5,
                ) as response:
                    readiness = json.load(response)
                self.assertEqual(readiness["decision"], "BLOCKED")
                with urlopen(
                    f"{base_url}/api/v1/runs/latest/event-study",
                    timeout=5,
                ) as response:
                    event_study = json.load(response)
                self.assertEqual(event_study[0]["event_ref"], "E1:v1")
                self.assertEqual(event_study[0]["ticker"], "NVDA")

                request = Request(f"{base_url}/api/v1/runs/latest", method="POST")
                with self.assertRaises(HTTPError) as rejected:
                    urlopen(request, timeout=5)
                self.assertEqual(rejected.exception.code, 405)
                rejected.exception.close()
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=5)
