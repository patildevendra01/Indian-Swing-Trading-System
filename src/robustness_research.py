"""Robustness diagnostics: cost sensitivity and reconstructed portfolio constraints.

The portfolio is an approximation from completed independent-symbol trades, not a
full daily-bar portfolio re-simulation. It cannot recover rejected signals or the
exact order of simultaneous candidate signals.
"""
import argparse
from pathlib import Path

import pandas as pd

REQUIRED = {
    "symbol", "entry_date", "exit_date", "entry", "stop", "exit", "quantity",
    "gross_pnl_inr", "estimated_costs_inr", "net_pnl_inr", "period",
}


def load_trade_export(path):
    frame = pd.read_csv(path)
    missing = REQUIRED.difference(frame.columns)
    if missing:
        raise ValueError(f"Trade file missing required columns: {sorted(missing)}")
    for col in ("entry", "stop", "exit", "quantity", "gross_pnl_inr",
                "estimated_costs_inr", "net_pnl_inr"):
        frame[col] = pd.to_numeric(frame[col], errors="coerce")
    frame["entry_date"] = pd.to_datetime(frame["entry_date"], errors="coerce")
    frame["exit_date"] = pd.to_datetime(frame["exit_date"], errors="coerce")
    frame = frame.dropna(subset=["symbol", "period", "entry_date", "exit_date",
                                 "entry", "stop", "exit", "quantity"])
    if frame.empty:
        raise ValueError("No valid trades in export")
    if (frame["quantity"] <= 0).any() or (frame["entry"] <= 0).any():
        raise ValueError("Trade export contains non-positive quantity or entry")
    return frame.sort_values(["period", "entry_date", "symbol"]).reset_index(drop=True)


def profit_factor(pnl):
    pnl = pd.Series(pnl, dtype=float)
    gains = pnl[pnl > 0].sum()
    losses = -pnl[pnl < 0].sum()
    return round(float(gains / losses), 3) if losses > 0 else None


def cost_sensitivity(frame, scenarios):
    rows = []
    raw_move = (frame["exit"] - frame["entry"]) * frame["quantity"]
    turnover = (frame["entry"] + frame["exit"]) * frame["quantity"]
    for period, group in frame.groupby("period"):
        idx = group.index
        for cost_bps, slippage_bps in scenarios:
            pnl = (raw_move.loc[idx]
                   - turnover.loc[idx] * (cost_bps + 2 * slippage_bps) / 10000)
            rows.append({
                "period": period, "cost_bps_per_side": cost_bps,
                "slippage_bps_per_side": slippage_bps, "trades": len(group),
                "net_pnl_inr": round(float(pnl.sum()), 2),
                "win_rate_pct": round(float((pnl > 0).mean() * 100), 2),
                "profit_factor": profit_factor(pnl),
                "average_trade_pnl_inr": round(float(pnl.mean()), 2),
            })
    return pd.DataFrame(rows)


def reconstruct_portfolio(frame, initial_capital=15000.0, risk_pct=0.5,
                          max_position_pct=25.0, max_positions=3,
                          cost_bps=20.0, slippage_bps=5.0):
    """Greedy chronological reconstruction using only trades already present.

    Capital is period-local. Existing positions remain occupied through their
    exit date; same-day exit/entry overlap is conservatively treated as occupied.
    The model cannot include candidates absent from the independent trade export.
    """
    out = []
    for period, group in frame.groupby("period"):
        equity = float(initial_capital)
        active = []
        accepted_pnl = []
        rejected_slots = rejected_cash = rejected_risk = 0
        for row in group.sort_values(["entry_date", "symbol"]).itertuples():
            active = [p for p in active if p["exit_date"] >= row.entry_date]
            if len(active) >= int(max_positions):
                rejected_slots += 1
                continue
            locked_value = sum(p["position_value"] for p in active)
            cash_available = max(0.0, equity - locked_value)
            max_value = min(equity * max_position_pct / 100.0, cash_available)
            risk_budget = equity * risk_pct / 100.0
            per_share_risk = float(row.entry - row.stop)
            if per_share_risk <= 0:
                rejected_risk += 1
                continue
            qty_risk = int(risk_budget // per_share_risk)
            qty_cash = int(max_value // float(row.entry))
            qty = min(qty_risk, qty_cash)
            if qty < 1:
                if qty_cash < 1:
                    rejected_cash += 1
                else:
                    rejected_risk += 1
                continue
            turnover = (float(row.entry) + float(row.exit)) * qty
            raw_pnl = (float(row.exit) - float(row.entry)) * qty
            costs = turnover * cost_bps / 10000.0
            slippage = turnover * 2 * slippage_bps / 10000.0
            pnl = raw_pnl - costs - slippage
            position_value = float(row.entry) * qty
            active.append({"exit_date": row.exit_date, "position_value": position_value})
            accepted_pnl.append(pnl)
            equity += pnl
        series = pd.Series(accepted_pnl, dtype=float)
        out.append({
            "period": period, "starting_capital_inr": round(initial_capital, 2),
            "accepted_trades": len(series), "rejected_max_positions": rejected_slots,
            "rejected_cash_limit": rejected_cash, "rejected_risk_or_one_share": rejected_risk,
            "net_pnl_inr": round(float(series.sum()), 2),
            "ending_equity_inr": round(initial_capital + float(series.sum()), 2),
            "return_pct": round(float(series.sum()) / initial_capital * 100, 2),
            "win_rate_pct": round(float((series > 0).mean() * 100), 2) if len(series) else 0.0,
            "profit_factor": profit_factor(series),
            "max_concurrent_positions": int(max_positions),
        })
    return pd.DataFrame(out)


def build_report(costs, portfolio, initial_capital, risk_pct, max_position_pct, max_positions):
    lines = [
        "# Robustness Study: Costs and Reconstructed Portfolio",
        "",
        "Research-only. No scanner, signal, stop, target, or production settings were changed.",
        "",
        "## Transaction-cost sensitivity",
        "",
        costs.to_string(index=False),
        "",
        "Cost and slippage are applied per side to entry/exit turnover. These are scenarios,",
        "not claims about the exact fees charged by a particular broker or exchange.",
        "",
        "## Approximate constrained portfolio reconstruction",
        "",
        portfolio.to_string(index=False),
        "",
        f"Assumptions: starting capital ₹{initial_capital:,.0f} per period; risk budget {risk_pct:.2f}% of current equity per accepted trade; "
        f"maximum position value {max_position_pct:.1f}% of current equity; at most {max_positions} overlapping positions.",
        "",
        "## Critical limitations",
        "",
        "- Source trades were generated by independent per-symbol simulations, not a shared portfolio.",
        "- This reconstruction only considers completed trades already present in the export; rejected candidates and other simultaneous signals are absent.",
        "- It re-sizes the recorded entry/exit prices and dates; it does not replay daily OHLC bars, portfolio cash flows, or signal ranking.",
        "- Positions are considered occupied through their exit date, a conservative same-day overlap convention.",
        "- Results are diagnostic estimates, not a validated portfolio backtest or expected future return.",
        "- Yahoo Finance history, current-watchlist survivorship, simplified costs, and daily-bar execution limitations remain.",
        "",
        "Do not use this report to relax risk limits or initiate real-money trades. Paper-only remains in force.",
        "",
    ]
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", default="backtest_trades.csv")
    parser.add_argument("--capital", type=float, default=15000)
    parser.add_argument("--risk-pct", type=float, default=0.5)
    parser.add_argument("--max-position-pct", type=float, default=25.0)
    parser.add_argument("--max-positions", type=int, default=3)
    parser.add_argument("--cost-bps", type=float, default=20.0)
    parser.add_argument("--slippage-bps", type=float, default=5.0)
    parser.add_argument("--cost-output", default="robustness_cost_sensitivity.csv")
    parser.add_argument("--portfolio-output", default="robustness_portfolio_estimate.csv")
    parser.add_argument("--report", default="robustness_research_report.md")
    args = parser.parse_args()
    if min(args.capital, args.risk_pct, args.max_position_pct, args.max_positions) <= 0:
        parser.error("capital, risk, position cap, and max positions must be positive")
    frame = load_trade_export(args.input)
    scenarios = [(20, 5), (30, 10), (40, 15), (60, 20)]
    costs = cost_sensitivity(frame, scenarios)
    portfolio = reconstruct_portfolio(
        frame, args.capital, args.risk_pct, args.max_position_pct,
        args.max_positions, args.cost_bps, args.slippage_bps)
    costs.to_csv(args.cost_output, index=False)
    portfolio.to_csv(args.portfolio_output, index=False)
    Path(args.report).write_text(build_report(
        costs, portfolio, args.capital, args.risk_pct,
        args.max_position_pct, args.max_positions), encoding="utf-8")
    print("COST SENSITIVITY")
    print(costs.to_string(index=False))
    print("\nAPPROXIMATE PORTFOLIO RECONSTRUCTION")
    print(portfolio.to_string(index=False))
    print(f"\nSaved {args.cost_output}, {args.portfolio_output}, {args.report}")
    print("Research-only approximation; baseline scanner/backtest unchanged.")


if __name__ == "__main__":
    main()
