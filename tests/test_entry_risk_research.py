import unittest
import pandas as pd
from src.entry_risk_research import summarize, gap_buckets, stop_reason_summary

class EntryRiskResearchTests(unittest.TestCase):
    def setUp(self):
        self.frame = pd.DataFrame({
            "symbol": ["AAA", "BBB", "CCC"], "period": ["development_3y"]*3,
            "signal_date": ["2024-01-01"]*3,
            "entry_date": ["2024-01-02", "2024-01-03", "2024-01-04"],
            "exit_reason": ["stop", "stop_gap", "target"],
            "signal_close": [100,100,100], "signal_atr": [2,2,2],
            "entry_gap_pct": [0.5,2.0,-0.5],
            "entry_stop_distance_inr": [3,4.5,2.5],
            "entry_stop_distance_pct": [3,4.4,2.5],
            "stop_distance_vs_signal_atr": [1.5,2.25,1.25],
            "net_pnl_inr": [-10,-20,30], "net_r_multiple": [-1,-1,1.5],
        })
    def test_period_summary_separates_gap_stops(self):
        result = summarize(self.frame).iloc[0]
        self.assertEqual(result["trades"], 3)
        self.assertEqual(result["gap_stop_count"], 1)
        self.assertEqual(result["gap_stop_net_pnl_inr"], -20)
        self.assertEqual(result["stop_exit_count"], 2)
    def test_gap_buckets_cover_trades(self):
        self.assertEqual(int(gap_buckets(self.frame)["trades"].sum()), 3)
    def test_stop_reason_breakdown(self):
        result = stop_reason_summary(self.frame)
        self.assertEqual(set(result["exit_reason"]), {"stop", "stop_gap"})

if __name__ == "__main__":
    unittest.main()
