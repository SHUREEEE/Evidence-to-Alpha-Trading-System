import unittest
from datetime import date, datetime, timezone

from evidence_alpha.models import PriceBar
from evidence_alpha.oms import OmsConfig, simulate_paper_oms


class OmsTests(unittest.TestCase):
    def test_fills_are_t_plus_one_and_reconcile(self):
        prices = [
            PriceBar(date(2026, 1, 2), "AAA", 10, 10.5),
            PriceBar(date(2026, 1, 5), "AAA", 11, 12),
            PriceBar(date(2026, 1, 6), "AAA", 12, 13),
            PriceBar(date(2026, 1, 2), "SPY", 100, 101),
            PriceBar(date(2026, 1, 5), "SPY", 101, 102),
            PriceBar(date(2026, 1, 6), "SPY", 102, 103),
        ]
        orders, fills, summary = simulate_paper_oms(
            "RUN-1", datetime(2026, 1, 2, 12, tzinfo=timezone.utc), {"AAA": 1.0}, prices, "F-1", {}, OmsConfig()
        )
        self.assertEqual(fills[0].trade_date, date(2026, 1, 5))
        self.assertGreater(fills[0].trade_date, orders[0].created_at.date())
        self.assertTrue(summary["reconciliation"]["closed_to_cent"])

