import unittest
import pandas as pd

from src.backtest import classify_exit, simulate_symbol


def sample_config():
    return {
        "market": {"exchange": "NSE"},
        "account": {"capital_inr": 15000, "risk_per_trade_pct": 0.5,
                    "max_position_pct": 25.0},
        "strategy": {"holding_days_min": 3, "holding_days_max": 3,
                     "min_reward_risk": 2.0, "ema_fast": 20, "ema_slow": 50,
                     "rsi_period": 14, "atr_period": 14, "volume_lookback": 20,
                     "min_relative_volume": 1.5, "breakout_lookback": 20,
                     "min_price_inr": 50, "min_avg_daily_turnover_inr": 1000,
                     "max_atr_pct": 6.0},
    }


def qualifying_frame(periods=104):
    idx = pd.date_range("2025-01-01", periods=periods, freq="B")
    close = [100.0] * periods
    data = pd.DataFrame({
        "Open": close, "High": [101.0] * periods, "Low": [99.0] * periods,
        "Close": close, "Volume": [10000.0] * periods,
        "ema_fast": [99.0] * periods, "ema_slow": [98.0] * periods,
        "rsi": [60.0] * periods, "relative_volume": [2.0] * periods,
        "prior_high": [99.0] * periods, "avg_turnover": [1_000_000.0] * periods,
        "atr": [2.0] * periods, "atr_pct": [2.0] * periods,
    }, index=idx)
    # Only bar 100 is a signal; the next three sessions are the holding window.
    data.loc[data.index[100], "Close"] = 100.0
    data.loc[data.index[100], "prior_high"] = 99.0
    for bar in range(101, min(104, periods)):
        data.loc[data.index[bar], ["Open", "High", "Low", "Close"]] = [100, 101, 99, 100]
    return data


class BacktestLogicTests(unittest.TestCase):
    def test_gap_through_stop_exits_at_open(self):
        self.assertEqual(classify_exit(95, 98, 94, 97, 106), (95, "stop_gap"))

    def test_gap_through_target_exits_at_open(self):
        self.assertEqual(classify_exit(108, 110, 107, 97, 106), (108, "target_gap"))

    def test_both_hit_same_bar_assumes_stop_first(self):
        self.assertEqual(classify_exit(100, 107, 96, 97, 106),
                         (97, "both_hit_stop_assumed"))

    def test_holding_window_counts_entry_session_as_session_one(self):
        trades, diag = simulate_symbol(qualifying_frame(104), "TEST.NS", sample_config(),
                                       cost_bps=0, slippage_bps=0)
        self.assertEqual(diag["raw_signals"], 1)
        self.assertEqual(len(trades), 1)
        self.assertEqual(trades[0]["holding_sessions"], 3)
        self.assertEqual(trades[0]["exit_reason"], "time_exit")

    def test_incomplete_final_holding_window_is_not_a_completed_time_exit(self):
        trades, diag = simulate_symbol(qualifying_frame(103), "TEST.NS", sample_config(),
                                       cost_bps=0, slippage_bps=0)
        self.assertEqual(trades, [])
        self.assertEqual(diag["truncated_positions"], 1)


if __name__ == "__main__":
    unittest.main()


class FilterDiagnosticTests(unittest.TestCase):
    def test_filter_diagnostics_count_passes_and_fails(self):
        from src.backtest import count_filter_passes
        frame = qualifying_frame(104)
        counts = count_filter_passes(frame, sample_config())
        self.assertEqual(counts["bars_evaluated"], 4)
        self.assertEqual(counts["raw_signals"], 4)
        self.assertEqual(counts["trend_pass"], 4)
        self.assertEqual(counts["trend_fail"], 0)
