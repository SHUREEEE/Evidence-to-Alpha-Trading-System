import tempfile
import unittest
from pathlib import Path

from evidence_alpha.models import ContractError
from evidence_alpha.multifactor_adapter import MultiFactorAdapter, load_weight_panel


class MultiFactorAdapterTests(unittest.TestCase):
    def test_loads_wide_weights_and_long_prices(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "weights.csv").write_text(
                "date,NVDA,TSM\n2026-08-18,0.4,0.6\n2026-08-19,0.5,0.5\n",
                encoding="utf-8",
            )
            (root / "prices.csv").write_text(
                "date,ticker,adj_close\n"
                "2026-08-19,NVDA,100\n2026-08-19,TSM,50\n"
                "2026-08-20,NVDA,102\n2026-08-20,TSM,49\n",
                encoding="utf-8",
            )
            (root / "sectors.csv").write_text(
                "symbol,sector\nNVDA,Technology\nTSM,Technology\n", encoding="utf-8"
            )
            inputs = MultiFactorAdapter(
                root,
                weights_path="weights.csv",
                sectors_path="sectors.csv",
                prices_path="prices.csv",
            ).load()
            day, row = inputs.weights.on_or_before(__import__("datetime").date(2026, 8, 19))
            self.assertEqual(day.isoformat(), "2026-08-19")
            self.assertEqual(row, {"NVDA": 0.5, "TSM": 0.5})
            self.assertEqual(inputs.prices.adj_close[day]["NVDA"], 100.0)

    def test_duplicate_weight_row_fails_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "weights.csv"
            path.write_text(
                "date,ticker,weight\n2026-08-19,NVDA,0.5\n2026-08-19,NVDA,0.6\n",
                encoding="utf-8",
            )
            with self.assertRaises(ContractError):
                load_weight_panel(path)
