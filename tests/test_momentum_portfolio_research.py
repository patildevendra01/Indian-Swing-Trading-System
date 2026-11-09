import tempfile
import unittest
from pathlib import Path

import pandas as pd

from src.momentum_portfolio_research import _run_portfolio, _read_bars


class FlatCostModel:
    def calculate(self, entry_price, exit_price, quantity):
        return {"total_charges_inr": 0.0}


def config(data_dir):
    return {
        "_data_dir": str(data_dir),
        "account": {
            "capital_inr": 15000,
            "risk_per_trade_pct": 0.5,
            "max_position_pct": 25.0,
            "max_open_positions": 3,
        },
    }


class MomentumPortfolioTests(unittest.TestCase):
    def test_next_session_entry_and_fixed_horizon_exit(self):
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp)
            dates = pd.bdate_range("2026-01-05", periods=7)
            bars = pd.DataFrame({
                "Date": dates,
                "Open": [100, 101, 102, 103, 104, 105, 106],
                "High": [101, 102, 103, 104, 105, 106, 107],
                "Low": [99, 100, 101, 102, 103, 104, 105],
                "Close": [100, 101, 102, 103, 104, 105, 106],
                "Volume": [1000] * 7,
            })
            bars.to_csv(folder / "AAA_NS.csv", index=False)
            loaded = _read_bars(folder / "AAA_NS.csv")
            self.assertEqual(len(loaded), 7)

            candidates = pd.DataFrame([{
                "signal_date": dates[0], "symbol": "AAA",
                "signal_close": 100.0, "signal_atr": 1.0,
                "return_63_pct": 8.0, "return_126_pct": 15.0,
                "relative_63_pct": 3.0, "relative_126_pct": 5.0,
                "momentum_score": 0.04,
            }])
            trades, rejected, summary = _run_portfolio(
                candidates, dates, "development", dates[0],
                dates[-1] + pd.Timedelta(days=1), 2,
                config(folder), FlatCostModel(), 0.0
            )
            self.assertEqual(len(trades), 1)
            self.assertTrue(rejected.empty)
            self.assertEqual(trades.iloc[0]["entry_date"], str(dates[1].date()))
            self.assertEqual(trades.iloc[0]["exit_date"], str(dates[2].date()))
            self.assertEqual(trades.iloc[0]["holding_sessions"], 2)
            self.assertEqual(trades.iloc[0]["exit_reason"], "time_exit")
            self.assertEqual(summary["accepted_trades"], 1)
            self.assertEqual(summary["max_concurrent_positions"], 1)
            self.assertAlmostEqual(summary["ending_equity_inr"], 15000 + summary["net_pnl_inr"], places=2)

    def test_stop_is_checked_before_time_exit(self):
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp)
            dates = pd.bdate_range("2026-02-02", periods=6)
            bars = pd.DataFrame({
                "Date": dates,
                "Open": [100, 101, 96, 97, 98, 99],
                "High": [101, 102, 98, 98, 99, 100],
                "Low": [99, 100, 95, 96, 97, 98],
                "Close": [100, 101, 97, 97, 98, 99],
            })
            bars.to_csv(folder / "AAA_NS.csv", index=False)
            candidates = pd.DataFrame([{
                "signal_date": dates[0], "symbol": "AAA",
                "signal_close": 100.0, "signal_atr": 1.0,
                "return_63_pct": 8.0, "return_126_pct": 15.0,
                "relative_63_pct": 3.0, "relative_126_pct": 5.0,
                "momentum_score": 0.04,
            }])
            trades, _, _ = _run_portfolio(
                candidates, dates, "development", dates[0],
                dates[-1] + pd.Timedelta(days=1), 3,
                config(folder), FlatCostModel(), 0.0
            )
            self.assertEqual(len(trades), 1)
            self.assertEqual(trades.iloc[0]["exit_reason"], "stop_gap")
            self.assertEqual(trades.iloc[0]["exit"], 96.0)


    def test_trade_cannot_cross_period_boundary(self):
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp)
            dates = pd.bdate_range("2026-03-02", periods=6)
            bars = pd.DataFrame({
                "Date": dates, "Open": [100] * 6, "High": [101] * 6,
                "Low": [99] * 6, "Close": [100] * 6,
            })
            bars.to_csv(folder / "AAA_NS.csv", index=False)
            candidates = pd.DataFrame([{
                "signal_date": dates[1], "symbol": "AAA",
                "signal_close": 100.0, "signal_atr": 1.0,
                "return_63_pct": 8.0, "return_126_pct": 15.0,
                "relative_63_pct": 3.0, "relative_126_pct": 5.0,
                "momentum_score": 0.04,
            }])
            trades, _, summary = _run_portfolio(
                candidates, dates, "development", dates[0],
                dates[3], 2, config(folder), FlatCostModel(), 0.0
            )
            self.assertTrue(trades.empty)
            self.assertEqual(summary["accepted_trades"], 0)
            self.assertEqual(summary["ending_equity_inr"], 15000.0)


if __name__ == "__main__":
    unittest.main()
