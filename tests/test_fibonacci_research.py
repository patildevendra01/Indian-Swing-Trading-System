import unittest

import pandas as pd

from src.fibonacci_research import (
    confirmed_pivots,
    fib_levels,
    latest_confirmed_uptrend_leg,
    summarize_fibonacci_cohorts,
    tag_trade,
)


def swing_frame():
    # Deliberate sequence: low 90, high 110, higher low 95, higher high 120.
    # Three bars to the right confirm each pivot.
    values = [
        (100, 102, 98, 100),
        (99, 100, 95, 97),
        (96, 98, 90, 92),
        (93, 99, 92, 98),
        (99, 104, 97, 102),
        (103, 110, 101, 108),
        (107, 109, 103, 105),
        (104, 107, 100, 102),
        (103, 106, 95, 97),
        (98, 108, 97, 106),
        (107, 115, 105, 113),
        (112, 120, 110, 118),
        (117, 119, 108, 110),
        (109, 115, 105, 112),
        (111, 116, 106, 113),
        (112, 114, 107, 109),
    ]
    return pd.DataFrame(values, columns=["Open", "High", "Low", "Close"],
                        index=pd.date_range("2025-01-01", periods=len(values), freq="B"))


class FibonacciResearchTests(unittest.TestCase):
    def test_retracement_prices_for_upward_impulse(self):
        levels = fib_levels(100, 200)
        self.assertAlmostEqual(levels["fib_050"], 150.0)
        self.assertAlmostEqual(levels["fib_0618"], 138.2)
        self.assertAlmostEqual(levels["fib_066"], 134.0)
        self.assertAlmostEqual(levels["fib_0786"], 121.4)

    def test_rejects_invalid_impulse(self):
        with self.assertRaises(ValueError):
            fib_levels(200, 100)

    def test_pivots_are_not_confirmed_until_right_bars_have_elapsed(self):
        frame = swing_frame()
        before_confirmation = confirmed_pivots(frame, 4, left_bars=2, right_bars=3)
        self.assertFalse(any(p["index"] == 2 for p in before_confirmation))
        after_confirmation = confirmed_pivots(frame, 5, left_bars=2, right_bars=3)
        self.assertTrue(any(p["kind"] == "low" and p["index"] == 2
                            for p in after_confirmation))

    def test_latest_uptrend_leg_requires_higher_high_and_higher_low(self):
        frame = swing_frame()
        leg = latest_confirmed_uptrend_leg(frame, len(frame) - 1,
                                           left_bars=2, right_bars=2)
        self.assertIsNotNone(leg)
        self.assertEqual(leg["swing_low"], 95.0)
        self.assertEqual(leg["swing_high"], 120.0)

    def test_signal_tag_uses_only_history_through_signal_date(self):
        frame = swing_frame()
        trade = {"signal_date": frame.index[13].strftime("%Y-%m-%d")}
        tag = tag_trade(trade, frame, tolerance_pct=100,
                        left_bars=2, right_bars=2)
        self.assertEqual(tag["fib_signal_data_date"], frame.index[13].strftime("%Y-%m-%d"))
        self.assertNotEqual(tag["fib_structure"], "history_unavailable")

    def test_cohort_summary_compares_to_baseline_and_marks_small_samples(self):
        trades = pd.DataFrame([
            {"period": "development_3y", "net_pnl_inr": 10, "net_r_multiple": 0.2,
             "fib_050_match": True, "fib_0618_match": False, "fib_066_match": False,
             "fib_0786_match": False, "fib_golden_pocket_match": False},
            {"period": "development_3y", "net_pnl_inr": -5, "net_r_multiple": -0.1,
             "fib_050_match": False, "fib_0618_match": True, "fib_066_match": False,
             "fib_0786_match": False, "fib_golden_pocket_match": True},
        ])
        summary = summarize_fibonacci_cohorts(trades, min_trades=2)
        baseline = summary[summary["setup"] == "baseline_all"].iloc[0]
        half = summary[summary["setup"] == "fib_050"].iloc[0]
        self.assertEqual(baseline["trades"], 2)
        self.assertTrue(baseline["meets_min_sample"])
        self.assertEqual(half["trades"], 1)
        self.assertFalse(half["meets_min_sample"])


if __name__ == "__main__":
    unittest.main()
