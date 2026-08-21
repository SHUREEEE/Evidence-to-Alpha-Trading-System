from __future__ import annotations

from contextlib import redirect_stderr, redirect_stdout
from hashlib import sha256
from io import StringIO
from pathlib import Path
import json
import tempfile
import unittest

from evidence_alpha.artifact_inspection import build_panel_inspection_report
from evidence_alpha.cli import main as cli_main
from evidence_alpha.models import ContractError


class ArtifactInspectionCliTests(unittest.TestCase):
    def test_report_contains_digest_counts_and_safe_logical_path(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "weights.csv"
            content = (
                "date,ticker,weight\n"
                "2026-08-20,NVDA,0.1\n"
                "2026-08-21,TSM,-0.2\n"
            )
            source.write_text(content, encoding="utf-8")

            report = build_panel_inspection_report(
                source,
                "factor_weights",
                logical_path="production/weights.csv",
            )

            self.assertEqual(report["artifact"]["logical_path"], "production/weights.csv")
            self.assertEqual(
                report["artifact"]["sha256"],
                sha256(source.read_bytes()).hexdigest(),
            )
            self.assertEqual(report["artifact"]["size_bytes"], source.stat().st_size)
            self.assertEqual(report["content"]["coverage_start"], "2026-08-20")
            self.assertEqual(report["content"]["coverage_end"], "2026-08-21")
            self.assertEqual(report["content"]["row_count"], 2)
            self.assertEqual(report["content"]["ticker_count"], 2)
            self.assertIn(
                "point_in_time_universe_not_attested",
                report["limitations"],
            )
            self.assertNotIn(str(Path(directory)), json.dumps(report))

    def test_report_rejects_unsafe_logical_paths(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "weights.csv"
            source.write_text(
                "date,ticker,weight\n2026-08-20,NVDA,0.1\n",
                encoding="utf-8",
            )

            with self.assertRaisesRegex(ContractError, "relative path"):
                build_panel_inspection_report(
                    source,
                    "factor_weights",
                    logical_path="../weights.csv",
                )
            with self.assertRaisesRegex(ContractError, "relative path"):
                build_panel_inspection_report(
                    source,
                    "factor_weights",
                    logical_path=str(Path(directory) / "weights.csv"),
                )

    def test_cli_writes_machine_readable_report(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "prices.csv"
            output = root / "inspection.json"
            source.write_text(
                "date,ticker,total_return_index\n"
                "2026-08-20,NVDA,100\n"
                "2026-08-21,NVDA,101\n",
                encoding="utf-8",
            )
            stdout = StringIO()

            with redirect_stdout(stdout):
                exit_code = cli_main(
                    [
                        "inspect-panel",
                        "--input",
                        str(source),
                        "--kind",
                        "adjusted_prices",
                        "--logical-path",
                        "vendor/prices.csv",
                        "--output",
                        str(output),
                    ]
                )

            self.assertEqual(exit_code, 0)
            written = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(json.loads(stdout.getvalue()), written)
            self.assertEqual(written["content"]["value_field"], "total_return_index")
            self.assertIn("corporate_actions_not_attested", written["limitations"])

    def test_cli_fails_closed_for_raw_close(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "prices.csv"
            output = root / "inspection.json"
            source.write_text(
                "date,ticker,close\n2026-08-20,NVDA,100\n",
                encoding="utf-8",
            )
            stderr = StringIO()

            with redirect_stderr(stderr):
                exit_code = cli_main(
                    [
                        "inspect-panel",
                        "--input",
                        str(source),
                        "--kind",
                        "adjusted_prices",
                        "--output",
                        str(output),
                    ]
                )

            self.assertEqual(exit_code, 2)
            self.assertFalse(output.exists())
            error = json.loads(stderr.getvalue())
            self.assertEqual(error["decision"], "REJECT")
            self.assertIn("adj_close", error["error"])

    def test_cli_refuses_to_overwrite_input(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "weights.csv"
            original = "date,ticker,weight\n2026-08-20,NVDA,0.1\n"
            source.write_text(original, encoding="utf-8")

            with redirect_stderr(StringIO()):
                exit_code = cli_main(
                    [
                        "inspect-panel",
                        "--input",
                        str(source),
                        "--kind",
                        "factor_weights",
                        "--output",
                        str(source),
                    ]
                )

            self.assertEqual(exit_code, 2)
            self.assertEqual(source.read_text(encoding="utf-8"), original)
