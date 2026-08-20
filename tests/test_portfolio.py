import unittest

from evidence_alpha.models import BaselineWeight, EventSignal
from evidence_alpha.portfolio import PortfolioConfig, build_portfolios
from datetime import datetime, timezone


class PortfolioTests(unittest.TestCase):
    def test_overlay_constraints_hold(self):
        baseline = [
            BaselineWeight(__import__("datetime").date(2026, 1, 1), "AAA", 0.5, "F1"),
            BaselineWeight(__import__("datetime").date(2026, 1, 1), "BBB", 0.3, "F1"),
            BaselineWeight(__import__("datetime").date(2026, 1, 1), "SPY", 0.2, "F1"),
        ]
        signal = EventSignal("S1", "E1", 1, "AAA", "Tech", datetime(2026, 1, 2, tzinfo=timezone.utc), 1, 1, ("SRC",), "CFG")
        result = build_portfolios(baseline, [signal], PortfolioConfig())
        self.assertTrue(all(result["constraints"].values()))
        self.assertAlmostEqual(sum(result["overlay"].values()), 1.0)

