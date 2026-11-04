import unittest
import pandas as pd

from src.relative_strength_research import relative_return, strength_bucket, attach_relative_strength, summarize_cohorts


class RelativeStrengthResearchTests(unittest.TestCase):
    def setUp(self):
        self.dates = pd.date_range("2024-01-01", periods=30, freq="B")
        self.market = pd.DataFrame({"Close": [100 + i for i in range(30)]}, index=self.dates)
        self.stock = pd.DataFrame({"Close": [200 + 2 * i for i in range(30)]}, index=self.dates)

    def test_returns_use_only_data_on_or_before_signal(self):
        result = relative_return(self.stock, self.market, self.dates[25] + pd.Timedelta(days=2), 20)
        self.assertEqual(result["stock_data_date"], self.dates[25].strftime("%Y-%m-%d"))
        self.assertEqual(result["nifty_data_date"], self.dates[25].strftime("%Y-%m-%d"))

    def test_insufficient_history_is_unavailable(self):
        self.assertIsNone(relative_return(self.stock.iloc[:10], self.market, self.dates[9], 20))

    def test_fixed_bucket_boundaries(self):
        self.assertEqual(strength_bucket(2.0), "outperforming_by_2pp_or_more")
        self.assertEqual(strength_bucket(-2.0), "underperforming_by_2pp_or_more")
        self.assertEqual(strength_bucket(1.99), "within_plus_minus_2pp")
        self.assertEqual(strength_bucket(float("nan")), "unavailable")

    def test_attach_and_summary(self):
        trades = pd.DataFrame({"symbol": ["ABC"], "signal_date": [self.dates[25].strftime("%Y-%m-%d")],
            "period": ["development_3y"], "net_pnl_inr": [100], "net_r_multiple": [1.0]})
        tagged = attach_relative_strength(trades, self.market, {"ABC": self.stock}, 20)
        self.assertIn("relative_strength_pct", tagged)
        summary = summarize_cohorts(tagged)
        self.assertEqual(summary.loc[0, "trades"], 1)


if __name__ == "__main__":
    unittest.main()
