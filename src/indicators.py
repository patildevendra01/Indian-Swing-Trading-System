"""Technical indicators calculated from daily OHLCV data."""
import numpy as np
import pandas as pd


def add_indicators(frame: pd.DataFrame, ema_fast: int = 20, ema_slow: int = 50,
                   rsi_period: int = 14, atr_period: int = 14,
                   volume_lookback: int = 20, breakout_lookback: int = 20) -> pd.DataFrame:
    required = {"Open", "High", "Low", "Close", "Volume"}
    missing = required.difference(frame.columns)
    if missing:
        raise ValueError(f"Missing OHLCV columns: {sorted(missing)}")
    df = frame.copy().sort_index()
    close = df["Close"].astype(float)
    high = df["High"].astype(float)
    low = df["Low"].astype(float)
    volume = df["Volume"].astype(float)

    df["ema_fast"] = close.ewm(span=ema_fast, adjust=False).mean()
    df["ema_slow"] = close.ewm(span=ema_slow, adjust=False).mean()
    delta = close.diff()
    gain = delta.clip(lower=0).ewm(alpha=1 / rsi_period, adjust=False).mean()
    loss = (-delta.clip(upper=0)).ewm(alpha=1 / rsi_period, adjust=False).mean()
    rs = gain / loss.replace(0, np.nan)
    df["rsi"] = 100 - (100 / (1 + rs))
    df.loc[(loss == 0) & (gain > 0), "rsi"] = 100
    df["rsi"] = df["rsi"].fillna(50)

    previous_close = close.shift(1)
    true_range = pd.concat([(high - low), (high - previous_close).abs(),
                            (low - previous_close).abs()], axis=1).max(axis=1)
    df["atr"] = true_range.ewm(alpha=1 / atr_period, adjust=False).mean()
    df["atr_pct"] = (df["atr"] / close) * 100
    df["avg_volume"] = volume.rolling(volume_lookback).mean()
    df["relative_volume"] = volume / df["avg_volume"].replace(0, np.nan)
    # Exclude today's candle from the prior-high breakout reference.
    df["prior_high"] = high.shift(1).rolling(breakout_lookback).max()
    df["avg_turnover"] = (close * volume).rolling(volume_lookback).mean()
    return df
