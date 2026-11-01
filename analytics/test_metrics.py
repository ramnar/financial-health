"""Run: python -m unittest test_metrics  (from the analytics/ directory)"""
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

import metrics as m

ROOT = Path(__file__).parent


class PureLogic(unittest.TestCase):
    def test_mark_missing_turns_zero_into_nan(self):
        df = pd.DataFrame({"v": [10.0, 0.0, 12.0]})
        self.assertTrue(np.isnan(m.mark_missing(df, ["v"])["v"][1]))

    def test_latest_change_skips_missing(self):
        value, delta = m.latest_change(pd.Series([10.0, 15.0, np.nan]))
        self.assertEqual((value, delta), (15.0, 5.0))

    def test_complete_months_drops_current_and_partial(self):
        cf = pd.DataFrame({"month": pd.to_datetime(["2026-09-01", "2026-10-01", "2026-11-01"]),
                           "income": [100.0, np.nan, 100.0], "expense": [40.0, 30.0, 40.0],
                           "savings": [60.0, -30.0, 60.0]})
        out = m.complete_months(cf, pd.Timestamp("2026-11-15"))
        self.assertEqual(out["month"].tolist(), [pd.Timestamp("2026-09-01")])
        self.assertAlmostEqual(out["savings_rate"][0], 60.0)

    def test_filter_period(self):
        df = pd.DataFrame({"month": pd.date_range("2024-01-01", periods=30, freq="MS")})
        self.assertEqual(len(m.filter_period(df, "1Y")), 12)
        self.assertEqual(len(m.filter_period(df, "All")), 30)

    def test_annual_trend_is_per_year(self):
        df = pd.DataFrame({"month": pd.date_range("2024-01-01", periods=12, freq="MS"),
                           "x": np.arange(12) * 100.0})
        self.assertAlmostEqual(m.annual_trend(df, "x"), 1200.0)

    def test_head_inflation_simple_average_and_zero_base(self):
        eh = pd.DataFrame({"head": ["A"] * 4 + ["B"] * 4, "year": [2023, 2024, 2025, 2026] * 2,
                           "annual": 0.0, "monthly_avg": [100, 100, 100, 130, 0, 0, 50, 60]})
        out = m.head_inflation(eh)
        self.assertAlmostEqual(out.loc["A", "infl_1y"], 30.0)
        self.assertAlmostEqual(out.loc["A", "infl_3y"], 10.0)
        self.assertTrue(np.isnan(out.loc["B", "infl_2y"]))

    def test_balance_status_and_rebalance_amount(self):
        alloc = pd.DataFrame({"asset_class": ["Equity", "Debt"], "value": [70.0, 30.0],
                              "pct": [70.0, 30.0]})
        ranges = pd.DataFrame({"asset_class": ["Equity", "Debt"], "low": [40.0, 35.0],
                               "high": [60.0, 50.0]})
        out = m.balance_status(alloc, ranges, {"Equity": 50.0, "Debt": 50.0}).set_index("asset_class")
        self.assertEqual(out.loc["Equity", "status"], "Above range")
        self.assertAlmostEqual(out.loc["Equity", "rebalance_amount"], -10.0)
        self.assertAlmostEqual(out.loc["Debt", "rebalance_amount"], 5.0)
        self.assertEqual(out.loc["Real Estate", "status"], "No recommendation")


@unittest.skipUnless((ROOT / "data" / "cashflow.csv").exists(), "run extract.py first")
class MatchesRR2FF(unittest.TestCase):
    """The extracted data must reproduce figures shown on the RR2FF pages."""

    @classmethod
    def setUpClass(cls):
        cls.d = m.load_data(ROOT / "data")

    def test_portfolio_total_and_class_split(self):
        alloc = m.class_allocation(self.d["asset_split"]).set_index("asset_class")
        self.assertEqual(alloc["value"].sum(), 29_890_601)
        self.assertAlmostEqual(alloc.loc["Equity", "pct"], 55.56, places=2)
        self.assertAlmostEqual(alloc.loc["Debt", "pct"], 34.76, places=2)
        self.assertAlmostEqual(alloc.loc["Commodities", "pct"], 8.96, places=2)
        self.assertAlmostEqual(alloc.loc["Crypto", "pct"], 0.39, places=2)

    def test_asset_to_class_mapping_sums_to_class_totals(self):
        tree = m.asset_tree(self.d["asset_split"]).groupby("asset_class")["value"].sum()
        alloc = m.class_allocation(self.d["asset_split"]).set_index("asset_class")["value"]
        for cls in ["Equity", "Debt", "Commodities", "Crypto"]:
            self.assertEqual(tree[cls], alloc[cls], cls)

    def test_latest_roi(self):
        self.assertEqual(self.d["roi"].dropna()["roi_pct"].iloc[-1], 17.23)

    def test_savings_equals_income_minus_expense(self):
        cf = self.d["cashflow"].dropna(subset=["savings_reported"])
        self.assertTrue(((cf["savings"] - cf["savings_reported"]).abs() < 1).all())

    def test_expense_year_total_and_inflation(self):
        eh = self.d["expense_heads"]
        self.assertEqual(eh[eh["year"] == 2026]["annual"].sum(), 1_022_337)
        infl = m.total_inflation(eh)
        # RR2FF truncates to whole percent: 15%, 22%, 5%
        self.assertEqual([int(infl[f"infl_{n}y"]) for n in (1, 2, 3)], [15, 22, 5])
        grocery = m.head_inflation(eh).loc["Grocery"]
        self.assertEqual([int(grocery[f"infl_{n}y"]) for n in (1, 2, 3)], [41, 18, 15])

    def test_latest_strategy_targets(self):
        t = m.latest_targets(self.d["strategy"])
        self.assertEqual(t, {"Equity": 51, "Debt": 39, "Commodities": 8,
                             "Crypto": 2, "Real Estate": 0})


if __name__ == "__main__":
    unittest.main()
