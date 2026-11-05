import unittest

import pandas as pd

from src.fibonacci_pullback_backtest import latest_confirmed_uptrend_leg, summarize


class FibonacciPullbackTests(unittest.TestCase):
    def test_latest_confirmed_higher_high_higher_low_leg(self):
        pivots = [
            {"kind": "low", "index": 2, "confirmed_index": 5, "price": 90.0},
            {"kind": "high", "index": 5, "confirmed_index": 8, "price": 110.0},
            {"kind": "low", "index": 9, "confirmed_index": 12, "price": 95.0},
            {"kind": "high", "index": 13, "confirmed_index": 16, "price": 120.0},
        ]
        self.assertIsNone(latest_confirmed_uptrend_leg(pivots, 15))
        leg = latest_confirmed_uptrend_leg(pivots, 16)
        self.assertEqual(leg["swing_low"], 95.0)
        self.assertEqual(leg["swing_high"], 120.0)
        self.assertEqual(leg["confirmed_index"], 16)

    def test_rejects_non_higher_high_or_non_higher_low(self):
        pivots = [
            {"kind": "low", "index": 2, "confirmed_index": 5, "price": 90.0},
            {"kind": "high", "index": 5, "confirmed_index": 8, "price": 110.0},
            {"kind": "low", "index": 9, "confirmed_index": 12, "price": 89.0},
            {"kind": "high", "index": 13, "confirmed_index": 16, "price": 120.0},
        ]
        self.assertIsNone(latest_confirmed_uptrend_leg(pivots, 16))

    def test_cohort_summary_marks_small_samples(self):
        trades = pd.DataFrame([
            {"period": "development_3y", "setup": "fib_0618",
             "net_pnl_inr": 10.0, "net_r_multiple": 0.2},
            {"period": "development_3y", "setup": "fib_0618",
             "net_pnl_inr": -5.0, "net_r_multiple": -0.1},
        ])
        row = summarize(trades, min_trades=3).iloc[0]
        self.assertEqual(row["trades"], 2)
        self.assertFalse(row["meets_min_sample"])
        self.assertEqual(row["net_pnl_inr"], 5.0)


if __name__ == "__main__":
    unittest.main()
