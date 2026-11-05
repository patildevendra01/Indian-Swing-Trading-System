import unittest
import pandas as pd

from src.metrics import chronological_trade_metrics


class ChronologicalMetricsTests(unittest.TestCase):
    def calendar(self):
        return pd.bdate_range("2024-01-02", periods=4)

    def test_drawdown_is_independent_of_input_row_order(self):
        frame = pd.DataFrame([
            {"entry_date":"2024-01-02","exit_date":"2024-01-03","entry":100,"quantity":1,"net_pnl_inr":-100},
            {"entry_date":"2024-01-03","exit_date":"2024-01-04","entry":100,"quantity":1,"net_pnl_inr":200},
        ])
        first = chronological_trade_metrics(frame, 1000, self.calendar())
        shuffled = chronological_trade_metrics(frame.iloc[::-1], 1000, self.calendar())
        self.assertEqual(first, shuffled)
        self.assertEqual(first["max_drawdown_pct"], -10.0)

    def test_same_day_exits_are_aggregated_before_equity_update(self):
        frame = pd.DataFrame([
            {"entry_date":"2024-01-02","exit_date":"2024-01-03","entry":100,"quantity":1,"net_pnl_inr":-100},
            {"entry_date":"2024-01-02","exit_date":"2024-01-03","entry":100,"quantity":1,"net_pnl_inr":200},
        ])
        result = chronological_trade_metrics(frame, 1000, self.calendar())
        self.assertEqual(result["max_drawdown_pct"], 0.0)

    def test_exposure_counts_positions_inclusively_on_calendar(self):
        frame = pd.DataFrame([
            {"entry_date":"2024-01-02","exit_date":"2024-01-04","entry":100,"quantity":1,"net_pnl_inr":0},
            {"entry_date":"2024-01-03","exit_date":"2024-01-05","entry":200,"quantity":1,"net_pnl_inr":0},
        ])
        result = chronological_trade_metrics(frame, 1000, self.calendar())
        self.assertEqual(result["avg_concurrent_positions"], 1.5)
        self.assertEqual(result["max_concurrent_positions"], 2)
        self.assertEqual(result["days_with_position_pct"], 100.0)
        self.assertEqual(result["avg_capital_exposure_pct"], 15.0)

    def test_starting_capital_is_initial_equity_peak(self):
        frame = pd.DataFrame([
            {"entry_date":"2024-01-02","exit_date":"2024-01-03","entry":100,"quantity":1,"net_pnl_inr":-100},
        ])
        result = chronological_trade_metrics(frame, 1000, self.calendar())
        self.assertEqual(result["max_drawdown_pct"], -10.0)


if __name__ == "__main__":
    unittest.main()
