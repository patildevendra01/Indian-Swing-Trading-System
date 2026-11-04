import unittest
import pandas as pd

from src.improvement_research import (
    max_loss_streak, period_diagnostics, rolling_diagnostics, symbol_diagnostics
)


class ImprovementResearchTests(unittest.TestCase):
    def setUp(self):
        self.frame = pd.DataFrame({
            "period": ["out_of_sample_2y"] * 6,
            "symbol": ["AAA.NS"] * 5 + ["BBB.NS"],
            "entry_date": pd.to_datetime([
                "2025-01-01", "2025-01-02", "2025-01-03",
                "2025-01-04", "2025-01-05", "2025-01-06"
            ]),
            "exit_reason": ["stop", "stop_gap", "target", "time_exit", "stop", "target"],
            "net_pnl_inr": [-100, -120, 200, 30, -80, 150],
            "net_r_multiple": [-1.0, -1.2, 1.8, 0.2, -0.8, 1.5],
            "holding_sessions": [2, 1, 5, 10, 3, 4],
        })

    def test_max_consecutive_losses(self):
        self.assertEqual(max_loss_streak([-1, -2, 1, -3, -4, -5, 1]), 3)

    def test_period_stop_diagnostics(self):
        result = period_diagnostics(self.frame).iloc[0]
        self.assertEqual(int(result["trades"]), 6)
        self.assertEqual(int(result["max_consecutive_losses"]), 2)
        self.assertEqual(round(result["stop_net_pnl_inr"], 2), -300.00)

    def test_symbol_minimum_sample(self):
        result = symbol_diagnostics(self.frame, minimum=5)
        self.assertEqual(len(result), 1)
        self.assertEqual(result.iloc[0]["symbol"], "AAA.NS")

    def test_rolling_requires_full_window(self):
        result = rolling_diagnostics(self.frame, window=3)
        self.assertEqual(len(result), 4)


if __name__ == "__main__":
    unittest.main()
