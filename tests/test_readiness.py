from __future__ import annotations

from datetime import date, timedelta
from hashlib import sha256
import json
from pathlib import Path
import tempfile
import unittest

from evidence_alpha.cli import main as cli_main
from evidence_alpha.independent_validation import REQUIRED_SCENARIOS
from evidence_alpha.readiness import (
    REQUIRED_RESEARCH_GATES,
    evaluate_release_readiness,
)


def _write_json(path: Path, payload: object) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return path


def _digest(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()


def _business_dates(start: date, count: int) -> list[str]:
    result: list[str] = []
    cursor = start
    while len(result) < count:
        if cursor.weekday() < 5:
            result.append(cursor.isoformat())
        cursor += timedelta(days=1)
    return result


def _positive_bundle(root: Path) -> dict[str, Path]:
    artifacts = root / "integration"
    production = root / "production"
    production.mkdir()
    weights = production / "weights.csv"
    prices = production / "prices.csv"
    borrow = production / "borrow.csv"
    weights.write_text("date,ticker,weight\n2026-03-01,NVDA,0.1\n", encoding="utf-8")
    prices.write_text(
        "date,ticker,adj_close\n2026-03-01,NVDA,100\n2026-03-02,NVDA,101\n",
        encoding="utf-8",
    )
    borrow.write_text(
        "date,symbol,locate_available_shares\n2026-03-01,NVDA,1000\n",
        encoding="utf-8",
    )

    visible = []
    evidence = []
    source_urls = {}
    for index in range(30):
        event_id = f"E{index:02d}"
        event_ref = f"{event_id}:v1"
        observed = date(2026, 1, 1) + timedelta(days=index)
        evidence_id = f"EV{index:02d}"
        url = f"https://news{index}.trusted-source.com/item/{index}"
        visible.append(
            {
                "event_id": event_id,
                "event_version": 1,
                "observed_at": f"{observed.isoformat()}T12:00:00+00:00",
                "evidence_ids": [evidence_id],
            }
        )
        evidence.append(
            {
                "evidence_id": evidence_id,
                "source_url": url,
                "captured_at": f"{observed.isoformat()}T12:01:00+00:00",
                "source_name": f"Source {index}",
            }
        )
        source_urls[event_ref] = [url]

    validation = {
        "decision": "PROMOTE",
        "config": {
            "data_classification": "real",
            "minimum_events": 30,
            "minimum_oos_events": 10,
            "rolling_folds": 3,
        },
        "counts": {
            "usable_primary_window_events": 30,
            "out_of_sample_events": 10,
        },
        "gates": [
            {"name": name, "passed": True, "severity": "research"}
            for name in sorted(REQUIRED_RESEARCH_GATES)
        ],
        "scenario_returns": {name: 0.01 for name in REQUIRED_SCENARIOS},
    }
    report = {
        "run_id": "INT-REAL-001",
        "asof": "2026-03-01T20:00:00+00:00",
        "hard_failures": [],
        "gates": {
            "factor_asof_not_future": True,
            "t_plus_one_prices": True,
        },
        "factor_inputs": {
            "weights": str(weights),
            "prices": str(prices),
        },
        "comparisons": {
            "factor_baseline": {
                "status": "ok",
                "return_end_date": "2026-03-02",
            }
        },
        "news_manifest": {
            "synthetic": False,
            "synthetic_event_refs": [],
            "placeholder_mapping_refs": [],
            "contract_degradations_by_event_version": {},
            "source_urls_by_event_version": source_urls,
        },
    }
    _write_json(artifacts / "report.json", report)
    _write_json(artifacts / "independent_validation.json", validation)
    _write_json(
        artifacts / "audit.json",
        {
            "gates": [
                {
                    "name": "integration_integrity",
                    "passed": True,
                    "severity": "hard",
                }
            ]
        },
    )
    _write_json(artifacts / "visible_events.json", visible)
    _write_json(artifacts / "news_export" / "evidence.json", {"evidence": evidence})

    factor_attestation = _write_json(
        root / "factor_attestation.json",
        {
            "schema_version": "1.0",
            "attestation_type": "factor_weights",
            "artifact": {
                "sha256": _digest(weights),
                "coverage_start": "2025-12-01",
                "coverage_end": "2026-03-02",
            },
            "production": {
                "synthetic": False,
                "source_repository": "SHUREEEE/multi-factor-alpha-platform",
                "source_commit": "a" * 40,
                "pipeline_run_id": "MF-RUN-001",
                "generated_at": "2026-03-02T02:00:00+00:00",
            },
            "quality": {
                "point_in_time": True,
                "universe_membership_point_in_time": True,
                "unresolved_exceptions": [],
            },
        },
    )
    price_attestation = _write_json(
        root / "price_attestation.json",
        {
            "schema_version": "1.0",
            "attestation_type": "corporate_action_safe_prices",
            "artifact": {
                "sha256": _digest(prices),
                "coverage_start": "2025-12-01",
                "coverage_end": "2026-03-02",
            },
            "production": {
                "synthetic": False,
                "provider": "Licensed Market Data Vendor",
                "dataset": "US Total Return Daily",
                "retrieved_at": "2026-03-02T02:05:00+00:00",
            },
            "adjustments": {
                "price_field": "adj_close",
                "splits": True,
                "cash_dividends": True,
                "special_dividends": True,
            },
            "quality": {
                "delistings_represented": True,
                "unresolved_exceptions": [],
            },
        },
    )
    pb_validation = _write_json(
        root / "pb_validation.json",
        {
            "pass_fail": True,
            "failures": [],
            "borrow_feed": str(borrow),
            "borrow_feed_sha256": _digest(borrow),
            "asof": "2026-03-01",
            "required_symbols_count": 1,
            "missing_required_symbols": [],
            "stale_symbols": [],
            "required_zero_locate_symbols": [],
            "max_age_days": 1,
            "reason": "PASS",
        },
    )
    pb_dry_run = _write_json(
        root / "pb_dry_run.json",
        {
            "workflow": "v4_pb_live_dry_run",
            "status": "PASS",
            "asof": "2026-03-01",
            "borrow_feed": str(borrow),
            "borrow_feed_sha256": _digest(borrow),
            "pipeline_exit_code": 0,
            "synthetic_borrow_used": False,
        },
    )
    pb_bundle = _write_json(
        root / "pb_bundle.json",
        {
            "workflow": "v4_launch_evidence_bundle",
            "status": "READY",
            "asof": "2026-03-01",
            "borrow_feed_sha256": _digest(borrow),
            "pb_dry_run_exit_code": 0,
            "go_no_go_exit_code": 0,
            "synthetic_borrow_used": False,
        },
    )

    paper_dir = root / "paper"
    session_dates = _business_dates(date(2026, 1, 5), 20)
    session_rows = []
    for session_date in session_dates:
        session_artifact = _write_json(
            paper_dir / "sessions" / f"{session_date}.json",
            {
                "session_date": session_date,
                "mode": "PAPER",
                "status": "PASS",
                "run_id": f"PAPER-{session_date}",
                "reconciliation": {
                    "closed_to_cent": True,
                    "unreconciled_items": 0,
                },
                "data_freshness": {"passed": True},
                "exceptions": [],
            },
        )
        session_rows.append(
            {
                "session_date": session_date,
                "artifact": str(session_artifact),
                "sha256": _digest(session_artifact),
            }
        )
    paper_manifest = _write_json(
        paper_dir / "manifest.json",
        {
            "schema_version": "1.0",
            "mode": "PAPER",
            "market_calendar": "XNYS",
            "calendar_source": {
                "name": "exchange-calendars",
                "version": "2026.1",
                "generated_at": "2026-02-01T00:00:00+00:00",
            },
            "expected_session_dates": session_dates,
            "missing_session_dates": [],
            "sessions": session_rows,
            "exceptions": [],
        },
    )
    return {
        "artifacts": artifacts,
        "factor": factor_attestation,
        "price": price_attestation,
        "pb_validation": pb_validation,
        "pb_dry_run": pb_dry_run,
        "pb_bundle": pb_bundle,
        "paper": paper_manifest,
        "borrow": borrow,
        "first_paper_session": Path(session_rows[0]["artifact"]),
    }


def _evaluate(paths: dict[str, Path]):
    return evaluate_release_readiness(
        artifact_dir=paths["artifacts"],
        factor_attestation_path=paths["factor"],
        price_attestation_path=paths["price"],
        pb_validation_path=paths["pb_validation"],
        pb_dry_run_manifest_path=paths["pb_dry_run"],
        pb_launch_bundle_path=paths["pb_bundle"],
        paper_manifest_path=paths["paper"],
    )


class ReadinessTests(unittest.TestCase):
    def test_complete_evidence_reaches_authorization_review_only(self):
        with tempfile.TemporaryDirectory() as directory:
            paths = _positive_bundle(Path(directory))
            report = _evaluate(paths)

            self.assertEqual(
                report["decision"], "READY_FOR_LIVE_AUTHORIZATION_REVIEW"
            )
            self.assertFalse(report["hard_failures"])
            self.assertEqual(report["authorization"]["live_trading"], "NOT_GRANTED")
            self.assertEqual(report["counts"]["paper_sessions"], 20)

    def test_real_label_alone_cannot_clear_provenance_gates(self):
        with tempfile.TemporaryDirectory() as directory:
            paths = _positive_bundle(Path(directory))
            report = evaluate_release_readiness(artifact_dir=paths["artifacts"])

            self.assertEqual(report["decision"], "BLOCKED")
            self.assertIn("factor_artifact_hash", report["hard_failures"])
            self.assertIn("corporate_action_safe_prices", report["hard_failures"])
            self.assertIn("pb_borrow_validation", report["hard_failures"])
            self.assertIn("continuous_paper_sessions", report["hard_failures"])

    def test_changed_paper_artifact_breaks_hash_and_reconciliation_gate(self):
        with tempfile.TemporaryDirectory() as directory:
            paths = _positive_bundle(Path(directory))
            paths["first_paper_session"].write_text("{}\n", encoding="utf-8")
            report = _evaluate(paths)

            self.assertEqual(report["decision"], "BLOCKED")
            self.assertIn(
                "continuous_paper_reconciliation", report["hard_failures"]
            )

    def test_changed_pb_feed_breaks_attested_hash_crosscheck(self):
        with tempfile.TemporaryDirectory() as directory:
            paths = _positive_bundle(Path(directory))
            paths["borrow"].write_text(
                "date,symbol,locate_available_shares\n"
                "2026-03-01,NVDA,0\n",
                encoding="utf-8",
            )
            report = _evaluate(paths)

            self.assertEqual(report["decision"], "BLOCKED")
            self.assertIn("pb_real_feed_crosscheck", report["hard_failures"])

    def test_changed_news_enrichment_breaks_provenance_gate(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            paths = _positive_bundle(root)
            database_input = _write_json(
                root / "production" / "news-claws.db.json",
                {"snapshot": "immutable"},
            )
            events_input = _write_json(
                root / "production" / "news-events.json",
                [{"event_id": "E00", "event_version": 1}],
            )
            input_artifacts = [
                {
                    "artifact_type": "news_claws_sqlite_snapshot",
                    "artifact": database_input.name,
                    "sha256": _digest(database_input),
                },
                {
                    "artifact_type": "news_export_events",
                    "artifact": events_input.name,
                    "sha256": _digest(events_input),
                },
            ]
            enrichment_payload = {
                "schema_version": "1.0",
                "enrichment_type": "news_event_enrichment",
                "generated_at": "2026-01-02T00:00:00+00:00",
                "source": {
                    "synthetic": False,
                    "repository": "SHUREEEE/News_Claws",
                    "commit": "a" * 40,
                    "pipeline_run_id": "NEWS-RUN-001",
                    "methodology": "PIT production novelty scoring",
                    "input_artifacts": input_artifacts,
                },
                "events": [
                    {
                        "event_id": "E00",
                        "event_version": 1,
                        "available_at": "2026-01-01T13:00:00+00:00",
                        "source_urls": [
                            "https://news0.trusted-source.com/item/0"
                        ],
                        "novelty": 0.8,
                        "mappings": [],
                    }
                ],
            }
            enrichment = _write_json(
                root / "production" / "news_enrichment.json",
                enrichment_payload,
            )
            report_path = paths["artifacts"] / "report.json"
            integration_report = json.loads(
                report_path.read_text(encoding="utf-8")
            )
            integration_report["news_manifest"]["enrichment"] = {
                "schema_version": "1.0",
                "artifact": str(enrichment),
                "sha256": _digest(enrichment),
                "synthetic": False,
                "source_repository": "SHUREEEE/News_Claws",
                "source_commit": "a" * 40,
                "pipeline_run_id": "NEWS-RUN-001",
                "methodology": "PIT production novelty scoring",
                "input_artifacts": [
                    {
                        **item,
                        "artifact": str(
                            (root / "production" / item["artifact"]).resolve()
                        ),
                    }
                    for item in input_artifacts
                ],
                "selection": {
                    "policy": "all_requested",
                    "requested_event_refs": ["E00:v1"],
                    "enriched_event_refs": ["E00:v1"],
                    "unresolved_event_refs": [],
                },
                "generated_at": "2026-01-02T00:00:00+00:00",
                "applied_event_refs": ["E00:v1"],
                "unresolved_event_refs": [],
            }
            _write_json(report_path, integration_report)

            initial = _evaluate(paths)
            self.assertEqual(
                initial["decision"], "READY_FOR_LIVE_AUTHORIZATION_REVIEW"
            )

            original_events_input = events_input.read_text(encoding="utf-8")
            events_input.write_text(
                f"{original_events_input} ",
                encoding="utf-8",
            )
            input_tampered = _evaluate(paths)
            self.assertEqual(input_tampered["decision"], "BLOCKED")
            self.assertIn(
                "news_enrichment_provenance",
                input_tampered["hard_failures"],
            )
            events_input.write_text(original_events_input, encoding="utf-8")
            self.assertEqual(
                _evaluate(paths)["decision"],
                "READY_FOR_LIVE_AUTHORIZATION_REVIEW",
            )

            enrichment.write_text(
                json.dumps(enrichment_payload, indent=4),
                encoding="utf-8",
            )
            report = _evaluate(paths)

            self.assertEqual(report["decision"], "BLOCKED")
            self.assertIn(
                "news_enrichment_provenance", report["hard_failures"]
            )

    def test_malformed_numeric_and_datetime_fields_fail_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            paths = _positive_bundle(Path(directory))
            validation_path = paths["artifacts"] / "independent_validation.json"
            validation = json.loads(validation_path.read_text(encoding="utf-8"))
            validation["counts"]["usable_primary_window_events"] = "not-an-integer"
            validation_path.write_text(
                json.dumps(validation, indent=2), encoding="utf-8"
            )
            visible_path = paths["artifacts"] / "visible_events.json"
            visible = json.loads(visible_path.read_text(encoding="utf-8"))
            visible[0]["observed_at"] = "not-a-datetime"
            visible_path.write_text(json.dumps(visible, indent=2), encoding="utf-8")
            report = _evaluate(paths)

            self.assertEqual(report["decision"], "BLOCKED")
            self.assertIn("primary_event_sample", report["hard_failures"])
            self.assertIn("input_contract_valid", report["hard_failures"])
            self.assertTrue(
                any("invalid primary event count" in item for item in report["input_errors"])
            )
            self.assertTrue(
                any("invalid observed_at" in item for item in report["input_errors"])
            )

    def test_cli_writes_machine_readable_report(self):
        with tempfile.TemporaryDirectory() as directory:
            paths = _positive_bundle(Path(directory))
            output = Path(directory) / "readiness.json"
            result = cli_main(
                [
                    "readiness",
                    "--artifact-dir",
                    str(paths["artifacts"]),
                    "--factor-attestation",
                    str(paths["factor"]),
                    "--price-attestation",
                    str(paths["price"]),
                    "--pb-validation",
                    str(paths["pb_validation"]),
                    "--pb-dry-run-manifest",
                    str(paths["pb_dry_run"]),
                    "--pb-launch-bundle",
                    str(paths["pb_bundle"]),
                    "--paper-manifest",
                    str(paths["paper"]),
                    "--output",
                    str(output),
                ]
            )

            self.assertEqual(result, 0)
            self.assertEqual(
                json.loads(output.read_text(encoding="utf-8"))["decision"],
                "READY_FOR_LIVE_AUTHORIZATION_REVIEW",
            )
