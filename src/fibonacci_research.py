"""Research-only Fibonacci pullback diagnostics for existing baseline trades.

This module labels historical baseline trades; it does not create signals,
change entries/exits, or modify the scanner/backtester.
"""
import argparse
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

try:
    from .backtest import load_or_download_history
    from .scan import yahoo_symbol
except ImportError:
    from src.backtest import load_or_download_history
    from src.scan import yahoo_symbol


FIB_LEVELS = (0.50, 0.618, 0.66, 0.786)
SETUP_COLUMNS = {
    "fib_050": 0.50,
    "fib_0618": 0.618,
    "fib_066": 0.66,
    "fib_0786": 0.786,
}


def _ohlc(frame):
    required = {"High", "Low", "Close"}
    missing = required.difference(frame.columns)
    if missing:
        raise ValueError(f"Price history missing columns: {sorted(missing)}")
    data = frame.loc[:, ["High", "Low", "Close"]].copy().sort_index()
    idx = pd.to_datetime(data.index)
    if getattr(idx, "tz", None) is not None:
        idx = idx.tz_localize(None)
    data.index = idx.normalize()
    data = data[~data.index.duplicated(keep="last")]
    for col in ("High", "Low", "Close"):
        data[col] = pd.to_numeric(data[col], errors="coerce")
    return data.dropna()


def confirmed_pivots(frame, asof_index, left_bars=3, right_bars=3):
    """Return pivots confirmed by asof_index; future bars are never consulted.

    A pivot at j is only available from j + right_bars onward. The asymmetric
    comparisons make flat-topped/bottomed plateaus deterministic.
    """
    if left_bars < 1 or right_bars < 1:
        raise ValueError("left_bars and right_bars must be at least 1")
    data = _ohlc(frame)
    asof_index = int(asof_index)
    if asof_index < 0 or asof_index >= len(data):
        raise IndexError("asof_index is outside the price history")
    highs = data["High"].to_numpy(dtype=float)
    lows = data["Low"].to_numpy(dtype=float)
    pivots = []
    last_candidate = asof_index - right_bars
    for j in range(left_bars, last_candidate + 1):
        left_high = highs[j-left_bars:j]
        right_high = highs[j+1:j+right_bars+1]
        left_low = lows[j-left_bars:j]
        right_low = lows[j+1:j+right_bars+1]
        if len(right_high) != right_bars:
            continue
        if highs[j] >= left_high.max() and highs[j] > right_high.max():
            pivots.append({"kind": "high", "index": j, "price": highs[j],
                           "confirmed_index": j + right_bars})
        if lows[j] <= left_low.min() and lows[j] < right_low.min():
            pivots.append({"kind": "low", "index": j, "price": lows[j],
                           "confirmed_index": j + right_bars})
    return sorted(pivots, key=lambda item: (item["index"], item["kind"]))


def latest_confirmed_uptrend_leg(frame, asof_index, left_bars=3, right_bars=3):
    """Find a confirmed higher-high/higher-low impulse ending in a swing high."""
    data = _ohlc(frame)
    pivots = confirmed_pivots(data, asof_index, left_bars, right_bars)
    lows = [p for p in pivots if p["kind"] == "low"]
    highs = [p for p in pivots if p["kind"] == "high"]
    if len(lows) < 2 or len(highs) < 2:
        return None
    previous_low, latest_low = lows[-2], lows[-1]
    previous_high, latest_high = highs[-2], highs[-1]
    if not (latest_low["price"] > previous_low["price"]
            and latest_high["price"] > previous_high["price"]
            and latest_low["index"] < latest_high["index"]):
        return None
    if latest_high["price"] <= latest_low["price"]:
        return None
    return {
        "swing_low": float(latest_low["price"]),
        "swing_high": float(latest_high["price"]),
        "swing_low_date": data.index[latest_low["index"]].strftime("%Y-%m-%d"),
        "swing_high_date": data.index[latest_high["index"]].strftime("%Y-%m-%d"),
        "swing_low_index": int(latest_low["index"]),
        "swing_high_index": int(latest_high["index"]),
    }


def fib_levels(swing_low, swing_high):
    """Price levels for an upward impulse retracing down from its swing high."""
    low, high = float(swing_low), float(swing_high)
    if not np.isfinite(low) or not np.isfinite(high) or low <= 0 or high <= low:
        raise ValueError("Require positive swing_low < swing_high")
    return {f"fib_{int(round(ratio * 1000)):04d}": high - ratio * (high - low)
            for ratio in FIB_LEVELS}


def tag_trade(trade, history, tolerance_pct=1.0, left_bars=3, right_bars=3):
    """Attach only information available at the trade's signal-date close."""
    if tolerance_pct < 0:
        raise ValueError("tolerance_pct must be non-negative")
    data = _ohlc(history)
    signal_date = pd.Timestamp(trade["signal_date"])
    if signal_date.tzinfo is not None:
        signal_date = signal_date.tz_localize(None)
    signal_date = signal_date.normalize()
    eligible = np.flatnonzero(data.index <= signal_date)
    if len(eligible) == 0:
        return {"fib_structure": "unavailable", "fib_signal_data_date": ""}
    asof = int(eligible[-1])
    leg = latest_confirmed_uptrend_leg(data, asof, left_bars, right_bars)
    result = {
        "fib_structure": "higher_high_higher_low" if leg else "no_confirmed_uptrend",
        "fib_signal_data_date": data.index[asof].strftime("%Y-%m-%d"),
        "fib_swing_low": None, "fib_swing_high": None,
        "fib_swing_low_date": "", "fib_swing_high_date": "",
    }
    for name in SETUP_COLUMNS:
        result[f"{name}_price"] = None
        result[f"{name}_distance_pct"] = None
        result[f"{name}_match"] = False
    result["fib_golden_pocket_match"] = False
    if leg is None:
        return result

    close = float(data.iloc[asof]["Close"])
    levels = fib_levels(leg["swing_low"], leg["swing_high"])
    result.update({
        "fib_swing_low": round(leg["swing_low"], 4),
        "fib_swing_high": round(leg["swing_high"], 4),
        "fib_swing_low_date": leg["swing_low_date"],
        "fib_swing_high_date": leg["swing_high_date"],
    })
    distances = {}
    for name, level_price in levels.items():
        distance = abs(close / level_price - 1.0) * 100 if level_price > 0 else float("inf")
        result[f"{name}_price"] = round(level_price, 4)
        result[f"{name}_distance_pct"] = round(distance, 4)
        result[f"{name}_match"] = bool(distance <= tolerance_pct)
        distances[name] = distance
    # Golden Pocket is the full 0.618–0.66 price band, with the same tolerance
    # applied to the nearest edge; it is not treated as a separate magic ratio.
    band_top = levels["fib_0618"]
    band_bottom = levels["fib_066"]
    if band_bottom > band_top:
        band_bottom, band_top = band_top, band_bottom
    gap = max(band_bottom - close, 0.0, close - band_top)
    result["fib_golden_pocket_match"] = bool(gap / close * 100 <= tolerance_pct)
    result["fib_nearest_level"] = min(distances, key=distances.get)
    result["fib_nearest_distance_pct"] = round(min(distances.values()), 4)
    return result


def attach_fibonacci_tags(trades, histories, tolerance_pct=1.0,
                          left_bars=3, right_bars=3):
    if not {"symbol", "signal_date"}.issubset(trades.columns):
        raise ValueError("Trade file must contain symbol and signal_date")
    rows = []
    for _, trade in trades.iterrows():
        row = trade.to_dict()
        history = histories.get(str(trade["symbol"]))
        if history is None or history.empty:
            tags = {"fib_structure": "history_unavailable",
                    "fib_signal_data_date": ""}
        else:
            tags = tag_trade(trade, history, tolerance_pct, left_bars, right_bars)
        row.update(tags)
        rows.append(row)
    return pd.DataFrame(rows)


def summarize_fibonacci_cohorts(trades, min_trades=1):
    required = {"period", "net_pnl_inr", "net_r_multiple"}
    missing = required.difference(trades.columns)
    if missing:
        raise ValueError(f"Trade data missing columns: {sorted(missing)}")
    setups = {"baseline_all": None, **SETUP_COLUMNS,
              "golden_pocket": "fib_golden_pocket_match"}
    rows = []
    for period, period_frame in trades.groupby("period", sort=True):
        for setup, column in setups.items():
            if setup == "baseline_all":
                group = period_frame
            elif setup == "golden_pocket":
                group = period_frame[period_frame[column].fillna(False).astype(bool)]
            else:
                group = period_frame[period_frame[f"{setup}_match"].fillna(False).astype(bool)]
            pnl = pd.to_numeric(group["net_pnl_inr"], errors="coerce").dropna()
            r = pd.to_numeric(group["net_r_multiple"], errors="coerce").dropna()
            gross_profit = float(pnl[pnl > 0].sum())
            gross_loss = float(-pnl[pnl < 0].sum())
            rows.append({
                "period": period, "setup": setup, "trades": len(group),
                "meets_min_sample": bool(len(group) >= min_trades),
                "win_rate_pct": round(float((pnl > 0).mean() * 100), 2) if len(pnl) else None,
                "net_pnl_inr": round(float(pnl.sum()), 2) if len(pnl) else 0.0,
                "profit_factor": round(gross_profit / gross_loss, 3) if gross_loss
                                 else (float("inf") if gross_profit else 0.0),
                "average_r": round(float(r.mean()), 3) if len(r) else None,
            })
    return pd.DataFrame(rows)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", default="backtest_trades.csv")
    parser.add_argument("--data-dir", default="backtest_data")
    parser.add_argument("--config", default="config.yaml")
    parser.add_argument("--tolerance-pct", type=float, default=1.0,
                        help="Maximum distance from a level/band as %% of signal close.")
    parser.add_argument("--left-bars", type=int, default=3)
    parser.add_argument("--right-bars", type=int, default=3,
                        help="Bars required to confirm a swing; confirmation must precede signal.")
    parser.add_argument("--min-trades", type=int, default=20)
    args = parser.parse_args()
    if args.min_trades < 1 or args.left_bars < 1 or args.right_bars < 1:
        parser.error("--min-trades, --left-bars and --right-bars must be at least 1")
    if args.tolerance_pct < 0:
        parser.error("--tolerance-pct must be non-negative")

    trades = pd.read_csv(args.input)
    required = {"symbol", "signal_date", "period", "net_pnl_inr", "net_r_multiple"}
    missing = required.difference(trades.columns)
    if missing:
        raise SystemExit(f"Trade file missing columns: {sorted(missing)}")
    with open(args.config, encoding="utf-8") as handle:
        cfg = yaml.safe_load(handle)
    exchange = cfg["market"].get("exchange", "NSE")
    history_period = cfg.get("backtest", {}).get("history_period", "5y")
    histories = {}
    for symbol in trades["symbol"].dropna().astype(str).unique():
        ticker = yahoo_symbol(symbol, exchange)
        frame, _ = load_or_download_history(ticker, args.data_dir, history_period)
        if not frame.empty:
            histories[symbol] = frame

    tagged = attach_fibonacci_tags(trades, histories, args.tolerance_pct,
                                   args.left_bars, args.right_bars)
    summary = summarize_fibonacci_cohorts(tagged, args.min_trades)
    tagged.to_csv("fibonacci_tagged_trades.csv", index=False)
    summary.to_csv("fibonacci_cohort_summary.csv", index=False)
    report = [
        "# Fibonacci Retracement Research (Descriptive Cohorts)",
        "",
        "This is a research-only tag of existing baseline trades. It does not simulate new pullback entries,",
        "change the baseline strategy, or establish that a Fibonacci filter causes better performance.",
        "",
        f"- Swing confirmation: {args.left_bars} bars left and {args.right_bars} bars right.",
        f"- Signal proximity tolerance: {args.tolerance_pct:.3f}% of signal-date close.",
        f"- Minimum sample flag: {args.min_trades} trades.",
        "- Long-side structure requires confirmed higher highs and higher lows.",
        "- Only pivots confirmed on or before the signal date are eligible; no future bars are used.",
        "- Ratios tested: 0.50, 0.618, 0.66, 0.786, plus the 0.618–0.66 Golden Pocket band.",
        "",
        "## Cohort results",
        "",
        summary.to_string(index=False) if not summary.empty else "No cohorts available.",
        "",
        "## Interpretation safeguards",
        "",
        "- The baseline_all row is the unfiltered reference for each period.",
        "- Cohorts overlap; do not add their trade counts together.",
        "- Small cohorts are descriptive only; a positive result is not proof of an edge.",
        "- The 1% proximity band and pivot settings are pre-specified research assumptions, not optimized values.",
        "- This study tags existing baseline trades; it cannot measure a new pullback-entry strategy's fills or stop/target path.",
        "- Any promising hypothesis requires a separately specified entry/exit simulation, realistic Indian delivery costs,",
        "  shared-capital constraints, and a fresh untouched out-of-sample period.",
        "- No scanner, baseline backtest, account risk settings, or live-trading behavior are changed.",
        "",
    ]
    Path("fibonacci_research_report.md").write_text("\n".join(report), encoding="utf-8")
    print("Fibonacci cohort summary:")
    print(summary.to_string(index=False))
    print("\nSaved fibonacci_tagged_trades.csv, fibonacci_cohort_summary.csv, and fibonacci_research_report.md")
    print("Research-only: baseline scanner and backtest rules remain unchanged.")


if __name__ == "__main__":
    main()
