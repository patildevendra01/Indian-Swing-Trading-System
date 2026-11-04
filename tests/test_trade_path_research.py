import unittest
import pandas as pd
from src.trade_path_research import load, summarize_paths, summarize_periods


class TradePathResearchTests(unittest.TestCase):
    def setUp(self):
        self.frame = pd.DataFrame({
            "period": ["development_3y"] * 3,
            "exit_reason": ["stop", "target", "time_exit"],
            "net_pnl_inr": [-10, 30, 5],
            "net_r_multiple": [-1, 1.8, 0.2],
            "holding_sessions": [2, 4, 5],
            "mfe_r": [0.2, 2.1, 0.8],
            "mae_r": [-1.1, -0.3, -0.6],
            "best_close_r": [0.1, 1.9, 0.6],
            "exit_close_r": [-1.0, 1.7, 0.2],
        })

    def test_period_summary_counts_and_thresholds(self):
        result = summarize_periods(self.frame).iloc[0]
        self.assertEqual(result["trades"], 3)
        self.assertAlmostEqual(result["share_mfe_ge_0_5r_pct"], 66.67, places=1)
        self.assertAlmostEqual(result["share_mfe_ge_1r_pct"], 33.33, places=1)

    def test_exit_summary_separates_reasons(self):
        result = summarize_paths(self.frame)
        self.assertEqual(set(result["exit_reason"]), {"stop", "target", "time_exit"})
        stop = result[result.exit_reason == "stop"].iloc[0]
        self.assertEqual(stop["trades"], 1)
        self.assertEqual(stop["avg_mfe_r"], 0.2)

    def test_load_requires_path_columns(self):
        with self.assertRaises(ValueError):
            load("/path/that/does/not/exist.csv")


if __name__ == "__main__":
    unittest.main()
