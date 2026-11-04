"""Research-only close-based profit-protection experiment.

Baseline entries, initial stops, 2R targets, sizing, costs and 10-session
maximum holding period are copied from the baseline backtest. The candidate
adds one rule: after a daily close reaches +1R, if a later close falls below
+0.5R, exit at the following session's open. No production rules are changed.
"""
import argparse
from pathlib import Path
import sys

import pandas as pd
import yaml

try:
    from .backtest import (load_or_download_history, _filter_checks, classify_exit,
                           performance_summary)
    from .indicators import add_indicators
    from .risk import build_trade_plan
    from .scan import yahoo_symbol
except ImportError:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from src.backtest import (load_or_download_history, _filter_checks, classify_exit,
                              performance_summary)
    from src.indicators import add_indicators
    from src.risk import build_trade_plan
    from src.scan import yahoo_symbol


def protection_state(close_r: float, armed: bool) -> tuple[bool, bool]:
    """Return (armed_after_close, trigger_next_open) for the proposed rule."""
    armed_now = armed or close_r >= 1.0
    return armed_now, bool(armed and close_r < 0.5)


def simulate_symbol_protected(frame, symbol, cfg, cost_bps=20.0,
                              slippage_bps=5.0, max_gap_pct=2.5):
    """Simulate baseline rules plus close-confirmed +1R/+0.5R protection."""
    market, account, st = cfg["market"], cfg["account"], cfg["strategy"]
    df = frame.copy()
    if not {"ema_fast", "ema_slow", "rsi", "relative_volume", "prior_high",
            "avg_turnover", "atr", "atr_pct"}.issubset(df.columns):
        df = add_indicators(df, st["ema_fast"], st["ema_slow"], st["rsi_period"],
                            st["atr_period"], st["volume_lookback"], st["breakout_lookback"])
    capital = float(account["capital_inr"])
    trades, diag = [], {"raw_signals": 0, "gap_rejections": 0,
                        "risk_rejections": 0, "truncated_positions": 0}
    warmup = max(100, st["ema_slow"] * 2, st["breakout_lookback"] + st["volume_lookback"])
    i = warmup
    while i < len(df) - 1:
        row = df.iloc[i]
        required = ("Close", "ema_fast", "ema_slow", "rsi", "atr",
                    "relative_volume", "prior_high", "avg_turnover", "atr_pct")
        if not all(pd.notna(row.get(k)) for k in required) or not all(_filter_checks(row, st).values()):
            i += 1
            continue
        diag["raw_signals"] += 1
        entry_idx = i + 1
        entry_bar = df.iloc[entry_idx]
        signal_close, entry = float(row["Close"]), float(entry_bar["Open"])
        gap_pct = (entry / signal_close - 1) * 100 if signal_close else float("inf")
        if entry <= 0 or abs(gap_pct) > max_gap_pct:
            diag["gap_rejections"] += 1
            i += 1
            continue
        stop = signal_close - 1.5 * float(row["atr"])
        if stop <= 0 or stop >= entry:
            diag["risk_rejections"] += 1
            i += 1
            continue
        try:
            plan = build_trade_plan(entry, stop, capital, account["risk_per_trade_pct"],
                                    account["max_position_pct"], st["min_reward_risk"])
        except ValueError:
            diag["risk_rejections"] += 1
            i += 1
            continue
        qty, target = plan.quantity, plan.target
        max_hold = int(st["holding_days_max"])
        last_j = min(entry_idx + max_hold - 1, len(df) - 1)
        intended_last_j = entry_idx + max_hold - 1
        risk_per_share = entry - stop
        armed = False
        pending_protection = False
        exit_price = exit_reason = None
        exit_idx = None
        for j in range(entry_idx, last_j + 1):
            bar = df.iloc[j]
            op, hi, lo, cl = map(float, (bar["Open"], bar["High"], bar["Low"], bar["Close"]))
            # A prior session's confirmed close signal exits at this session's open.
            if pending_protection:
                exit_price, exit_reason, exit_idx = op, "profit_protection_open", j
                break
            exit_price, exit_reason = classify_exit(op, hi, lo, stop, target)
            if exit_price is not None:
                exit_idx = j
                break
            close_r = (cl - entry) / risk_per_share
            was_armed = armed
            armed, trigger = protection_state(close_r, armed)
            if trigger and was_armed:
                pending_protection = True
                # Need a following session to execute the close-confirmed instruction.
                if j + 1 <= last_j:
                    continue
                # No following open inside the allowed holding window: retain baseline time exit.
                pending_protection = False
            if exit_price is None and j == last_j and intended_last_j < len(df):
                exit_price, exit_reason, exit_idx = cl, "time_exit", j
                break
        if exit_price is None:
            diag["truncated_positions"] += 1
            break
        entry_slip = entry * slippage_bps / 10000
        exit_slip = exit_price * slippage_bps / 10000
        gross = ((exit_price - exit_slip) - (entry + entry_slip)) * qty
        costs = (entry * qty + exit_price * qty) * cost_bps / 10000
        net = gross - costs
        trades.append({
            "symbol": symbol, "signal_date": str(df.index[i].date()),
            "entry_date": str(df.index[entry_idx].date()),
            "exit_date": str(df.index[exit_idx].date()),
            "entry": round(entry, 2), "stop": round(stop, 2), "target": round(target, 2),
            "exit": round(exit_price, 2), "quantity": qty,
            "holding_sessions": exit_idx - entry_idx + 1, "exit_reason": exit_reason,
            "gross_pnl_inr": round(gross, 2), "estimated_costs_inr": round(costs, 2),
            "net_pnl_inr": round(net, 2), "planned_risk_inr": round(plan.planned_risk_inr, 2),
            "net_r_multiple": round(net / plan.planned_risk_inr, 3) if plan.planned_risk_inr else None,
        })
        capital += net
        i = exit_idx + 1
    return trades, diag


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default="config.yaml")
    parser.add_argument("--data-dir", default="backtest_data")
    parser.add_argument("--cost-bps", type=float, default=None)
    parser.add_argument("--slippage-bps", type=float, default=None)
    parser.add_argument("--max-gap-pct", type=float, default=None)
    args = parser.parse_args()
    with open(args.config, encoding="utf-8") as handle:
        cfg = yaml.safe_load(handle)
    bt, account = cfg.get("backtest", {}), cfg["account"]
    cost = bt.get("cost_bps", 20.0) if args.cost_bps is None else args.cost_bps
    slip = bt.get("slippage_bps", 5.0) if args.slippage_bps is None else args.slippage_bps
    gap = bt.get("max_gap_pct", 2.5) if args.max_gap_pct is None else args.max_gap_pct
    if min(cost, slip, gap) < 0:
        parser.error("cost, slippage and gap limits must be non-negative")

    histories = {}
    for symbol in cfg.get("watchlist", []):
        ticker = yahoo_symbol(symbol, cfg["market"].get("exchange", "NSE"))
        raw, _ = load_or_download_history(ticker, args.data_dir, bt.get("history_period", "5y"))
        if raw.empty:
            print(f"{symbol}: no cached/downloaded data; skipped")
            continue
        if isinstance(raw.columns, pd.MultiIndex):
            raw.columns = raw.columns.get_level_values(0)
        histories[symbol] = add_indicators(raw, cfg["strategy"]["ema_fast"],
            cfg["strategy"]["ema_slow"], cfg["strategy"]["rsi_period"],
            cfg["strategy"]["atr_period"], cfg["strategy"]["volume_lookback"],
            cfg["strategy"]["breakout_lookback"])
    if not histories:
        raise SystemExit("No history available. Run the baseline backtest first to populate the cache.")
    earliest = min(x.index.min() for x in histories.values())
    latest = max(x.index.max() for x in histories.values())
    split = earliest + pd.DateOffset(years=3)
    periods = (("development_3y", earliest, split),
               ("out_of_sample_2y", split, latest + pd.Timedelta(days=1)))
    all_rows = []
    for symbol, data in histories.items():
        for period, start, end in periods:
            segment = data.loc[(data.index >= start) & (data.index < end)]
            if segment.empty:
                continue
            rows, _ = simulate_symbol_protected(segment,
                yahoo_symbol(symbol, cfg["market"].get("exchange", "NSE")),
                cfg, cost, slip, gap)
            all_rows.extend([{**r, "period": period} for r in rows])
    result = pd.DataFrame(all_rows)
    if result.empty:
        raise SystemExit("No completed candidate trades.")
    result.to_csv("profit_protection_candidate_trades.csv", index=False)
    report = ["# Close-Based Profit-Protection Experiment", "",
        "Research-only candidate: after a daily close reaches +1R, a later close below +0.5R triggers an exit at the next session open.",
        "Entries, initial stops, 2R targets, sizing, costs, gap filter and maximum holding period are unchanged.",
        "This is a separate simulation; the baseline backtest and production rules are untouched.", ""]
    rows = []
    for period, group in result.groupby("period", sort=False):
        pnl = group["net_pnl_inr"].astype(float)
        winners = pnl[pnl > 0].sum()
        losers = -pnl[pnl < 0].sum()
        rows.append({"period": period, "trades": len(group),
            "win_rate_pct": round((pnl > 0).mean() * 100, 2),
            "net_pnl_inr": round(pnl.sum(), 2),
            "profit_factor": round(winners / losers, 3) if losers else float("inf"),
            "average_r": round(group["net_r_multiple"].mean(), 3),
            "protection_exits": int((group.exit_reason == "profit_protection_open").sum()),
            "time_exits": int((group.exit_reason == "time_exit").sum())})
    summary = pd.DataFrame(rows)
    report += ["## Candidate results", "", summary.to_string(index=False), "",
        "## Important interpretation limits", "",
        "- Compare these candidate results with the baseline run on the exact same cached snapshot.",
        "- Development results are exploratory, not proof of an edge.",
        "- Do not select the rule based on OOS performance; preserve that period as a holdout.",
        "- Next-open execution is simulated from daily OHLC data and does not include intraday path or market impact.",
        "- This experiment does not establish portfolio-level performance or justify real-money trading.", ""]
    Path("profit_protection_research_report.md").write_text("\n".join(report), encoding="utf-8")
    print("Candidate results:")
    print(summary.to_string(index=False))
    print("\nSaved profit_protection_candidate_trades.csv and profit_protection_research_report.md")
    print("Research-only: no baseline, scanner, configuration, or trading rules were modified.")


if __name__ == "__main__":
    main()
