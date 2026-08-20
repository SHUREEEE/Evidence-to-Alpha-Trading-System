import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from evidence_alpha.integration import config_from_asof, fuse_pre_v4_weights, run_integration
from evidence_alpha.models import EntityMapping, EventSignal, EventSnapshot, EvidenceRecord
from evidence_alpha.news_adapter import NewsExport


def _signal(ticker="NVDA", strength=0.8):
    return EventSignal(
        "S1", "E1", 1, ticker, "Technology",
        datetime(2026, 8, 19, 12, tzinfo=timezone.utc),
        strength, strength, ("EV1",), "CFG",
    )


def _news_export():
    event = EventSnapshot.from_dict(
        {
            "event_id": "E1",
            "event_version": 1,
            "published_at": "2026-08-19T09:00:00Z",
            "observed_at": "2026-08-19T09:05:00Z",
            "event_type": "news_event",
            "direction": "positive",
            "confidence": 0.8,
            "novelty": 0.6,
            "conflict": False,
            "impact_horizon_days": 20,
            "entities": ["NVDA", "TSM"],
            "sectors": [],
            "evidence_ids": ["EV1"],
            "status": "developing",
            "asof": "2026-08-19T09:05:00Z",
        }
    )
    return NewsExport(
        events=[event],
        evidence={
            "EV1": EvidenceRecord(
                "EV1", "https://source.test/1", datetime(2026, 8, 19, 9, 5, tzinfo=timezone.utc), "Source"
            )
        },
        mappings=[
            EntityMapping("NVDA", "NVDA", "Technology"),
            EntityMapping("TSM", "TSM", "Technology"),
        ],
        manifest={"synthetic": True, "synthetic_allowed": True},
    )


class IntegrationTests(unittest.TestCase):
    def test_pre_v4_overlay_preserves_net_exposure_and_turnover(self):
        config = config_from_asof("2026-08-19T12:00:00Z")
        baseline = {"NVDA": 0.5, "TSM": 0.3, "SPY": 0.2}
        fused, delta = fuse_pre_v4_weights(baseline, [_signal()], config)
        self.assertAlmostEqual(sum(fused.values()), sum(baseline.values()))
        self.assertAlmostEqual(sum(delta.values()), 0.0)
        self.assertLessEqual(sum(abs(value) for value in delta.values()), config.overlay_turnover_cap)

    def test_full_integration_writes_three_comparisons_and_paper_blotter(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "weights.csv").write_text(
                "date,ticker,weight\n"
                "2026-08-18,NVDA,0.4\n2026-08-18,TSM,0.3\n2026-08-18,SPY,0.3\n"
                "2026-08-19,NVDA,0.4\n2026-08-19,TSM,0.3\n2026-08-19,SPY,0.3\n",
                encoding="utf-8",
            )
            (root / "prices.csv").write_text(
                "date,ticker,adj_close\n"
                "2026-08-19,NVDA,100\n2026-08-19,TSM,50\n2026-08-19,SPY,500\n"
                "2026-08-20,NVDA,102\n2026-08-20,TSM,51\n2026-08-20,SPY,501\n",
                encoding="utf-8",
            )
            (root / "sectors.csv").write_text(
                "symbol,sector\nNVDA,Technology\nTSM,Technology\nSPY,ETF\n", encoding="utf-8"
            )
            output = root / "output"
            with patch("evidence_alpha.integration.NewsAdapter") as adapter:
                adapter.return_value.export.return_value = _news_export()
                report = run_integration(
                    news_base_url="http://news.test",
                    factor_root=root,
                    weights_path="weights.csv",
                    sectors_path="sectors.csv",
                    prices_path="prices.csv",
                    output_dir=output,
                    config=config_from_asof("2026-08-19T12:00:00Z"),
                    allow_synthetic_news=True,
                    write_parquet_staging=False,
                )
            self.assertEqual(report["status"], "READY_FOR_PAPER_RESEARCH")
            self.assertEqual(report["decision"], "INCONCLUSIVE")
            self.assertEqual(report["live_launch"]["decision"], "BLOCKED")
            self.assertEqual(
                set(report["comparisons"]),
                {"factor_baseline", "event_only", "factor_plus_event_pre_v4"},
            )
            self.assertTrue(report["paper_oms"]["reconciliation"]["closed_to_cent"])
            self.assertTrue((output / "fused_pre_v4_weights.csv").exists())
            orders = json.loads((output / "orders.json").read_text(encoding="utf-8"))
            fills = json.loads((output / "fills.json").read_text(encoding="utf-8"))
            self.assertTrue(orders)
            self.assertEqual(report["counts"]["paper_fills"], len(fills))
            self.assertEqual(fills[0]["order_id"], orders[0]["order_id"])
            self.assertTrue(fills[0]["fill_id"].startswith("INTFILL-"))
            self.assertTrue(any(item["event_refs"] for item in orders if item["ticker"] in {"NVDA", "TSM"}))
