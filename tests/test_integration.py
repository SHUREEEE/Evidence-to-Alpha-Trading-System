import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from evidence_alpha.cli import main as cli_main
from evidence_alpha.integration import (
    _effective_data_classification,
    config_from_asof,
    fuse_pre_v4_weights,
    run_integration,
)
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


def _real_news_export(size=12):
    events = []
    evidence = {}
    start = datetime(2026, 7, 1, 9, tzinfo=timezone.utc)
    for index in range(size):
        observed = start + timedelta(days=index)
        ticker = "NVDA" if index % 2 == 0 else "TSM"
        evidence_id = f"REAL-EV-{index:02d}"
        events.append(
            EventSnapshot.from_dict(
                {
                    "event_id": f"REAL-{index:02d}",
                    "event_version": 1,
                    "published_at": (
                        observed - timedelta(minutes=5)
                    ).isoformat(),
                    "observed_at": observed.isoformat(),
                    "event_type": "news_event",
                    "direction": "positive",
                    "confidence": 0.8,
                    "novelty": 0.7,
                    "conflict": False,
                    "impact_horizon_days": 20,
                    "entities": [ticker],
                    "sectors": [],
                    "evidence_ids": [evidence_id],
                    "status": "confirmed",
                    "asof": observed.isoformat(),
                }
            )
        )
        evidence[evidence_id] = EvidenceRecord(
            evidence_id,
            f"https://source.test/{index}",
            observed,
            "Source",
        )
    return NewsExport(
        events=events,
        evidence=evidence,
        mappings=[
            EntityMapping("NVDA", "NVDA", "Technology"),
            EntityMapping("TSM", "TSM", "Technology"),
        ],
        manifest={"synthetic": False},
    )


class IntegrationTests(unittest.TestCase):
    def test_real_label_cannot_override_news_contract_degradation(self):
        news = _real_news_export()
        news.manifest["contract_degradations_by_event_version"] = {
            "REAL-00:v1": ["novelty_not_exposed_by_api"]
        }

        classification = _effective_data_classification(
            news,
            config_from_asof(
                "2026-08-19T12:00:00Z", data_classification="real"
            ),
        )

        self.assertEqual(classification, "unknown")

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
                "2026-08-20,NVDA,102\n2026-08-20,TSM,51\n2026-08-20,SPY,501\n"
                "2026-08-21,NVDA,103\n2026-08-21,TSM,51.2\n2026-08-21,SPY,501.5\n",
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
            self.assertEqual(report["release"], "v0.5.0-integration")
            self.assertEqual(report["data_classification"], "synthetic")
            self.assertEqual(
                report["independent_validation"]["decision"], "INCONCLUSIVE"
            )
            self.assertEqual(report["live_launch"]["decision"], "BLOCKED")
            self.assertEqual(
                set(report["comparisons"]),
                {"factor_baseline", "event_only", "factor_plus_event_pre_v4"},
            )
            self.assertTrue(report["paper_oms"]["reconciliation"]["closed_to_cent"])
            self.assertTrue(report["gates"]["paper_fill_after_asof"])
            self.assertEqual(report["paper_oms"]["fill_date"], "2026-08-20")
            self.assertTrue((output / "fused_pre_v4_weights.csv").exists())
            self.assertTrue((output / "event_study.csv").exists())
            self.assertTrue((output / "independent_validation.json").exists())
            self.assertTrue((output / "audit.json").exists())
            with patch("builtins.print"):
                self.assertEqual(
                    cli_main(["verify", "--artifact-dir", str(output)]),
                    0,
                )
            orders = json.loads((output / "orders.json").read_text(encoding="utf-8"))
            fills = json.loads((output / "fills.json").read_text(encoding="utf-8"))
            self.assertTrue(orders)
            self.assertEqual(report["counts"]["paper_fills"], len(fills))
            self.assertEqual(fills[0]["order_id"], orders[0]["order_id"])
            self.assertTrue(fills[0]["fill_id"].startswith("INTFILL-"))
            self.assertTrue(any(item["event_refs"] for item in orders if item["ticker"] in {"NVDA", "TSM"}))
            rejected_output = root / "nonfinite-output"
            with (
                patch("evidence_alpha.integration.NewsAdapter") as adapter,
                patch(
                    "evidence_alpha.integration._scenario_net_return",
                    return_value=float("nan"),
                ),
            ):
                adapter.return_value.export.return_value = _news_export()
                rejected = run_integration(
                    news_base_url="http://news.test",
                    factor_root=root,
                    weights_path="weights.csv",
                    sectors_path="sectors.csv",
                    prices_path="prices.csv",
                    output_dir=rejected_output,
                    config=config_from_asof("2026-08-19T12:00:00Z"),
                    allow_synthetic_news=True,
                    write_parquet_staging=False,
                )
            self.assertEqual(rejected["decision"], "REJECT")
            self.assertIn(
                "robustness_scenarios_numeric",
                rejected["independent_validation"]["hard_failures"],
            )

    def test_real_positive_integrated_sample_can_promote_but_live_stays_blocked(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "weights.csv").write_text(
                "date,ticker,weight\n"
                "2026-07-11,NVDA,0.4\n"
                "2026-07-11,TSM,0.3\n"
                "2026-07-11,SPY,0.3\n"
                "2026-07-12,NVDA,0.4\n"
                "2026-07-12,TSM,0.3\n"
                "2026-07-12,SPY,0.3\n",
                encoding="utf-8",
            )
            price_lines = ["date,ticker,adj_close"]
            nvda = 100.0
            tsm = 100.0
            start = datetime(2026, 7, 1)
            for index in range(25):
                if index:
                    if index == 12:
                        nvda *= 1.10
                        tsm *= 1.08
                    elif index == 13:
                        nvda *= 1.005
                        tsm *= 1.004
                    else:
                        nvda *= 1.02
                        tsm *= 1.015
                day = (start + timedelta(days=index)).date().isoformat()
                price_lines.extend(
                    [
                        f"{day},NVDA,{nvda}",
                        f"{day},TSM,{tsm}",
                        f"{day},SPY,100",
                    ]
                )
            (root / "prices.csv").write_text(
                "\n".join(price_lines) + "\n", encoding="utf-8"
            )
            (root / "sectors.csv").write_text(
                "symbol,sector\n"
                "NVDA,Technology\n"
                "TSM,Technology\n"
                "SPY,ETF\n",
                encoding="utf-8",
            )
            output = root / "output"
            with patch("evidence_alpha.integration.NewsAdapter") as adapter:
                adapter.return_value.export.return_value = _real_news_export()
                report = run_integration(
                    news_base_url="http://news.test",
                    factor_root=root,
                    weights_path="weights.csv",
                    sectors_path="sectors.csv",
                    prices_path="prices.csv",
                    output_dir=output,
                    config=config_from_asof(
                        "2026-07-12T12:00:00Z",
                        data_classification="real",
                        minimum_event_count=12,
                        minimum_oos_events=3,
                        rolling_folds=3,
                        oos_fraction=0.25,
                    ),
                    write_parquet_staging=False,
                )

            self.assertEqual(report["decision"], "PROMOTE")
            self.assertEqual(report["status"], "READY_FOR_PAPER_RESEARCH")
            self.assertEqual(report["data_classification"], "real")
            self.assertFalse(report["hard_failures"])
            self.assertEqual(
                report["independent_validation"]["decision"], "PROMOTE"
            )
            self.assertEqual(report["live_launch"]["decision"], "BLOCKED")

    def test_stale_factor_data_cannot_fill_before_event_asof(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "weights.csv").write_text(
                "date,ticker,weight\n"
                "2026-07-16,NVDA,0.4\n2026-07-16,TSM,0.3\n2026-07-16,SPY,0.3\n"
                "2026-07-17,NVDA,0.4\n2026-07-17,TSM,0.3\n2026-07-17,SPY,0.3\n",
                encoding="utf-8",
            )
            (root / "prices.csv").write_text(
                "date,ticker,adj_close\n"
                "2026-07-16,NVDA,100\n2026-07-16,TSM,50\n2026-07-16,SPY,500\n"
                "2026-07-17,NVDA,102\n2026-07-17,TSM,51\n2026-07-17,SPY,501\n",
                encoding="utf-8",
            )
            (root / "sectors.csv").write_text(
                "symbol,sector\nNVDA,Technology\nTSM,Technology\nSPY,ETF\n",
                encoding="utf-8",
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

            self.assertEqual(report["status"], "BLOCKED")
            self.assertEqual(report["decision"], "REJECT")
            self.assertEqual(report["factor_weight_date"], "2026-07-17")
            self.assertEqual(report["execution_anchor_date"], "2026-08-19")
            self.assertFalse(report["gates"]["t_plus_one_prices"])
            self.assertFalse(report["gates"]["paper_fill_after_asof"])
            self.assertIn("paper_fill_after_asof", report["hard_failures"])
            self.assertIn(
                "robustness_scenarios_numeric",
                report["independent_validation"]["hard_failures"],
            )
            self.assertIn(
                "independent_validation:robustness_scenarios_numeric",
                report["hard_failures"],
            )
            with patch("builtins.print"):
                self.assertEqual(
                    cli_main(["verify", "--artifact-dir", str(output)]),
                    1,
                )
            self.assertEqual(report["counts"]["paper_orders"], 0)
            self.assertEqual(report["counts"]["paper_fills"], 0)
            self.assertEqual(
                report["comparisons"]["factor_baseline"]["status"],
                "missing_t_plus_one_prices",
            )
            self.assertEqual(
                report["paper_oms"]["reconciliation"]["reason"],
                "missing_t_plus_one_prices",
            )
