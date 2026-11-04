"""Research-only stock relative-strength study versus NIFTY 50."""
import argparse
from pathlib import Path
import pandas as pd
import yaml

try:
    from .backtest import load_or_download_history
    from .scan import yahoo_symbol
except ImportError:
    from src.backtest import load_or_download_history
    from src.scan import yahoo_symbol


def _close_series(frame):
    if "Close" not in frame:
        raise ValueError("Price history must contain Close")
    s = pd.to_numeric(frame["Close"], errors="coerce").dropna().copy()
    idx = pd.to_datetime(s.index)
    if getattr(idx, "tz", None) is not None:
        idx = idx.tz_localize(None)
    s.index = idx.normalize()
    return s[~s.index.duplicated(keep="last")].sort_index()


def relative_return(stock_frame, market_frame, signal_date, lookback=20):
    """Return stock, NIFTY and excess returns using closes on/before signal date."""
    if lookback < 1:
        raise ValueError("lookback must be at least 1")
    stock, market = _close_series(stock_frame), _close_series(market_frame)
    date = pd.Timestamp(signal_date)
    if date.tzinfo is not None:
        date = date.tz_localize(None)
    date = date.normalize()
    stock = stock.loc[stock.index <= date]
    market = market.loc[market.index <= date]
    if len(stock) <= lookback or len(market) <= lookback:
        return None
    stock_ret = (float(stock.iloc[-1]) / float(stock.iloc[-lookback-1]) - 1) * 100
    market_ret = (float(market.iloc[-1]) / float(market.iloc[-lookback-1]) - 1) * 100
    return {"stock_return_pct": stock_ret, "nifty_return_pct": market_ret,
            "relative_strength_pct": stock_ret - market_ret,
            "stock_data_date": stock.index[-1].strftime("%Y-%m-%d"),
            "nifty_data_date": market.index[-1].strftime("%Y-%m-%d")}


def strength_bucket(value, threshold=2.0):
    """Fixed ex-ante bands; ±2 percentage points is considered in-line."""
    if pd.isna(value):
        return "unavailable"
    if value >= threshold:
        return "outperforming_by_2pp_or_more"
    if value <= -threshold:
        return "underperforming_by_2pp_or_more"
    return "within_plus_minus_2pp"


def attach_relative_strength(trades, market_frame, stock_histories, lookback=20):
    if "symbol" not in trades or "signal_date" not in trades:
        raise ValueError("Trade file must contain symbol and signal_date")
    rows = []
    for _, trade in trades.iterrows():
        stock = stock_histories.get(str(trade["symbol"]))
        metrics = relative_return(stock, market_frame, trade["signal_date"], lookback) if stock is not None else None
        row = trade.to_dict()
        if metrics is None:
            row.update({"stock_return_pct": None, "nifty_return_pct": None,
                        "relative_strength_pct": None, "stock_data_date": "",
                        "nifty_data_date": "", "relative_strength_bucket": "unavailable"})
        else:
            row.update({k: round(v, 4) if isinstance(v, float) else v for k, v in metrics.items()})
            row["relative_strength_bucket"] = strength_bucket(metrics["relative_strength_pct"])
        rows.append(row)
    return pd.DataFrame(rows)


def summarize_cohorts(trades, min_trades=1):
    required = {"period", "relative_strength_bucket", "net_pnl_inr", "net_r_multiple"}
    missing = required - set(trades.columns)
    if missing:
        raise ValueError(f"Trade data missing columns: {', '.join(sorted(missing))}")
    rows = []
    for (period, bucket), group in trades.groupby(["period", "relative_strength_bucket"], sort=True):
        if len(group) < min_trades:
            continue
        pnl = pd.to_numeric(group["net_pnl_inr"], errors="coerce").dropna()
        r = pd.to_numeric(group["net_r_multiple"], errors="coerce").dropna()
        gp, gl = pnl[pnl > 0].sum(), -pnl[pnl < 0].sum()
        rows.append({"period": period, "relative_strength_bucket": bucket, "trades": len(group),
            "win_rate_pct": round(float((pnl > 0).mean() * 100), 2) if len(pnl) else 0.0,
            "net_pnl_inr": round(float(pnl.sum()), 2),
            "profit_factor": round(float(gp / gl), 3) if gl else (float("inf") if gp else 0.0),
            "average_r": round(float(r.mean()), 3) if len(r) else None})
    return pd.DataFrame(rows)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", default="backtest_trades.csv")
    parser.add_argument("--data-dir", default="backtest_data")
    parser.add_argument("--config", default="config.yaml")
    parser.add_argument("--min-trades", type=int, default=20)
    parser.add_argument("--lookback", type=int, default=20)
    args = parser.parse_args()
    if args.min_trades < 1 or args.lookback < 1:
        parser.error("--min-trades and --lookback must be at least 1")
    trades = pd.read_csv(args.input)
    with open(args.config, encoding="utf-8") as handle:
        cfg = yaml.safe_load(handle)
    exchange = cfg["market"].get("exchange", "NSE")
    bt = cfg.get("backtest", {})
    market, market_meta = load_or_download_history("^NSEI", args.data_dir,
        bt.get("history_period", "5y"))
    if market.empty:
        raise SystemExit("NIFTY 50 history unavailable; no relative-strength report generated.")
    histories = {}
    for symbol in trades["symbol"].dropna().astype(str).unique():
        ticker = yahoo_symbol(symbol, exchange)
        frame, _ = load_or_download_history(ticker, args.data_dir, bt.get("history_period", "5y"))
        if not frame.empty:
            histories[symbol] = frame
    enriched = attach_relative_strength(trades, market, histories, args.lookback)
    enriched.to_csv("relative_strength_tagged_trades.csv", index=False)
    summary = summarize_cohorts(enriched, args.min_trades)
    summary.to_csv("relative_strength_cohort_summary.csv", index=False)
    report = ["# Stock Relative-Strength Study vs NIFTY 50", "",
        f"Relative strength = stock {args.lookback}-session return minus NIFTY 50 {args.lookback}-session return.",
        "Both returns use the latest available close on or before the signal date and the close exactly one lookback window earlier.",
        "Fixed buckets: outperforming by at least +2 percentage points; within ±2pp; underperforming by at least -2pp.",
        f"NIFTY data source: {market_meta.get('source', 'unknown')}; rows: {market_meta.get('rows', len(market))}.", "",
        f"## Cohort results (minimum trades: {args.min_trades})", "",
        summary.to_string(index=False) if not summary.empty else "No cohorts met the minimum trade count.", "",
        "## Interpretation and guardrails", "",
        "- Development cohorts may motivate one pre-specified hypothesis; do not optimize bucket thresholds repeatedly.",
        "- OOS figures are descriptive only and must not be used to select or tune a filter.",
        "- These are existing baseline trades grouped by a pre-signal measure, not a portfolio re-simulation.",
        "- Missing/short histories are labelled unavailable; check cohort counts and coverage before interpretation.",
        "- This is price relative strength, not risk-adjusted performance or sector-neutral strength.",
        "- Yahoo Finance data can be revised, delayed or incomplete; use the same cached snapshot for comparisons.",
        "- No scanner, baseline rules, account risk settings, or live-trading behavior are changed.", ""]
    Path("relative_strength_research_report.md").write_text("\n".join(report), encoding="utf-8")
    print("Relative-strength cohort summary:")
    print(summary.to_string(index=False))
    print("\nSaved relative_strength_tagged_trades.csv, relative_strength_cohort_summary.csv, and relative_strength_research_report.md")
    print("Research-only; baseline scanner and backtest remain unchanged.")


if __name__ == "__main__":
    main()
