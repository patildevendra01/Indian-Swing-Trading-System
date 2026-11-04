"""Conservative daily-bar backtester; no broker integration or live execution."""
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
    from .scan import yahoo_symbol, sector_for, load_sector_context, sector_rank_adjustment
except ImportError:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from src.indicators import add_indicators
    from src.risk import build_trade_plan
    from src.scan import yahoo_symbol, sector_for, load_sector_context, sector_rank_adjustment


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
        checks = (
            row["Close"] > row["ema_fast"] > row["ema_slow"],
            50 <= row["rsi"] <= 70,
            pd.notna(row["relative_volume"]) and row["relative_volume"] >= st["min_relative_volume"],
            pd.notna(row["prior_high"]) and row["Close"] > row["prior_high"],
            row["Close"] >= st["min_price_inr"],
            pd.notna(row["avg_turnover"]) and row["avg_turnover"] >= st["min_avg_daily_turnover_inr"],
            pd.notna(row["atr_pct"]) and row["atr_pct"] <= st["max_atr_pct"],
        )
        if not all(checks):
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
        # holding_days_max counts trading sessions from the entry session, inclusive.
        max_hold = int(st["holding_days_max"])
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
            # Data ended before the planned holding window: not a completed trade.
            diagnostics["truncated_positions"] += 1
            break
        entry_slip, exit_slip = entry * slippage_bps / 10000, exit_price * slippage_bps / 10000
        effective_entry, effective_exit = entry + entry_slip, exit_price - exit_slip
        gross = (effective_exit - effective_entry) * qty
        costs = (entry * qty + exit_price * qty) * cost_bps / 10000
        net = gross - costs
        hold_sessions = exit_idx - entry_idx + 1
        trades.append({
            "symbol": symbol, "signal_date": str(df.index[i].date()),
            "entry_date": str(df.index[entry_idx].date()), "exit_date": str(df.index[exit_idx].date()),
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


def backtest_symbol(symbol: str, cfg: dict, cost_bps: float = 20.0,
                    slippage_bps: float = 5.0, max_gap_pct: float = 2.5) -> list[dict]:
    market, st = cfg["market"], cfg["strategy"]
    ticker = yahoo_symbol(symbol, market.get("exchange", "NSE"))
    raw = yf.download(ticker, period=cfg.get("backtest", {}).get("history_period", "5y"),
                      interval="1d", auto_adjust=True, progress=False, threads=False)
    if raw.empty:
        return []
    if isinstance(raw.columns, pd.MultiIndex):
        raw.columns = raw.columns.get_level_values(0)
    data = add_indicators(raw, st["ema_fast"], st["ema_slow"], st["rsi_period"],
                          st["atr_period"], st["volume_lookback"], st["breakout_lookback"])
    trades, _ = simulate_symbol(data, ticker, cfg, cost_bps, slippage_bps, max_gap_pct)
    return trades


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
    all_trades, raw_signals, gap_rejections, risk_rejections, truncated = [], 0, 0, 0, 0
    total_sessions = 0
    sector_context = load_sector_context(bt.get("market_context_file", "market_context.csv"))
    print("Sector context is used for scanner ranking only, not as a backtest entry filter; "
          "ranking does not change per-symbol signal qualification.")
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
            trades, diag = simulate_symbol(data, ticker, cfg, cost_bps, slippage_bps, max_gap_pct)
            all_trades.extend(trades)
            raw_signals += diag["raw_signals"]
            gap_rejections += diag["gap_rejections"]
            risk_rejections += diag["risk_rejections"]
            truncated += diag["truncated_positions"]
            total_sessions = max(total_sessions, len(data))
            print(f"{symbol}: signals={diag['raw_signals']} completed={len(trades)} "
                  f"gap_rejected={diag['gap_rejections']} risk_rejected={diag['risk_rejections']} "
                  f"truncated={diag['truncated_positions']}")
        except Exception as exc:
            print(f"{symbol}: ERROR — {exc}")
    print(f"\nRaw signals: {raw_signals} | gap rejections: {gap_rejections} | "
          f"risk rejections: {risk_rejections} | truncated positions: {truncated}")
    if not all_trades:
        print("No completed trades. This is not evidence that the strategy works or fails.")
        return
    result = pd.DataFrame(all_trades)
    result.to_csv(args.output, index=False)
    winners = result[result.net_pnl_inr > 0]
    gross_profit = winners.net_pnl_inr.sum()
    gross_loss = -result.loc[result.net_pnl_inr < 0, "net_pnl_inr"].sum()
    metrics = performance_summary(result, float(account["capital_inr"]), total_sessions)
    print(f"Trades: {len(result)} | Win rate: {len(winners)/len(result):.1%}")
    print(f"Net P&L: ₹{result.net_pnl_inr.sum():,.2f} | Profit factor: "
          f"{gross_profit/gross_loss if gross_loss else float('inf'):.2f}")
    print(f"Average R: {metrics['average_r']:.3f} | Max drawdown: {metrics['max_drawdown_pct']:.2f}%")
    print(f"Average holding: {metrics['average_holding_sessions']:.2f} sessions | "
          f"Exposure (per-symbol, not portfolio): {metrics['exposure_pct']:.2f}%")
    print(f"Saved detailed trades to {args.output}")
    print("This remains a collection of independent single-symbol simulations, not a portfolio backtest.")
    print("NIFTY benchmark and walk-forward testing are not yet implemented; do not infer out-of-sample performance.")


if __name__ == "__main__":
    main()
