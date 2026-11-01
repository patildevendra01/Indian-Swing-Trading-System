"""Fetch broad-market and sector index context from Yahoo Finance (indicative only)."""
import argparse
from pathlib import Path
import pandas as pd
import yfinance as yf

INDICES = {
    "NIFTY_50": "^NSEI",
    "NIFTY_BANK": "^NSEBANK",
    "NIFTY_IT": "^CNXIT",
    "NIFTY_AUTO": "^CNXAUTO",
    "NIFTY_PHARMA": "^CNXPHARMA",
    "NIFTY_FMCG": "^CNXFMCG",
    "NIFTY_METAL": "^CNXMETAL",
    "NIFTY_REALTY": "^CNXREALTY",
}


def summarize_index(name: str, ticker: str, period: str = "6mo") -> dict:
    data = yf.download(ticker, period=period, interval="1d", auto_adjust=True,
                       progress=False, threads=False)
    if data.empty:
        return {"index": name, "ticker": ticker, "status": "NO_DATA"}
    if isinstance(data.columns, pd.MultiIndex):
        data.columns = data.columns.get_level_values(0)
    close = data["Close"].dropna().astype(float)
    if len(close) < 50:
        return {"index": name, "ticker": ticker, "status": "INSUFFICIENT_HISTORY"}
    ema20 = close.ewm(span=20, adjust=False).mean()
    ema50 = close.ewm(span=50, adjust=False).mean()
    daily_pct = (close.iloc[-1] / close.iloc[-2] - 1) * 100
    trend = "BULLISH" if close.iloc[-1] > ema20.iloc[-1] > ema50.iloc[-1] else (
        "BEARISH" if close.iloc[-1] < ema20.iloc[-1] < ema50.iloc[-1] else "MIXED")
    return {"index": name, "ticker": ticker, "date": str(close.index[-1].date()),
            "close": round(float(close.iloc[-1]), 2),
            "daily_change_pct": round(float(daily_pct), 2),
            "ema20": round(float(ema20.iloc[-1]), 2),
            "ema50": round(float(ema50.iloc[-1]), 2), "trend": trend,
            "status": "INDICATIVE"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", default="market_context.csv")
    parser.add_argument("--period", default="6mo")
    args = parser.parse_args()
    rows = []
    for name, ticker in INDICES.items():
        try:
            row = summarize_index(name, ticker, args.period)
        except Exception as exc:
            row = {"index": name, "ticker": ticker, "status": "ERROR", "reason": str(exc)}
        rows.append(row)
        print(f"{name}: {row.get('trend', row['status'])}")
    pd.DataFrame(rows).to_csv(args.output, index=False)
    print(f"Saved index context to {args.output}; verify live levels independently.")


if __name__ == "__main__":
    main()
