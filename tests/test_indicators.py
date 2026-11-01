import unittest
import pandas as pd
from src.indicators import add_indicators


class IndicatorTests(unittest.TestCase):
    def test_adds_expected_columns(self):
        idx = pd.date_range("2024-01-01", periods=100, freq="B")
        close = pd.Series(range(100, 200), index=idx, dtype=float)
        frame = pd.DataFrame({"Open": close, "High": close + 1, "Low": close - 1,
                              "Close": close, "Volume": 10000.0}, index=idx)
        out = add_indicators(frame)
        for column in ("ema_fast", "ema_slow", "rsi", "atr", "atr_pct",
                       "relative_volume", "prior_high", "avg_turnover"):
            self.assertIn(column, out.columns)
        self.assertGreater(out.iloc[-1].ema_fast, out.iloc[-1].ema_slow)
        self.assertLessEqual(out.iloc[-1].prior_high, out.iloc[-2].High)

    def test_rejects_missing_ohlcv(self):
        with self.assertRaises(ValueError):
            add_indicators(pd.DataFrame({"Close": [1, 2]}))


if __name__ == "__main__":
    unittest.main()
