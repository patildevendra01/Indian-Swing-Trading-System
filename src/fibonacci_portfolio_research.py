"""Shared-capital portfolio replay for precomputed Fibonacci pullback trades.

Each (period, setup) is replayed as an independent portfolio using the
configured cash, open-position, risk and position-value limits. The underlying
daily-bar trade exits are inherited from fibonacci_pullback_backtest.py.
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


REQUIRED_COLUMNS = {
    "period", "setup", "symbol", "entry_date", "exit_date",
    "entry", "exit", "stop",
}


def _positive_float(value, name):
    result = float(value)
    if not np.isfinite(result) or result <= 0:
        raise ValueError(f"{name} must be a positive finite number")
    return result


def replay_portfolio(trades, cfg, cost_model, slippage_bps=5.0):
    """Replay each period/setup independently under shared cash constraints.

    A position remains reserved through its exit date; its cash is released on
    the following session. This avoids assuming that exit proceeds are
    available before that day's close. Simultaneous entries are considered in
    stable symbol order because this research file has no independent ranking.
    """
    missing = REQUIRED_COLUMNS.difference(trades.columns)
    if missing:
        raise ValueError(f"Trade input missing columns: {sorted(missing)}")
    if slippage_bps < 0 or not np.isfinite(slippage_bps):
        raise ValueError("slippage_bps must be finite and non-negative")

    account = cfg["account"]
    initial_capital = _positive_float(account["capital_inr"], "capital_inr")
    risk_pct = _positive_float(account["risk_per_trade_pct"], "risk_per_trade_pct")
    max_position_pct = _positive_float(account["max_position_pct"], "max_position_pct")
    max_positions = int(account["max_open_positions"])
    if max_positions < 1:
        raise ValueError("max_open_positions must be at least 1")
    risk_budget = initial_capital * risk_pct / 100.0
    max_position_value = initial_capital * max_position_pct / 100.0
    slip = slippage_bps / 10000.0

    accepted_rows, rejected_rows, summaries = [], [], []
    if trades.empty:
        return pd.DataFrame(), pd.DataFrame(), pd.DataFrame()

    work = trades.copy()
    work["entry_date"] = pd.to_datetime(work["entry_date"], errors="coerce")
    work["exit_date"] = pd.to_datetime(work["exit_date"], errors="coerce")
    for col in ("entry", "exit", "stop"):
        work[col] = pd.to_numeric(work[col], errors="coerce")
    work = work.dropna(subset=["entry_date", "exit_date", "entry", "exit", "stop"])
    work = work.sort_values(
        ["period", "setup", "entry_date", "symbol", "signal_date"]
        if "signal_date" in work.columns
        else ["period", "setup", "entry_date", "symbol"],
        kind="mergesort",
    )

    for (period, setup), group in work.groupby(["period", "setup"], sort=True):
        cash = initial_capital
        open_positions = []
        accepted = []
        rejected = []

        for _, candidate in group.iterrows():
            entry_date = candidate["entry_date"]
            # Release only positions whose exit date is strictly earlier.
            still_open = []
            for pos in open_positions:
                if pos["exit_date"] < entry_date:
                    cash += pos["entry_notional"] + pos["net_pnl_inr"]
                else:
                    still_open.append(pos)
            open_positions = still_open

            reason = None
            symbol = str(candidate["symbol"])
            if candidate["exit_date"] < entry_date:
                reason = "invalid_exit_before_entry"
            elif any(p["symbol"] == symbol for p in open_positions):
                reason = "symbol_already_open"
            elif len(open_positions) >= max_positions:
                reason = "max_concurrent_positions"
            else:
                raw_entry = float(candidate["entry"])
                raw_exit = float(candidate["exit"])
                stop = float(candidate["stop"])
                effective_entry = raw_entry * (1.0 + slip)
                effective_exit = raw_exit * (1.0 - slip)
                risk_per_share = effective_entry - stop
                if min(raw_entry, raw_exit, stop) <= 0 or risk_per_share <= 0:
                    reason = "invalid_entry_or_stop"
                else:
                    qty_risk = math.floor(risk_budget / risk_per_share)
                    qty_position = math.floor(max_position_value / effective_entry)
                    qty_cash = math.floor(cash / effective_entry)
                    quantity = min(qty_risk, qty_position, qty_cash)
                    if quantity < 1:
                        reason = "insufficient_cash_or_size_below_one"
                    else:
                        entry_notional = effective_entry * quantity
                        gross_pnl = (effective_exit - effective_entry) * quantity
                        charges = cost_model.calculate(raw_entry, raw_exit, quantity)
                        net_pnl = gross_pnl - float(charges["total_charges_inr"])
                        planned_risk = risk_per_share * quantity
                        row = candidate.to_dict()
                        row.update({
                            "portfolio_quantity": quantity,
                            "portfolio_entry_effective": round(effective_entry, 4),
                            "portfolio_exit_effective": round(effective_exit, 4),
                            "entry_notional_inr": round(entry_notional, 2),
                            "risk_budget_inr": round(risk_budget, 2),
                            "planned_risk_inr": round(planned_risk, 2),
                            "gross_pnl_inr": round(gross_pnl, 2),
                            "estimated_costs_inr": round(float(charges["total_charges_inr"]), 2),
                            "net_pnl_inr": round(net_pnl, 2),
                            "net_r_multiple": round(net_pnl / planned_risk, 4)
                                if planned_risk > 0 else None,
                            "cash_after_entry_inr": round(cash - entry_notional, 2),
                        })
                        accepted.append(row)
                        open_positions.append({
                            "symbol": symbol,
                            "exit_date": candidate["exit_date"],
                            "entry_notional": entry_notional,
                            "net_pnl_inr": net_pnl,
                        })
                        cash -= entry_notional
                        continue

            rejected.append({
                "period": period, "setup": setup, "symbol": symbol,
                "entry_date": entry_date.date().isoformat(),
                "reason": reason,
            })

        # All remaining positions are settled at their precomputed exit dates.
        for pos in open_positions:
            cash += pos["entry_notional"] + pos["net_pnl_inr"]

        accepted_rows.extend(accepted)
        rejected_rows.extend(rejected)

        if accepted:
            pf = pd.DataFrame(accepted)
            pnl = pd.to_numeric(pf["net_pnl_inr"], errors="coerce").fillna(0.0)
            gross_profit = float(pnl[pnl > 0].sum())
            gross_loss = float(-pnl[pnl < 0].sum())
            daily = pf.assign(_exit=pd.to_datetime(pf["exit_date"])) \
                .groupby("_exit")["net_pnl_inr"].sum().sort_index()
            equity = initial_capital + daily.cumsum()
            peaks = equity.cummax().clip(lower=initial_capital)
            drawdown = (equity / peaks - 1.0) * 100.0
            r_values = pd.to_numeric(pf["net_r_multiple"], errors="coerce").dropna()
            summaries.append({
                "period": period, "setup": setup,
                "candidate_trades": int(len(group)),
                "accepted_trades": int(len(pf)),
                "rejected_trades": int(len(rejected)),
                "ending_equity_inr": round(float(cash), 2),
                "net_pnl_inr": round(float(pnl.sum()), 2),
                "return_pct": round((float(cash) / initial_capital - 1.0) * 100.0, 2),
                "win_rate_pct": round(float((pnl > 0).mean() * 100.0), 2),
                "profit_factor": round(gross_profit / gross_loss, 3)
                    if gross_loss else (float("inf") if gross_profit else 0.0),
                "average_r": round(float(r_values.mean()), 3) if len(r_values) else None,
                "max_realized_drawdown_pct": round(float(drawdown.min()), 2),
                "max_concurrent_positions": max_positions if False else None,
                "starting_capital_inr": initial_capital,
                "risk_budget_per_entry_inr": round(risk_budget, 2),
                "max_position_value_inr": round(max_position_value, 2),
            })
        else:
            summaries.append({
                "period": period, "setup": setup,
                "candidate_trades": int(len(group)), "accepted_trades": 0,
                "rejected_trades": len(rejected), "ending_equity_inr": round(cash, 2),
                "net_pnl_inr": 0.0, "return_pct": 0.0, "win_rate_pct": None,
                "profit_factor": 0.0, "average_r": None,
                "max_realized_drawdown_pct": 0.0, "max_concurrent_positions": 0,
                "starting_capital_inr": initial_capital,
                "risk_budget_per_entry_inr": round(risk_budget, 2),
                "max_position_value_inr": round(max_position_value, 2),
            })

    return pd.DataFrame(accepted_rows), pd.DataFrame(rejected_rows), pd.DataFrame(summaries)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", default="fibonacci_pullback_trades.csv")
    parser.add_argument("--config", default="config.yaml")
    parser.add_argument("--cost-model", default="religare_basic_estimate")
    parser.add_argument("--cost-model-file", default="config/cost_models.example.yaml")
    parser.add_argument("--slippage-bps", type=float, default=5.0)
    parser.add_argument("--accepted-output", default="fibonacci_portfolio_trades.csv")
    parser.add_argument("--rejected-output", default="fibonacci_portfolio_rejections.csv")
    parser.add_argument("--summary-output", default="fibonacci_portfolio_summary.csv")
    parser.add_argument("--report", default="fibonacci_portfolio_report.md")
    args = parser.parse_args()

    with Path(args.config).open(encoding="utf-8") as handle:
        cfg = yaml.safe_load(handle)
    trades = pd.read_csv(args.input)
    cost_model = load_cost_model(args.cost_model_file, args.cost_model)
    accepted, rejected, summary = replay_portfolio(
        trades, cfg, cost_model, slippage_bps=args.slippage_bps
    )
    accepted.to_csv(args.accepted_output, index=False)
    rejected.to_csv(args.rejected_output, index=False)
    summary.to_csv(args.summary_output, index=False)

    report = [
        "# Fibonacci Shared-Capital Portfolio Replay", "",
        "Research only. This replays the independent-symbol trade outcomes under shared account constraints.",
        "",
        f"- Starting capital: ₹{cfg['account']['capital_inr']:,.0f}.",
        f"- Maximum concurrent positions: {cfg['account']['max_open_positions']}.",
        f"- Risk budget per entry: {cfg['account']['risk_per_trade_pct']}% of starting capital.",
        f"- Maximum position value: {cfg['account']['max_position_pct']}% of starting capital.",
        f"- Cost model: {args.cost_model}; adverse slippage: {args.slippage_bps:g} bps per side.",
        "- Positions remain cash-reserved through their exit date; proceeds are released on the following session.",
        "- Same-day simultaneous entries are considered in stable symbol order; no signal-strength ranking is assumed.",
        "- Each ratio and period is replayed as a separate portfolio, not combined with other ratios.",
        "- Quantity is recalculated from risk, position-value and available-cash limits; precomputed stop/target/exit dates are unchanged.",
        "- Drawdown is realized trade-close drawdown, not daily mark-to-market drawdown.",
        "- This replay does not model partial fills, taxes beyond the configured estimate, intraday cash timing, or changing watchlist membership.",
        "- The historical OOS period was already examined and is exploratory, not fresh validation.",
        "- No scanner, baseline strategy, account settings, or live trading behavior is changed.",
        "",
        "## Results", "",
        summary.to_string(index=False) if not summary.empty else "No candidate trades.",
        "",
        "## Interpretation", "",
        "This replay is a stricter capital-allocation check, not a new independent validation. A candidate still requires a future paper-trading window and robust data/cost verification.",
        "",
    ]
    Path(args.report).write_text("\n".join(report), encoding="utf-8")
    print(summary.to_string(index=False) if not summary.empty else "No candidate trades.")
    print(f"Saved {args.accepted_output}, {args.rejected_output}, {args.summary_output}, and {args.report}")


if __name__ == "__main__":
    main()
