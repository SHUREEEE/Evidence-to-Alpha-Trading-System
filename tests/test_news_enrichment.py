from __future__ import annotations

import csv
from datetime import datetime, timezone
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from evidence_alpha.cli import main as cli_main
from evidence_alpha.contracts import load_mappings
from evidence_alpha.models import ContractError, EventSnapshot, EvidenceRecord
from evidence_alpha.news_adapter import NewsExport
from evidence_alpha.news_enrichment import apply_news_enrichment
from evidence_alpha.signals import SignalConfig, generate_signals


DEGRADATIONS = [
    "industry_mapping_contains_encoding_replacement",
    "no_investable_company_or_industry_mapping",
    "novelty_not_exposed_by_api",
    "published_at_fell_back_to_first_seen",
]


def _bundle() -> NewsExport:
    event = EventSnapshot.from_dict(
        {
            "event_id": "E1",
            "event_version": 1,
            "published_at": "2026-08-19T09:00:00Z",
            "observed_at": "2026-08-19T09:05:00Z",
            "event_type": "news_event",
            "direction": "positive",
            "confidence": 0.8,
            "novelty": 0.0,
            "conflict": False,
            "impact_horizon_days": 20,
            "entities": [],
            "sectors": ["__UNMAPPED__"],
            "evidence_ids": ["EV1"],
            "status": "confirmed",
            "asof": "2026-08-19T09:05:00Z",
        }
    )
    return NewsExport(
        events=[event],
        evidence={
            "EV1": EvidenceRecord.from_dict(
                {
                    "evidence_id": "EV1",
                    "source_url": "https://www.sec.gov/news/press-release",
                    "captured_at": "2026-08-19T09:05:00Z",
                    "source_name": "SEC",
                }
            )
        },
        mappings=[],
        manifest={
            "synthetic": False,
            "placeholder_mapping_refs": ["E1:v1"],
            "contract_degradations_by_event_version": {
                "E1:v1": list(DEGRADATIONS)
            },
            "source_urls_by_event_version": {
                "E1:v1": ["https://www.sec.gov/news/press-release"]
            },
        },
    )


def _payload() -> dict[str, object]:
    return {
        "schema_version": "1.0",
        "enrichment_type": "news_event_enrichment",
        "generated_at": "2026-08-19T10:30:00Z",
        "source": {
            "synthetic": False,
            "repository": "SHUREEEE/News_Claws",
            "commit": "a" * 40,
            "pipeline_run_id": "NEWS-RUN-20260819-001",
            "methodology": "PIT article scoring and effective-dated issuer mapping",
        },
        "events": [
            {
                "event_id": "E1",
                "event_version": 1,
                "available_at": "2026-08-19T10:00:00Z",
                "source_urls": [
                    "https://www.sec.gov/news/press-release",
                    "https://www.nasdaq.com/market-activity/stocks/nvda",
                ],
                "published_at": "2026-08-19T08:55:00Z",
                "novelty": 0.8,
                "mappings": [
                    {
                        "entity": "NVIDIA",
                        "ticker": "NVDA",
                        "sector": "Technology",
                        "impact_multiplier": 1.0,
                        "effective_from": "2020-01-01",
                        "effective_to": None,
                        "source_url": "https://www.sec.gov/edgar/browse/?CIK=1045810",
                    }
                ],
            }
        ],
    }


def _write_payload(root: Path, payload: dict[str, object]) -> Path:
    path = root / "news_enrichment.json"
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return path


class NewsEnrichmentTests(unittest.TestCase):
    def test_complete_enrichment_clears_degradations_and_produces_signal(self):
        with tempfile.TemporaryDirectory() as directory:
            enriched = apply_news_enrichment(
                _bundle(), _write_payload(Path(directory), _payload())
            )

        event = enriched.events[0]
        self.assertEqual(event.published_at.isoformat(), "2026-08-19T08:55:00+00:00")
        self.assertEqual(event.observed_at.isoformat(), "2026-08-19T10:00:00+00:00")
        self.assertEqual(event.asof.isoformat(), "2026-08-19T10:00:00+00:00")
        self.assertEqual(event.novelty, 0.8)
        self.assertEqual(event.entities, ("NVIDIA",))
        self.assertEqual(event.sectors, ())
        self.assertEqual({item.ticker for item in enriched.mappings}, {"NVDA"})
        self.assertEqual(enriched.mappings[0].event_ref, "E1:v1")
        self.assertFalse(
            enriched.manifest["contract_degradations_by_event_version"]
        )
        self.assertFalse(enriched.manifest["placeholder_mapping_refs"])
        self.assertEqual(enriched.manifest["enrichment"]["unresolved_event_refs"], [])

        signals, unmapped = generate_signals(
            enriched.events,
            enriched.mappings,
            datetime(2026, 8, 19, 11, tzinfo=timezone.utc),
            SignalConfig(),
        )
        self.assertEqual([item.ticker for item in signals], ["NVDA"])
        self.assertAlmostEqual(signals[0].raw_strength, 0.64)
        self.assertFalse(unmapped)

    def test_enriched_mapping_does_not_leak_to_another_event_version(self):
        bundle = _bundle()
        bundle.events.append(
            EventSnapshot.from_dict(
                {
                    "event_id": "E2",
                    "event_version": 1,
                    "published_at": "2026-08-19T09:10:00Z",
                    "observed_at": "2026-08-19T09:15:00Z",
                    "event_type": "news_event",
                    "direction": "positive",
                    "confidence": 0.9,
                    "novelty": 0.9,
                    "conflict": False,
                    "impact_horizon_days": 20,
                    "entities": ["NVIDIA"],
                    "sectors": [],
                    "evidence_ids": ["EV1"],
                    "status": "confirmed",
                    "asof": "2026-08-19T09:15:00Z",
                }
            )
        )
        with tempfile.TemporaryDirectory() as directory:
            enriched = apply_news_enrichment(
                bundle, _write_payload(Path(directory), _payload())
            )

        signals, unmapped = generate_signals(
            enriched.events,
            enriched.mappings,
            datetime(2026, 8, 19, 11, tzinfo=timezone.utc),
            SignalConfig(),
        )
        self.assertEqual([item.event_id for item in signals], ["E1"])
        self.assertIn({"event_ref": "E2:v1", "entity": "NVIDIA"}, unmapped)

    def test_partial_enrichment_preserves_unresolved_mapping_state(self):
        payload = _payload()
        row = payload["events"][0]
        row["published_at"] = None
        row["mappings"] = []
        with tempfile.TemporaryDirectory() as directory:
            enriched = apply_news_enrichment(
                _bundle(), _write_payload(Path(directory), payload)
            )

        self.assertEqual(enriched.events[0].sectors, ("__UNMAPPED__",))
        remaining = enriched.manifest[
            "contract_degradations_by_event_version"
        ]["E1:v1"]
        self.assertEqual(
            remaining,
            [
                "industry_mapping_contains_encoding_replacement",
                "no_investable_company_or_industry_mapping",
                "published_at_fell_back_to_first_seen",
            ],
        )
        self.assertEqual(enriched.manifest["placeholder_mapping_refs"], ["E1:v1"])
        self.assertEqual(
            enriched.manifest["enrichment"]["unresolved_event_refs"], ["E1:v1"]
        )

    def test_unknown_and_duplicate_event_refs_fail_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            unknown = _payload()
            unknown["events"][0]["event_id"] = "UNKNOWN"
            with self.assertRaisesRegex(ContractError, "unknown event versions"):
                apply_news_enrichment(_bundle(), _write_payload(root, unknown))

            duplicate = _payload()
            duplicate["events"].append(dict(duplicate["events"][0]))
            with self.assertRaisesRegex(ContractError, "duplicate news enrichment"):
                apply_news_enrichment(_bundle(), _write_payload(root, duplicate))

    def test_event_version_must_be_a_real_json_integer(self):
        for invalid in (1.0, "1", True):
            with self.subTest(event_version=invalid):
                payload = _payload()
                payload["events"][0]["event_version"] = invalid
                with tempfile.TemporaryDirectory() as directory:
                    with self.assertRaisesRegex(ContractError, "must be an integer"):
                        apply_news_enrichment(
                            _bundle(), _write_payload(Path(directory), payload)
                        )

    def test_placeholder_ticker_and_non_external_urls_fail_closed(self):
        payload = _payload()
        payload["events"][0]["mappings"][0]["ticker"] = "DEMO-NVDA"
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(ContractError, "invalid enrichment ticker"):
                apply_news_enrichment(
                    _bundle(), _write_payload(Path(directory), payload)
                )

        for invalid_url in (
            "http://127.0.0.1/source",
            "https://example.com/source",
            "https://news.service.local/source",
        ):
            with self.subTest(url=invalid_url):
                payload = _payload()
                payload["events"][0]["source_urls"] = [invalid_url]
                with tempfile.TemporaryDirectory() as directory:
                    with self.assertRaisesRegex(ContractError, "non-external"):
                        apply_news_enrichment(
                            _bundle(), _write_payload(Path(directory), payload)
                        )

    def test_placeholder_source_provenance_fails_closed(self):
        payload = _payload()
        payload["source"]["pipeline_run_id"] = "REPLACE-WITH-PRODUCTION-RUN"
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(
                ContractError, "requires production repository"
            ):
                apply_news_enrichment(
                    _bundle(), _write_payload(Path(directory), payload)
                )

    def test_pit_dates_fail_closed(self):
        payload = _payload()
        payload["events"][0]["mappings"][0]["effective_from"] = "2027-01-01"
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(ContractError, "not effective"):
                apply_news_enrichment(
                    _bundle(), _write_payload(Path(directory), payload)
                )

        payload = _payload()
        payload["events"][0]["available_at"] = "2026-08-19T11:00:00Z"
        payload["generated_at"] = "2026-08-19T10:30:00Z"
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(ContractError, "exceeds generated_at"):
                apply_news_enrichment(
                    _bundle(), _write_payload(Path(directory), payload)
                )

    def test_news_export_cli_applies_enrichment(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            output = root / "export"
            enrichment = _write_payload(root, _payload())
            with (
                patch("evidence_alpha.cli.NewsAdapter") as adapter,
                patch("builtins.print"),
            ):
                adapter.return_value.export.return_value = _bundle()
                result = cli_main(
                    [
                        "news-export",
                        "--news-base-url",
                        "https://news.internal.invalid",
                        "--enrichment",
                        str(enrichment),
                        "--output-dir",
                        str(output),
                    ]
                )

            self.assertEqual(result, 0)
            manifest = json.loads(
                (output / "news_manifest.json").read_text(encoding="utf-8")
            )
            events = json.loads(
                (output / "events.json").read_text(encoding="utf-8")
            )
            self.assertEqual(manifest["enrichment"]["applied_event_refs"], ["E1:v1"])
            self.assertEqual(events[0]["novelty"], 0.8)
            with (output / "mappings.csv").open(
                "r", encoding="utf-8", newline=""
            ) as handle:
                rows = list(csv.DictReader(handle))
            self.assertEqual(rows[0]["event_ref"], "E1:v1")
            self.assertEqual(
                load_mappings(output / "mappings.csv")[0].event_ref,
                "E1:v1",
            )

    def test_integrate_cli_passes_enrichment_path(self):
        with tempfile.TemporaryDirectory() as directory:
            enrichment = Path(directory) / "news_enrichment.json"
            with (
                patch(
                    "evidence_alpha.cli.run_integration",
                    return_value={
                        "run_id": "RUN-1",
                        "status": "READY_FOR_PAPER_RESEARCH",
                        "decision": "PROMOTE",
                        "live_launch": {"decision": "BLOCKED"},
                        "hard_failures": [],
                    },
                ) as run,
                patch("builtins.print"),
            ):
                result = cli_main(
                    [
                        "integrate",
                        "--factor-root",
                        directory,
                        "--asof",
                        "2026-08-19T12:00:00Z",
                        "--news-enrichment",
                        str(enrichment),
                        "--output-dir",
                        str(Path(directory) / "output"),
                    ]
                )

            self.assertEqual(result, 0)
            self.assertEqual(
                run.call_args.kwargs["news_enrichment_path"], str(enrichment)
            )


if __name__ == "__main__":
    unittest.main()
