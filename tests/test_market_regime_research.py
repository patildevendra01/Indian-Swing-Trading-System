import unittest
import pandas as pd
from src.market_regime_research import build_regime_history, attach_signal_regime, summarize_cohorts


class MarketRegimeResearchTests(unittest.TestCase):
    def test_ema_warmup_is_unavailable(self):
        frame = pd.DataFrame({"Close": range(1, 40)}, index=pd.date_range("2024-01-01", periods=39))
        self.assertTrue((build_regime_history(frame)["regime"] == "unavailable").all())

    def test_signal_uses_latest_index_date_not_future(self):
        idx = pd.date_range("2024-01-01", periods=100, freq="B")
        history = build_regime_history(pd.DataFrame({"Close": [100 + i for i in range(100)]}, index=idx))
        result = attach_signal_regime(pd.DataFrame({"signal_date": ["2024-03-01"]}), history)
        self.assertLessEqual(pd.Timestamp(result.loc[0, "market_data_date"]), pd.Timestamp("2024-03-01"))

    def test_summary_metrics(self):
        trades = pd.DataFrame({"period": ["development_3y"] * 3, "regime": ["above_rising"] * 3,
            "net_pnl_inr": [100, -50, 25], "net_r_multiple": [1.0, -0.5, 0.25]})
        result = summarize_cohorts(trades)
        self.assertEqual(result.loc[0, "trades"], 3)
        self.assertAlmostEqual(result.loc[0, "net_pnl_inr"], 75.0)
        self.assertAlmostEqual(result.loc[0, "profit_factor"], 2.5)


if __name__ == "__main__":
    unittest.main()
