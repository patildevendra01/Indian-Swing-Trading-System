import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import pandas as pd

from src.backtest import load_or_download_history


class DataSnapshotTests(unittest.TestCase):
    def sample_frame(self, close=101.0):
        return pd.DataFrame(
            {"Open": [100.0], "High": [102.0], "Low": [99.0],
             "Close": [close], "Adj Close": [close], "Volume": [1000]},
            index=pd.DatetimeIndex(["2025-01-02"], name="Date"),
        )

    def test_download_is_cached_and_reused(self):
        with tempfile.TemporaryDirectory() as folder:
            with patch("src.backtest.yf.download", return_value=self.sample_frame()) as download:
                first, first_meta = load_or_download_history("TEST.NS", folder)
                second, second_meta = load_or_download_history("TEST.NS", folder)
            self.assertEqual(download.call_count, 1)
            self.assertEqual(first_meta["source"], "download")
            self.assertEqual(second_meta["source"], "cache")
            pd.testing.assert_frame_equal(first, second, check_dtype=False)

    def test_refresh_replaces_cached_snapshot(self):
        with tempfile.TemporaryDirectory() as folder:
            with patch("src.backtest.yf.download", side_effect=[
                self.sample_frame(101.0), self.sample_frame(105.0)
            ]) as download:
                load_or_download_history("TEST.NS", folder)
                refreshed, metadata = load_or_download_history("TEST.NS", folder, refresh=True)
            self.assertEqual(download.call_count, 2)
            self.assertEqual(metadata["source"], "download")
            self.assertEqual(float(refreshed["Close"].iloc[0]), 105.0)

    def test_empty_download_is_not_cached(self):
        with tempfile.TemporaryDirectory() as folder:
            with patch("src.backtest.yf.download", return_value=pd.DataFrame()):
                frame, metadata = load_or_download_history("EMPTY.NS", folder)
            self.assertTrue(frame.empty)
            self.assertEqual(metadata["source"], "download_empty")
            self.assertEqual(list(Path(folder).glob("*.csv")), [])


if __name__ == "__main__":
    unittest.main()
