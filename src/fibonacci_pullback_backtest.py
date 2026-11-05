"""Isolated daily-bar Fibonacci pullback-entry research backtest.

This is deliberately separate from the production scanner and baseline backtest.
It uses confirmed daily pivots, next-session entries, conservative OHLC exits,
existing risk sizing, Indian delivery-cost estimates, and explicit limitations:
symbols are simulated independently, not as a shared-capital portfolio.
"""
import argparse
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

try:
    from .backtest import classify_exit, load_or_download_history
    from .costs import load_cost_model
    from .fibonnaci_research import confirmed_pivots
    from .risk import build_trade_plan
    from .scan import yahoo_symbol
except ImportError:
    from src.backtest import classify_exit, load_or_download_history
    from src.costs import load_cost_model
    from src.fibonacci_research import confirmed_pivots
    from src.risk import build_trade_plan
    from src.scan import yahoo_symbol


RATIOS = {"fib_050": 0.50, "fib_0618": 0.618, "fib_066": 0.66, "fib_0786": 0.786}


def latest_confirmed_uptrend_leg(pivots, asof_index):
    """Return the latest confirmed low-high-low-high HH/HL impulse.

    Every pivot must have been confirmed by asof_index. The returned impulse is
    the second low-to-high leg in a chronological higher-low/higher-high sequence.
    """
    available = [p for p in pivots if int(p["confirmed_index"]) <= int(asof_index)]
    lows = [p for p in available if p["kind"] == "low"]
    highs = [p for p in available if p["kind"] == "high"]
    for high2 in reversed(highs):
        low2s = [p for p in lows if p["index"] < high2["index"]]
        if not low2s:
            continue
        low2 = low2s[-1]
        high1s = [p for p in highs if p["index"] < low2["index"]]
        if not high1s:
            continue
        high1 = high1s[-1]
        low1s = [p for p in lows if p["index"] < high1["index"]]
        if not low1s:
            continue
        low1 = low1s[-1]
        if (low2["price"] > low1["price"]
                and high2["price"] > high1["price"]
                and low1["index"] < high1["index"] < low2["index"] < high2["index"]
                and high2["price"] > low2["price"] > 0):
            return {
                "swing_low": float(low2["price"]),
                "swing_high": float(high2["price"]),
                "low_index": int(low2["index"]),
                "high_index": int(high2["index"]),
                "confirmed_index": int(high2["confirmed_index"]),
            }
    return None


def simulate_fibonacci_symbol(frame, symbol, cfg, ratio_name, ratio,
                              cost_model, slippage_bps=5.0, max_gap_pct=2.5,
                              max_wait_bars=20, left_bars=3, right_bars=3,
                              signal_start=None, signal_end=None):
    """Simulate one ratio for one symbol; all prices are daily OHLC adjusted bars."""
    data = frame.copy().sort_index()
    required = {"Open", "High", "Low", "Close"}
    missing = required.difference(data.columns)
    if missing:
        raise ValueError(f"History missing columns: {sorted(missing)}")
    data = data.dropna(subset=["Open", "High", "Low", "Close"])
    if len(data) < 120:
        return []
    pivots = confirmed_pivots(data, len(data) - 1, left_bars, right_bars)
    account = cfg["account"]
    strategy = cfg["strategy"]
    capital = float(account["capital_inr"])
    risk_pct = float(account["risk_per_trade_pct"])
    max_position_pct = float(account["max_position_pct"])
    reward_risk = float(strategy.get("min_reward_risk", 2.0))
    max_hold = int(strategy.get("holding_days_max", 10))
    atr_period = int(strategy.get("atr_period", 14))
    # Wilder-style ATR, calculated using data available up to each signal bar.
    previous_close = data["Close"].shift(1)
    tr = pd.concat([
        data["High"] - data["Low"],
        (data["High"] - previous_close).abs(),
        (data["Low"] - previous_close).abs(),
    ], axis=1).max(axis=1)
    atr = tr.ewm(alpha=1 / atr_period, adjust=False).mean()

    trades = []
    i = 100
    while i < len(data) - 1:
        date = data.index[i]
        if signal_start is not None and date < pd.Timestamp(signal_start):
            i += 1
            continue
        if signal_end is not None and date >= pd.Timestamp(signal_end):
            break
        leg = latest_confirmed_uptrend_leg(pivots, i)
        if leg is None or i - leg["confirmed_index"] > max_wait_bars:
            i += 1
            continue
        span = leg["swing_high"] - leg["swing_low"]
        level = leg["swing_high"] - ratio * span
        row = data.iloc[i]
        previous = data.iloc[i - 1]
        op, hi, lo, close = map(float, (row["Open"], row["High"], row["Low"], row["Close"]))
        # A touch plus a bullish close back above the level is the fixed trigger.
        if not (lo <= level and close > level and close > op and close > float(previous["Close"])):
            i += 1
            continue

        entry_idx = i + 1
        raw_entry = float(data.iloc[entry_idx]["Open"])
        gap_pct = (raw_entry / close - 1.0) * 100.0 if close else float("inf")
        if raw_entry <= 0 or abs(gap_pct) > max_gap_pct:
            i += 1
            continue
        signal_atr = float(atr.iloc[i])
        if not np.isfinite(signal_atr) or signal_atr <= 0:
            i += 1
            continue
        stop = leg["swing_low"] - 0.25 * signal_atr
        effective_entry = raw_entry * (1.0 + slippage_bps / 10000.0)
        try:
            plan = build_trade_plan(effective_entry, stop, capital, risk_pct,
                                    max_position_pct, reward_risk)
        except ValueError:
            i += 1
            continue
        quantity, target = plan.quantity, plan.target
        last_idx = min(entry_idx + max_hold - 1, len(data) - 1)
        intended_last = entry_idx + max_hold - 1
        exit_price = exit_reason = None
        exit_idx = None
        for j in range(entry_idx, last_idx + 1):
            bar = data.iloc[j]
            exit_price, exit_reason = classify_exit(
                float(bar["Open"]), float(bar["High"]), float(bar["Low"]),
                stop, target)
            if exit_price is None and j == last_idx and intended_last < len(data):
                exit_price, exit_reason = float(bar["Close"]), "time_exit"
            if exit_price is not None:
                exit_idx = j
                break
        if exit_price is None:
            break
        effective_exit = float(exit_price) * (1.0 - slippage_bps / 10000.0)
        gross = (effective_exit - effective_entry) * quantity
        charges = cost_model.calculate(raw_entry, float(exit_price), quantity)
        net = gross - float(charges["total_charges_inr"])
        planned_risk = float(plan.planned_risk_inr)
        trades.append({
            "symbol": symbol, "setup": ratio_name,
            "signal_date": str(date.date()),
            "entry_date": str(data.index[entry_idx].date()),
            "exit_date": str(data.index[exit_idx].date()),
            "swing_low": round(leg["swing_low"], 4),
            "swing_high": round(leg["swing_high"], 4),
            "fib_level": round(level, 4), "ratio": ratio,
            "signal_close": round(close, 4), "entry": round(raw_entry, 4),
            "stop": round(stop, 4), "target": round(target, 4),
            "exit": round(float(exit_price), 4), "quantity": quantity,
            "holding_sessions": exit_idx - entry_idx + 1,
            "exit_reason": exit_reason, "gross_pnl_inr": round(gross, 2),
            "estimated_costs_inr": round(float(charges["total_charges_inr"]), 2),
            "net_pnl_inr": round(net, 2),
            "planned_risk_inr": round(planned_risk, 2),
            "net_r_multiple": round(net / planned_risk, 3) if planned_risk else None,
            "entry_gap_pct": round(gap_pct, 4),
            **{k: v for k, v in charges.items() if k != "total_charges_inr"},
        })
        capital += net
        # One position at a time per symbol; independent symbols still do not
        # share the account's cash or max-open-position limit in this phase.
        i = exit_idx + 1
    return trades


def summarize(trades, min_trades=20):
    rows = []
    if trades.empty:
        return pd.DataFrame(columns=["period", "setup", "trades", "meets_min_sample",
                                     "win_rate_pct", "net_pnl_inr", "profit_factor", "average_r"])
    for (period, setup), group in trades.groupby(["period", "setup"], sort=True):
        pnl = pd.to_numeric(group["net_pnl_inr"], errors="coerce").dropna()
        r = pd.to_numeric(group["net_r_multiple"], errors="coerce").dropna()
        gp = float(pnl[pnl > 0].sum())
        gl = float(-pnl[pnl < 0].sum())
        rows.append({
            "period": period, "setup": setup, "trades": len(group),
            "meets_min_sample": bool(len(group) >= min_trades),
            "win_rate_pct": round(float((pnl > 0).mean() * 100), 2) if len(pnl) else None,
            "net_pnl_inr": round(float(pnl.sum()), 2),
            "profit_factor": round(gp / gl, 3) if gl else (float("inf") if gp else 0.0),
            "average_r": round(float(r.mean()), 3) if len(r) else None,
        })
    return pd.DataFrame(rows)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default="config.yaml")
    parser.add_argument("--data-dir", default="backtest_data")
    parser.add_argument("--baseline", default="backtest_trades.csv")
    parser.add_argument("--output", default="fibonacci_pullback_trades.csv")
    parser.add_argument("--summary", default="fibonacci_pullback_summary.csv")
    parser.add_argument("--report", default="fibonacci_pullback_report.md")
    parser.add_argument("--cost-model", default="religare_basic_estimate")
    parser.add_argument("--cost-model-file", default="config/cost_models.example.yaml")
    parser.add_argument("--slippage-bps", type=float, default=5.0)
    parser.add_argument("--max-gap-pct", type=float, default=2.5)
    parser.add_argument("--max-wait-bars", type=int, default=20)
    parser.add_argument("--left-bars", type=int, default=3)
    parser.add_argument("--right-bars", type=int, default=3)
    parser.add_argument("--min-trades", type=int, default=20)
    args = parser.parse_args()
    if min(args.slippage_bps, args.max_gap_pct) < 0 or min(
            args.max_wait_bars, args.left_bars, args.right_bars, args.min_trades) < 1:
        parser.error("cost/gap values must be non-negative; bar/sample counts must be positive")

    with open(args.config, encoding="utf-8") as handle:
        cfg = yaml.safe_load(handle)
    cost_model = load_cost_model(args.cost_model_file, args.cost_model)
    histories = {}
    for symbol in cfg.get("watchlist", []):
        ticker = yahoo_symbol(symbol, cfg["market"].get("exchange", "NSE"))
        frame, _ = load_or_download_history(
            ticker, args.data_dir, cfg.get("backtest", {}).get("history_period", "5y"))
        if not frame.empty:
            histories[symbol] = frame

    if not histories:
        raise SystemExit("No cached/downloaded symbol histories available.")
    earliest = min(frame.index.min() for frame in histories.values())
    latest = max(frame.index.max() for frame in histories.values())
    split = earliest + pd.DateOffset(years=3)
    periods = [
        ("development_3y", earliest, split),
        ("out_of_sample_2y", split, latest + pd.Timedelta(days=1)),
    ]
    all_rows = []
    for symbol, frame in histories.items():
        for setup, ratio in RATIOS.items():
            for period, start, end in periods:
                rows = simulate_fibonacci_symbol(
                    frame, yahoo_symbol(symbol, cfg["market"].get("exchange", "NSE")),
                    cfg, setup, ratio, cost_model, args.slippage_bps,
                    args.max_gap_pct, args.max_wait_bars, args.left_bars,
                    args.right_bars, start, end)
                all_rows.extend([{**row, "period": period} for row in rows])

    result = pd.DataFrame(all_rows)
    result.to_csv(args.output, index=False)
    summary = summarize(result, args.min_trades)
    # Append the already-computed baseline as a reference; do not recompute or tune it.
    try:
        baseline = pd.read_csv(args.baseline)
        baseline_rows = []
        for period, group in baseline.groupby("period"):
            pnl = pd.to_numeric(group["net_pnl_inr"], errors="coerce").dropna()
            r = pd.to_numeric(group["net_r_multiple"], errors="coerce").dropna()
            gp, gl = float(pnl[pnl > 0].sum()), float(-pnl[pnl < 0].sum())
            baseline_rows.append({
                "period": period, "setup": "baseline_existing",
                "trades": len(group), "meets_min_sample": len(group) >= args.min_trades,
                "win_rate_pct": round(float((pnl > 0).mean() * 100), 2) if len(pnl) else None,
                "net_pnl_inr": round(float(pnl.sum()), 2),
                "profit_factor": round(gp / gl, 3) if gl else (float("inf") if gp else 0.0),
                "average_r": round(float(r.mean()), 3) if len(r) else None,
            })
        summary = pd.concat([pd.DataFrame(baseline_rows), summary], ignore_index=True)
    except FileNotFoundError:
        pass
    summary.to_csv(args.summary, index=False)
    report = [
        "# Fibonacci Pullback Entry Research",
        "",
        "Research-only experiment. The production scanner and baseline strategy are unchanged.",
        "",
        f"- Pivot confirmation: {args.left_bars} bars left / {args.right_bars} bars right.",
        f"- Pullback window after confirmed impulse high: at most {args.max_wait_bars} sessions.",
        "- Entry trigger: daily low touches the selected retracement; close finishes above it, above the day's open, and above prior close.",
        "- Execution: next session open, adverse slippage applied; signals beyond the configured opening gap are rejected.",
        f"- Stop: 0.25 signal-date ATR below the impulse higher low; target: {cfg['strategy'].get('min_reward_risk', 2.0):g}R.",
        f"- Maximum holding: {cfg['strategy'].get('holding_days_max', 10)} sessions; same-day stop/target ambiguity assumes stop first.",
        f"- Costs: {args.cost_model}; slippage: {args.slippage_bps:g} bps per side.",
        "- Ratios are reported separately and are not selected by looking at out-of-sample results.",
        "- Symbols are simulated independently with one open position per symbol; this is NOT a shared-capital portfolio backtest.",
        "- Current watchlist survivorship, adjusted-price history, OHLC intraday ordering, corporate actions and estimated fee schedule remain limitations.",
        "- The existing out-of-sample period has already been examined in earlier research; treat it as exploratory, not a fresh untouched validation set.",
        "- No live trading, scanner changes, or risk-setting changes are authorized by these results.",
        "",
        "## Results",
        "",
        summary.to_string(index=False) if not summary.empty else "No completed trades.",
        "",
        "## Promotion criteria",
        "",
        "Do not promote this setup from these independent-symbol results alone. Any candidate must next pass a shared-capital portfolio simulation with the configured ₹15,000 capital, maximum 3 concurrent positions, 0.5% risk budget per entry, 25% maximum position value, realistic costs, and a genuinely future paper-trading validation window.",
        "",
    ]
    Path(args.report).write_text("\n".join(report), encoding="utf-8")
    print("Fibonacci pullback summary:")
    print(summary.to_string(index=False))
    print(f"\nSaved {args.output}, {args.summary}, and {args.report}")
    print("Research only: no production scanner or baseline rules changed.")


if __name__ == "__main__":
    main()
