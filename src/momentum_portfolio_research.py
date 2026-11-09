"""Research-only NSE relative/absolute momentum portfolio backtest.

Signals use information available at the prior close; entries occur at the
next session open. Each horizon/period is an independent shared-capital run.
"""
import argparse
import math
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

try:
    from .costs import load_cost_model
except ImportError:
    from src.costs import load_cost_model


def _read_bars(path):
    frame = pd.read_csv(path)
    if "Date" in frame.columns:
        frame["Date"] = pd.to_datetime(frame["Date"], errors="coerce")
        frame = frame.set_index("Date")
    else:
        frame.index = pd.to_datetime(frame.index, errors="coerce")
    frame.index = pd.DatetimeIndex(frame.index).tz_localize(None).normalize()
    frame = frame[~frame.index.isna()].sort_index()
    frame = frame[~frame.index.duplicated(keep="last")]
    required = {"Open", "High", "Low", "Close"}
    missing = required - set(frame.columns)
    if missing:
        raise ValueError(f"{path} missing OHLC columns: {sorted(missing)}")
    for col in required:
        frame[col] = pd.to_numeric(frame[col], errors="coerce")
    return frame.dropna(subset=["Open", "High", "Low", "Close"])


def build_momentum_candidates(data_dir, symbols, index_file="INDEX_NSEI.csv"):
    """Build point-in-time candidate rows on NIFTY trading dates."""
    folder = Path(data_dir)
    market = _read_bars(folder / index_file)
    # The current NSE session may still be forming; use completed sessions only.
    today_ist = pd.Timestamp.now(tz="Asia/Kolkata").tz_localize(None).normalize()
    market = market.loc[market.index < today_ist]
    calendar = market.index
    market_close = market["Close"].reindex(calendar)
    market_63 = market_close / market_close.shift(63) - 1.0
    market_126 = market_close / market_close.shift(126) - 1.0
    candidates = []
    coverage = []

    for symbol in symbols:
        path = folder / f"{symbol}_NS.csv"
        if not path.exists():
            coverage.append({"symbol": symbol, "status": "missing_file"})
            continue
        bars = _read_bars(path).reindex(calendar)
        close = bars["Close"]
        prev_close = close.shift(1)
        true_range = pd.concat([
            bars["High"] - bars["Low"],
            (bars["High"] - prev_close).abs(),
            (bars["Low"] - prev_close).abs(),
        ], axis=1).max(axis=1)
        atr14 = true_range.rolling(14, min_periods=14).mean()
        sma50 = close.rolling(50, min_periods=50).mean()
        sma200 = close.rolling(200, min_periods=200).mean()
        ret63 = close / close.shift(63) - 1.0
        ret126 = close / close.shift(126) - 1.0
        rel63 = ret63 - market_63
        rel126 = ret126 - market_126
        eligible = (
            close.gt(sma50) & sma50.gt(sma200)
            & ret63.gt(0) & ret126.gt(0)
            & rel63.gt(0) & rel126.gt(0)
            & atr14.gt(0)
        )
        score = 0.5 * rel63 + 0.5 * rel126
        count = 0
        for date in calendar[eligible.fillna(False)]:
            row = {
                "signal_date": date,
                "symbol": symbol,
                "signal_close": float(close.loc[date]),
                "signal_atr": float(atr14.loc[date]),
                "return_63_pct": float(ret63.loc[date] * 100),
                "return_126_pct": float(ret126.loc[date] * 100),
                "relative_63_pct": float(rel63.loc[date] * 100),
                "relative_126_pct": float(rel126.loc[date] * 100),
                "momentum_score": float(score.loc[date]),
            }
            candidates.append(row)
            count += 1
        coverage.append({
            "symbol": symbol, "status": "loaded", "bars": int(close.notna().sum()),
            "first_date": str(close.first_valid_index().date()) if close.first_valid_index() is not None else "",
            "eligible_signal_days": count,
        })

    frame = pd.DataFrame(candidates)
    if not frame.empty:
        frame = frame.sort_values(
            ["signal_date", "momentum_score", "symbol"],
            ascending=[True, False, True], kind="mergesort"
        )
    return frame, pd.DataFrame(coverage), calendar


def _run_portfolio(candidates, calendar, period, start_date, end_date,
                   horizon, cfg, cost_model, slippage_bps):
    account = cfg["account"]
    capital = float(account["capital_inr"])
    risk_budget = capital * float(account["risk_per_trade_pct"]) / 100.0
    max_value = capital * float(account["max_position_pct"]) / 100.0
    max_positions = int(account["max_open_positions"])
    slip = slippage_bps / 10000.0
    cash = capital
    positions, pending = [], []
    trades, equity_rows, rejected = [], [], []
    peak_positions = 0
    by_date = {d: g.to_dict("records") for d, g in candidates.groupby("signal_date")} if not candidates.empty else {}
    bar_cache = {
        symbol: _read_bars(Path(cfg["_data_dir"]) / f"{symbol}_NS.csv")
        for symbol in candidates["symbol"].dropna().astype(str).unique()
    } if not candidates.empty else {}

    # Entry date must leave enough calendar sessions for the full holding horizon.
    for i in range(1, len(calendar) - horizon + 1):
        date = calendar[i]
        signal_date = calendar[i - 1]
        if date < start_date:
            continue
        can_enter = start_date <= signal_date < end_date

        # Release proceeds only on the session after the prior close exit.
        still_pending = []
        for item in pending:
            if item["release_date"] <= date:
                cash += item["cash_release"]
            else:
                still_pending.append(item)
        pending = still_pending

        todays = by_date.get(signal_date, []) if can_enter else []
        for candidate in todays:
            if len(positions) >= max_positions:
                rejected.append({"period": period, "horizon": horizon,
                                 "signal_date": str(signal_date.date()),
                                 "symbol": candidate["symbol"], "reason": "max_positions"})
                break
            if any(p["symbol"] == candidate["symbol"] for p in positions):
                continue
            bars = bar_cache[candidate["symbol"]]
            if date not in bars.index:
                continue
            raw_entry = float(bars.at[date, "Open"])
            stop = candidate["signal_close"] - 2.5 * candidate["signal_atr"]
            effective_entry = raw_entry * (1.0 + slip)
            risk_per_share = effective_entry - stop
            if raw_entry <= 0 or stop <= 0 or risk_per_share <= 0:
                rejected.append({"period": period, "horizon": horizon,
                                 "signal_date": str(signal_date.date()),
                                 "symbol": candidate["symbol"], "reason": "invalid_stop_or_entry"})
                continue
            qty = min(math.floor(risk_budget / risk_per_share),
                      math.floor(max_value / effective_entry),
                      math.floor(cash / effective_entry))
            if qty < 1:
                rejected.append({"period": period, "horizon": horizon,
                                 "signal_date": str(signal_date.date()),
                                 "symbol": candidate["symbol"], "reason": "insufficient_cash"})
                continue
            notional = effective_entry * qty
            cash -= notional
            positions.append({
                **candidate, "entry_date": date, "entry": raw_entry,
                "effective_entry": effective_entry, "stop": stop,
                "quantity": qty, "notional": notional,
                "held_sessions": 0, "horizon": horizon,
            })
            peak_positions = max(peak_positions, len(positions))

        # Check today's OHLC for stops/time exits. Cash is released tomorrow.
        remaining = []
        for pos in positions:
            bars = bar_cache[pos["symbol"]]
            if date not in bars.index:
                remaining.append(pos)
                continue
            bar = bars.loc[date]
            pos["held_sessions"] += 1
            op, hi, lo, cl = map(float, (bar["Open"], bar["High"], bar["Low"], bar["Close"]))
            exit_price, reason = None, None
            if op <= pos["stop"]:
                exit_price, reason = op, "stop_gap"
            elif lo <= pos["stop"]:
                exit_price, reason = pos["stop"], "stop"
            elif pos["held_sessions"] >= horizon:
                exit_price, reason = cl, "time_exit"
            if exit_price is None:
                remaining.append(pos)
                continue

            effective_exit = exit_price * (1.0 - slip)
            gross = (effective_exit - pos["effective_entry"]) * pos["quantity"]
            charges = cost_model.calculate(pos["entry"], exit_price, pos["quantity"])
            costs = float(charges["total_charges_inr"])
            net = gross - costs
            planned_risk = (pos["effective_entry"] - pos["stop"]) * pos["quantity"]
            trade = {
                "period": period, "horizon_sessions": horizon,
                "symbol": pos["symbol"], "signal_date": str(pos["signal_date"].date()),
                "entry_date": str(pos["entry_date"].date()), "exit_date": str(date.date()),
                "entry": round(pos["entry"], 4), "exit": round(exit_price, 4),
                "stop": round(pos["stop"], 4), "quantity": pos["quantity"],
                "holding_sessions": pos["held_sessions"], "exit_reason": reason,
                "momentum_score": pos["momentum_score"],
                "return_63_pct": pos["return_63_pct"], "return_126_pct": pos["return_126_pct"],
                "relative_63_pct": pos["relative_63_pct"], "relative_126_pct": pos["relative_126_pct"],
                "gross_pnl_inr": round(gross, 2), "estimated_costs_inr": round(costs, 2),
                "net_pnl_inr": round(net, 2), "net_r_multiple": round(net / planned_risk, 4)
                    if planned_risk > 0 else None,
            }
            trades.append(trade)
            pending.append({"release_date": calendar[i + 1] if i + 1 < len(calendar) else date,
                            "cash_release": pos["notional"] + net})
        positions = remaining

        # Mark-to-market equity includes cash, unsettled proceeds and open positions.
        open_value = 0.0
        for pos in positions:
            bars = bar_cache[pos["symbol"]]
            if date in bars.index:
                open_value += float(bars.at[date, "Close"]) * pos["quantity"]
        pending_value = sum(x["cash_release"] for x in pending)
        equity_rows.append({"date": date, "equity": cash + pending_value + open_value})

    trade_frame = pd.DataFrame(trades)
    equity = pd.DataFrame(equity_rows)
    if equity.empty:
        max_dd = 0.0
        ending = capital
    else:
        series = equity.set_index("date")["equity"]
        peaks = series.cummax().clip(lower=capital)
        max_dd = float(((series / peaks) - 1.0).min() * 100.0)
        ending = float(series.iloc[-1])
    pnl = trade_frame["net_pnl_inr"] if not trade_frame.empty else pd.Series(dtype=float)
    gp = float(pnl[pnl > 0].sum()) if len(pnl) else 0.0
    gl = float(-pnl[pnl < 0].sum()) if len(pnl) else 0.0
    summary = {
        "period": period, "horizon_sessions": horizon,
        "candidate_signals": int(sum(len(v) for d, v in by_date.items()
                                     if start_date <= d < end_date)),
        "accepted_trades": int(len(trade_frame)), "rejected_entries": len(rejected),
        "net_pnl_inr": round(float(pnl.sum()) if len(pnl) else 0.0, 2),
        "ending_equity_inr": round(ending, 2),
        "return_pct": round((ending / capital - 1.0) * 100.0, 2),
        "win_rate_pct": round(float((pnl > 0).mean() * 100.0), 2) if len(pnl) else 0.0,
        "profit_factor": round(gp / gl, 3) if gl else (float("inf") if gp else 0.0),
        "average_r": round(float(trade_frame["net_r_multiple"].mean()), 3) if len(trade_frame) else None,
        "max_daily_mark_to_market_drawdown_pct": round(max_dd, 2),
        "max_concurrent_positions": peak_positions,
    }
    return trade_frame, pd.DataFrame(rejected), summary


def run_research(data_dir, symbols, cfg, cost_model, slippage_bps=5.0,
                 horizons=(5, 10, 15), index_file="INDEX_NSEI.csv"):
    if slippage_bps < 0 or not np.isfinite(slippage_bps):
        raise ValueError("slippage_bps must be finite and non-negative")
    candidates, coverage, calendar = build_momentum_candidates(data_dir, symbols, index_file)
    if len(calendar) < 300:
        raise ValueError("At least 300 NIFTY sessions are required")
    cutoff = calendar[-1] - pd.DateOffset(years=2)
    development_start = calendar[200]
    cfg = dict(cfg)
    cfg["_data_dir"] = str(data_dir)
    all_trades, all_rejected, summaries = [], [], []
    periods = [
        ("development", development_start, cutoff),
        ("out_of_sample", cutoff, calendar[-1] + pd.Timedelta(days=1)),
    ]
    for period, start, end in periods:
        for horizon in horizons:
            trades, rejected, summary = _run_portfolio(
                candidates, calendar, period, start, end, int(horizon),
                cfg, cost_model, slippage_bps
            )
            all_trades.append(trades)
            all_rejected.append(rejected)
            summaries.append(summary)
    return (
        pd.concat(all_trades, ignore_index=True) if all_trades else pd.DataFrame(),
        pd.concat(all_rejected, ignore_index=True) if all_rejected else pd.DataFrame(),
        pd.DataFrame(summaries), coverage, cutoff,
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default="config.yaml")
    parser.add_argument("--data-dir", default="backtest_data")
    parser.add_argument("--cost-model", default="religare_basic_estimate")
    parser.add_argument("--cost-model-file", default="config/cost_models.example.yaml")
    parser.add_argument("--slippage-bps", type=float, default=5.0)
    parser.add_argument("--horizons", default="5,10,15")
    parser.add_argument("--trades-output", default="momentum_portfolio_trades.csv")
    parser.add_argument("--rejections-output", default="momentum_portfolio_rejections.csv")
    parser.add_argument("--summary-output", default="momentum_portfolio_summary.csv")
    parser.add_argument("--coverage-output", default="momentum_data_coverage.csv")
    parser.add_argument("--report", default="momentum_portfolio_report.md")
    args = parser.parse_args()
    with Path(args.config).open(encoding="utf-8") as handle:
        cfg = yaml.safe_load(handle)
    symbols = cfg["watchlist"]
    cost_model = load_cost_model(args.cost_model_file, args.cost_model)
    horizons = tuple(int(x) for x in args.horizons.split(",") if x.strip())
    trades, rejected, summary, coverage, cutoff = run_research(
        args.data_dir, symbols, cfg, cost_model, args.slippage_bps, horizons
    )
    trades.to_csv(args.trades_output, index=False)
    rejected.to_csv(args.rejections_output, index=False)
    summary.to_csv(args.summary_output, index=False)
    coverage.to_csv(args.coverage_output, index=False)
    report = [
        "# NSE Relative and Absolute Momentum Portfolio Research", "",
        "Research-only; no orders are placed and the baseline scanner is unchanged.", "",
        "- Universe: configured 100-symbol watchlist; current constituents applied historically create survivorship bias.",
        "- Signal: positive 63- and 126-session returns, both outperforming NIFTY 50, with Close > SMA50 > SMA200.",
        "- Ranking: equal-weight average of 63- and 126-session excess returns; strongest candidates considered first.",
        "- Entry: next NIFTY session open after signal close; the current calendar day's possibly incomplete candle is excluded.",
        "- Exit: 2.5 x signal-date ATR protective stop or fixed 5/10/15-session time exit, whichever occurs first.",
        "- Sizing: fixed starting-capital risk budget and position cap from config; shared cash and maximum concurrent positions enforced.",
        f"- Costs: {args.cost_model}; adverse slippage {args.slippage_bps:g} bps per side.",
        f"- Development/OOS boundary: {cutoff.date()}; OOS is a single chronological holdout, not repeated tuning material.",
        "- Daily mark-to-market drawdown uses closing prices; OHLC data cannot establish intraday ordering beyond conservative stop handling.",
        "- Cash from exits is released on the following session. No dividends, market impact, partial fills, or changing historical constituents are modeled.",
        "- Results are sensitive to data quality and estimated charges; verify broker contract notes before any future paper test.",
        "", "## Portfolio results", "", summary.to_string(index=False), "",
        "## Data coverage", "", coverage.to_string(index=False), "",
    ]
    Path(args.report).write_text("\\n".join(report), encoding="utf-8")
    print("Momentum portfolio summary:")
    print(summary.to_string(index=False))
    print("\\nSaved trades, rejections, summary, coverage and report.")
    print("Research only; no live-trading recommendation.")


if __name__ == "__main__":
    main()
