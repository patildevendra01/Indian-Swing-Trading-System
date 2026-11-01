"""Conservative daily-bar backtester; no broker integration or live execution."""
import argparse
from pathlib import Path
import sys

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


def backtest_symbol(symbol: str, cfg: dict, cost_bps: float = 20.0,
                    slippage_bps: float = 5.0, max_gap_pct: float = 2.5) -> list[dict]:
    market, account, st = cfg["market"], cfg["account"], cfg["strategy"]
    ticker = yahoo_symbol(symbol, market.get("exchange", "NSE"))
    raw = yf.download(ticker, period=market.get("history_period", "5y"),
                      interval="1d", auto_adjust=True, progress=False, threads=False)
    if raw.empty:
        return []
    if isinstance(raw.columns, pd.MultiIndex):
        raw.columns = raw.columns.get_level_values(0)
    df = add_indicators(raw, st["ema_fast"], st["ema_slow"], st["rsi_period"],
                        st["atr_period"], st["volume_lookback"], st["breakout_lookback"])
    capital = float(account["capital_inr"])
    trades = []
    i = max(st["ema_slow"], st["breakout_lookback"], st["volume_lookback"]) + 2
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

        entry_bar = df.iloc[i + 1]
        signal_close = float(row["Close"])
        entry = float(entry_bar["Open"])
        gap_pct = (entry / signal_close - 1) * 100
        if entry <= 0 or gap_pct > max_gap_pct or gap_pct < -max_gap_pct:
            i += 1
            continue
        stop = signal_close - 1.5 * float(row["atr"])
        if stop <= 0 or stop >= entry:
            i += 1
            continue
        try:
            plan = build_trade_plan(entry, stop, capital, account["risk_per_trade_pct"],
                                    account["max_position_pct"], st["min_reward_risk"])
        except ValueError:
            i += 1
            continue
        qty = plan.quantity
        target = plan.target
        exit_price = None
        exit_date = None
        exit_reason = None
        last_j = min(i + st["holding_days_max"], len(df) - 1)
        for j in range(i + 1, last_j + 1):
            bar = df.iloc[j]
            op, hi, lo, cl = map(float, (bar["Open"], bar["High"], bar["Low"], bar["Close"]))
            # If both levels trade in one daily candle, assume stop first (conservative).
            if op <= stop:
                exit_price, exit_reason = op, "stop_gap"
            elif op >= target:
                exit_price, exit_reason = op, "target_gap"
            elif lo <= stop and hi >= target:
                exit_price, exit_reason = stop, "both_hit_stop_assumed"
            elif lo <= stop:
                exit_price, exit_reason = stop, "stop"
            elif hi >= target:
                exit_price, exit_reason = target, "target"
            elif j == last_j:
                exit_price, exit_reason = cl, "time_exit"
            if exit_price is not None:
                exit_date = str(df.index[j].date())
                break
        if exit_price is None:
            i += 1
            continue
        entry_slip = entry * slippage_bps / 10000
        exit_slip = exit_price * slippage_bps / 10000
        effective_entry = entry + entry_slip
        effective_exit = exit_price - exit_slip
        gross = (effective_exit - effective_entry) * qty
        costs = (entry * qty + exit_price * qty) * cost_bps / 10000
        net = gross - costs
        risk_budget = capital * float(account["risk_per_trade_pct"]) / 100
        trades.append({"symbol": ticker, "signal_date": str(df.index[i].date()),
                       "entry_date": str(df.index[i + 1].date()), "exit_date": exit_date,
                       "entry": round(entry, 2), "stop": round(stop, 2),
                       "target": round(target, 2), "exit": round(exit_price, 2),
                       "quantity": qty, "exit_reason": exit_reason,
                       "gross_pnl_inr": round(gross, 2), "estimated_costs_inr": round(costs, 2),
                       "net_pnl_inr": round(net, 2),
                       "planned_risk_inr": round(plan.planned_risk_inr, 2),
                       "net_r_multiple": round(net / risk_budget, 3) if risk_budget else None})
        capital += net
        i = j + 1  # one position per symbol; no overlapping trades
    return trades


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default="config.yaml")
    parser.add_argument("--output", default="backtest_trades.csv")
    parser.add_argument("--cost-bps", type=float, default=20.0,
                        help="Estimated total round-trip costs in basis points of traded value")
    parser.add_argument("--slippage-bps", type=float, default=5.0)
    parser.add_argument("--max-gap-pct", type=float, default=2.5)
    args = parser.parse_args()
    if min(args.cost_bps, args.slippage_bps, args.max_gap_pct) < 0:
        parser.error("cost, slippage and gap limits must be non-negative")
    with open(args.config, encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    all_trades = []
    for symbol in cfg.get("watchlist", []):
        try:
            trades = backtest_symbol(symbol, cfg, args.cost_bps, args.slippage_bps, args.max_gap_pct)
            all_trades.extend(trades)
            print(f"{symbol}: {len(trades)} completed simulated trades")
        except Exception as exc:
            print(f"{symbol}: ERROR — {exc}")
    if not all_trades:
        print("No completed trades. This is not evidence that the strategy works or fails.")
        return
    result = pd.DataFrame(all_trades)
    result.to_csv(args.output, index=False)
    winners = result[result.net_pnl_inr > 0]
    gross_profit = winners.net_pnl_inr.sum()
    gross_loss = -result.loc[result.net_pnl_inr < 0, "net_pnl_inr"].sum()
    print(f"\\nTrades: {len(result)} | Win rate: {len(winners)/len(result):.1%}")
    print(f"Net P&L: ₹{result.net_pnl_inr.sum():,.2f} | Profit factor: {gross_profit/gross_loss if gross_loss else float('inf'):.2f}")
    print(f"Saved detailed trades to {args.output}")
    print("Single-symbol-at-a-time results are not a portfolio backtest; validate out-of-sample.")


if __name__ == "__main__":
    main()
