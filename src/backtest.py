"""Conservative daily-bar backtester with a chronological 3y/2y walk-forward report."""
import argparse
from pathlib import Path
import sys

import numpy as np
import pandas as pd
import yaml
import yfinance as yf

try:
    from .indicators import add_indicators
    from .risk import build_trade_plan
    from .scan import yahoo_symbol
except ImportError:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from src.indicators import add_indicators
    from src.risk import build_trade_plan
    from src.scan import yahoo_symbol


FILTER_NAMES = ("trend", "momentum", "volume", "breakout", "price", "turnover", "volatility")


def classify_exit(op: float, hi: float, lo: float, stop: float, target: float):
    """Return conservative daily-bar exit price/reason, including overnight gaps."""
    if op <= stop:
        return op, "stop_gap"
    if op >= target:
        return op, "target_gap"
    if lo <= stop and hi >= target:
        return stop, "both_hit_stop_assumed"
    if lo <= stop:
        return stop, "stop"
    if hi >= target:
        return target, "target"
    return None, None


def _filter_checks(row, st):
    return {
        "trend": bool(row["Close"] > row["ema_fast"] > row["ema_slow"]),
        "momentum": bool(50 <= row["rsi"] <= 70),
        "volume": bool(pd.notna(row["relative_volume"]) and row["relative_volume"] >= st["min_relative_volume"]),
        "breakout": bool(pd.notna(row["prior_high"]) and row["Close"] > row["prior_high"]),
        "price": bool(row["Close"] >= st["min_price_inr"]),
        "turnover": bool(pd.notna(row["avg_turnover"]) and row["avg_turnover"] >= st["min_avg_daily_turnover_inr"]),
        "volatility": bool(pd.notna(row["atr_pct"]) and row["atr_pct"] <= st["max_atr_pct"]),
    }


def count_filter_passes(frame: pd.DataFrame, cfg: dict) -> dict:
    """Count each filter pass/fail and fully-qualified signals after EMA warm-up."""
    st = cfg["strategy"]
    warmup = max(100, st["ema_slow"] * 2, st["breakout_lookback"] + st["volume_lookback"])
    counts = {f"{name}_{side}": 0 for name in FILTER_NAMES for side in ("pass", "fail")}
    counts["bars_evaluated"] = 0
    counts["raw_signals"] = 0
    for _, row in frame.iloc[warmup:-1].iterrows():
        if not all(pd.notna(row.get(k)) for k in ("Close", "ema_fast", "ema_slow", "rsi", "atr_pct")):
            continue
        checks = _filter_checks(row, st)
        counts["bars_evaluated"] += 1
        for name, passed in checks.items():
            counts[f"{name}_{'pass' if passed else 'fail'}"] += 1
        if all(checks.values()):
            counts["raw_signals"] += 1
    return counts


def simulate_symbol(frame: pd.DataFrame, symbol: str, cfg: dict,
                    cost_bps: float = 20.0, slippage_bps: float = 5.0,
                    max_gap_pct: float = 2.5) -> tuple[list[dict], dict]:
    """Run fixed rules on supplied OHLCV data; useful for deterministic tests."""
    market, account, st = cfg["market"], cfg["account"], cfg["strategy"]
    df = frame.copy()
    if not {"ema_fast", "ema_slow", "rsi", "relative_volume", "prior_high",
            "avg_turnover", "atr", "atr_pct"}.issubset(df.columns):
        df = add_indicators(df, st["ema_fast"], st["ema_slow"], st["rsi_period"],
                            st["atr_period"], st["volume_lookback"], st["breakout_lookback"])
    capital = float(account["capital_inr"])
    trades, diagnostics = [], {"raw_signals": 0, "gap_rejections": 0,
                               "risk_rejections": 0, "truncated_positions": 0}
    warmup = max(100, st["ema_slow"] * 2, st["breakout_lookback"] + st["volume_lookback"])
    i = warmup
    while i < len(df) - 1:
        row = df.iloc[i]
        if not all(pd.notna(row.get(k)) for k in ("Close", "ema_fast", "ema_slow", "rsi", "atr",
                                                   "relative_volume", "prior_high", "avg_turnover", "atr_pct")):
            i += 1
            continue
        if not all(_filter_checks(row, st).values()):
            i += 1
            continue
        diagnostics["raw_signals"] += 1
        entry_idx = i + 1
        entry_bar = df.iloc[entry_idx]
        signal_close, entry = float(row["Close"]), float(entry_bar["Open"])
        gap_pct = (entry / signal_close - 1) * 100 if signal_close else float("inf")
        if entry <= 0 or abs(gap_pct) > max_gap_pct:
            diagnostics["gap_rejections"] += 1
            i += 1
            continue
        stop = signal_close - 1.5 * float(row["atr"])
        if stop <= 0 or stop >= entry:
            diagnostics["risk_rejections"] += 1
            i += 1
            continue
        try:
            plan = build_trade_plan(entry, stop, capital, account["risk_per_trade_pct"],
                                    account["max_position_pct"], st["min_reward_risk"])
        except ValueError:
            diagnostics["risk_rejections"] += 1
            i += 1
            continue
        qty, target = plan.quantity, plan.target
        max_hold = int(st["holding_days_max"])  # entry session is session 1
        last_j = min(entry_idx + max_hold - 1, len(df) - 1)
        intended_last_j = entry_idx + max_hold - 1
        exit_price = exit_reason = None
        exit_idx = None
        for j in range(entry_idx, last_j + 1):
            bar = df.iloc[j]
            op, hi, lo, cl = map(float, (bar["Open"], bar["High"], bar["Low"], bar["Close"]))
            exit_price, exit_reason = classify_exit(op, hi, lo, stop, target)
            if exit_price is None and j == last_j and intended_last_j < len(df):
                exit_price, exit_reason = cl, "time_exit"
            if exit_price is not None:
                exit_idx = j
                break
        if exit_price is None:
            diagnostics["truncated_positions"] += 1
            break
        entry_slip, exit_slip = entry * slippage_bps / 10000, exit_price * slippage_bps / 10000
        effective_entry, effective_exit = entry + entry_slip, exit_price - exit_slip
        gross = (effective_exit - effective_entry) * qty
        costs = (entry * qty + exit_price * qty) * cost_bps / 10000
        net = gross - costs
        hold_sessions = exit_idx - entry_idx + 1
        initial_stop_distance = entry - stop
        signal_atr = float(row["atr"])
        trades.append({
            "symbol": symbol, "signal_date": str(df.index[i].date()),
            "entry_date": str(df.index[entry_idx].date()), "exit_date": str(df.index[exit_idx].date()),
            "signal_close": round(signal_close, 2), "signal_atr": round(signal_atr, 4),
            "entry_gap_pct": round(gap_pct, 4),
            "entry_stop_distance_inr": round(initial_stop_distance, 4),
            "entry_stop_distance_pct": round(initial_stop_distance / entry * 100, 4),
            "stop_distance_vs_signal_atr": round(initial_stop_distance / signal_atr, 4) if signal_atr else None,
            "entry": round(entry, 2), "stop": round(stop, 2), "target": round(target, 2),
            "exit": round(exit_price, 2), "quantity": qty, "holding_sessions": hold_sessions,
            "exit_reason": exit_reason, "gross_pnl_inr": round(gross, 2),
            "estimated_costs_inr": round(costs, 2), "net_pnl_inr": round(net, 2),
            "planned_risk_inr": round(plan.planned_risk_inr, 2),
            "net_r_multiple": round(net / plan.planned_risk_inr, 3) if plan.planned_risk_inr else None,
        })
        capital += net
        i = exit_idx + 1
    return trades, diagnostics


def performance_summary(trades: pd.DataFrame, initial_capital: float, total_sessions: int) -> dict:
    if trades.empty:
        return {"trades": 0, "average_r": 0.0, "max_drawdown_pct": 0.0,
                "average_holding_sessions": 0.0, "exposure_pct": 0.0}
    pnl = trades["net_pnl_inr"].astype(float)
    equity = initial_capital + pnl.cumsum()
    peak = equity.cummax().clip(lower=initial_capital)
    drawdown = (equity / peak - 1.0) * 100
    held = trades["holding_sessions"].astype(float).sum()
    return {
        "trades": len(trades),
        "average_r": round(float(trades["net_r_multiple"].dropna().mean()), 3),
        "max_drawdown_pct": round(float(drawdown.min()), 2),
        "average_holding_sessions": round(float(trades["holding_sessions"].mean()), 2),
        "exposure_pct": round(100.0 * held / max(total_sessions, 1), 2),
    }


def nifty_buy_hold_return(start_date, end_date):
    """NIFTY 50 price-index return over the requested dates; dividends excluded."""
    try:
        idx = yf.download("^NSEI", start=start_date, end=end_date + pd.Timedelta(days=1),
                          interval="1d", auto_adjust=False, progress=False, threads=False)
        if idx.empty:
            return None
        if isinstance(idx.columns, pd.MultiIndex):
            idx.columns = idx.columns.get_level_values(0)
        close = idx["Close"].dropna()
        if len(close) < 2:
            return None
        return round(float((close.iloc[-1] / close.iloc[0] - 1) * 100), 2)
    except Exception:
        return None


def _print_period_report(label, trades, signals, diagnostics, capital, sessions):
    frame = pd.DataFrame(trades)
    metrics = performance_summary(frame, capital, sessions)
    print(f"\n{label}: bars={signals['bars_evaluated']} raw_signals={signals['raw_signals']} "
          f"completed_trades={len(frame)} gap_rejected={diagnostics['gap_rejections']} "
          f"risk_rejected={diagnostics['risk_rejections']} truncated={diagnostics['truncated_positions']}")
    print("Filter pass/fail counts: " + " | ".join(
        f"{name} {signals[name+'_pass']}/{signals[name+'_fail']}" for name in FILTER_NAMES))
    if not frame.empty:
        winners = frame[frame.net_pnl_inr > 0]
        gross_profit = winners.net_pnl_inr.sum()
        gross_loss = -frame.loc[frame.net_pnl_inr < 0, "net_pnl_inr"].sum()
        print(f"Net P&L ₹{frame.net_pnl_inr.sum():,.2f} | Win rate {len(winners)/len(frame):.1%} | "
              f"Profit factor {gross_profit/gross_loss if gross_loss else float('inf'):.2f}")
    print(f"Average R {metrics['average_r']:.3f} | trade-close drawdown {metrics['max_drawdown_pct']:.2f}% | "
          f"avg hold {metrics['average_holding_sessions']:.2f} sessions | "
          f"rough independent-symbol exposure {metrics['exposure_pct']:.2f}%")
    return frame


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default="config.yaml")
    parser.add_argument("--output", default="backtest_trades.csv")
    parser.add_argument("--cost-bps", type=float, default=None)
    parser.add_argument("--slippage-bps", type=float, default=None)
    parser.add_argument("--max-gap-pct", type=float, default=None)
    args = parser.parse_args()
    with open(args.config, encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    bt, account = cfg.get("backtest", {}), cfg["account"]
    cost_bps = bt.get("cost_bps", 20.0) if args.cost_bps is None else args.cost_bps
    slippage_bps = bt.get("slippage_bps", 5.0) if args.slippage_bps is None else args.slippage_bps
    max_gap_pct = bt.get("max_gap_pct", 2.5) if args.max_gap_pct is None else args.max_gap_pct
    if min(cost_bps, slippage_bps, max_gap_pct) < 0:
        parser.error("cost, slippage and gap limits must be non-negative")

    downloaded = {}
    all_trades = {"development_3y": [], "out_of_sample_2y": []}
    aggregate = {p: {"signals": {f"{n}_{s}": 0 for n in FILTER_NAMES for s in ("pass", "fail")},
                     "signals_extra": {"bars_evaluated": 0, "raw_signals": 0},
                     "diag": {"gap_rejections": 0, "risk_rejections": 0, "truncated_positions": 0},
                     "sessions": 0} for p in all_trades}
    for symbol in cfg.get("watchlist", []):
        try:
            ticker = yahoo_symbol(symbol, cfg["market"].get("exchange", "NSE"))
            raw = yf.download(ticker, period=bt.get("history_period", "5y"), interval="1d",
                              auto_adjust=True, progress=False, threads=False)
            if raw.empty:
                print(f"{symbol}: no data")
                continue
            if isinstance(raw.columns, pd.MultiIndex):
                raw.columns = raw.columns.get_level_values(0)
            data = add_indicators(raw, cfg["strategy"]["ema_fast"], cfg["strategy"]["ema_slow"],
                                  cfg["strategy"]["rsi_period"], cfg["strategy"]["atr_period"],
                                  cfg["strategy"]["volume_lookback"], cfg["strategy"]["breakout_lookback"])
            downloaded[symbol] = data
        except Exception as exc:
            print(f"{symbol}: ERROR — {exc}")

    if not downloaded:
        print("No symbol data downloaded.")
        return
    earliest = min(df.index.min() for df in downloaded.values())
    latest = max(df.index.max() for df in downloaded.values())
    split_date = earliest + pd.DateOffset(years=3)
    print(f"Chronological split: development {earliest.date()} to {split_date.date()} (first 3 years); "
          f"out-of-sample {split_date.date()} to {latest.date()} (next 2 years).")
    print("Rules/parameters remain fixed in both periods; this is a chronological holdout, not parameter tuning.")
    print("Sector context is scanner ranking only, not a backtest entry filter.")

    for symbol, data in downloaded.items():
        for label, start, end in (("development_3y", earliest, split_date),
                                  ("out_of_sample_2y", split_date, latest + pd.Timedelta(days=1))):
            segment = data.loc[(data.index >= start) & (data.index < end)]
            if segment.empty:
                continue
            trades, diag = simulate_symbol(segment, yahoo_symbol(symbol, cfg["market"].get("exchange", "NSE")),
                                           cfg, cost_bps, slippage_bps, max_gap_pct)
            counts = count_filter_passes(segment, cfg)
            all_trades[label].extend([{**t, "period": label} for t in trades])
            for k in aggregate[label]["signals"]:
                aggregate[label]["signals"][k] += counts[k]
            for k in aggregate[label]["signals_extra"]:
                aggregate[label]["signals_extra"][k] += counts[k]
            for k in aggregate[label]["diag"]:
                aggregate[label]["diag"][k] += diag[k]
            aggregate[label]["sessions"] = max(aggregate[label]["sessions"], len(segment))

    frames = []
    for label in ("development_3y", "out_of_sample_2y"):
        a = aggregate[label]
        counts = {**a["signals"], **a["signals_extra"]}
        frame = _print_period_report(label, all_trades[label], counts, a["diag"],
                                     float(account["capital_inr"]), a["sessions"])
        if not frame.empty:
            frames.append(frame)
    if frames:
        result = pd.concat(frames, ignore_index=True)
        result.to_csv(args.output, index=False)
        print(f"\nSaved all completed trades to {args.output}")
    else:
        print("\nNo completed trades in either period; inspect raw signal and filter counts above.")

    benchmark = nifty_buy_hold_return(split_date, latest)
    if benchmark is None:
        print("NIFTY 50 benchmark: unavailable (index data could not be retrieved).")
    else:
        print(f"NIFTY 50 buy-and-hold price return over out-of-sample dates: {benchmark:.2f}% "
              "(dividends excluded; compare as a market reference, not a portfolio-equivalent return).")
    print("\nLimitations: independent single-symbol simulations, not a portfolio; trade-close drawdown, "
          "rough aggregate exposure, current-watchlist survivorship bias, and simplified costs. "
          "No live execution or investment advice.")


if __name__ == "__main__":
    main()
