"""Second-stage loss diagnostics for completed swing-backtest trades.

This is descriptive research only. It does not tune rules or create signals.
Run: python -m src.improvement_research --input backtest_trades.csv
"""
import argparse
from pathlib import Path
import pandas as pd

REQUIRED = {"symbol", "entry_date", "exit_date", "holding_sessions",
            "exit_reason", "net_pnl_inr", "net_r_multiple", "period"}

def load(path):
    df = pd.read_csv(path)
    missing = REQUIRED - set(df.columns)
    if missing:
        raise ValueError(f"Missing columns: {sorted(missing)}")
    for c in ("holding_sessions", "net_pnl_inr", "net_r_multiple"):
        df[c] = pd.to_numeric(df[c], errors="coerce")
    df["entry_date"] = pd.to_datetime(df["entry_date"], errors="coerce")
    df["exit_date"] = pd.to_datetime(df["exit_date"], errors="coerce")
    df = df.dropna(subset=["symbol", "period", "entry_date", "net_pnl_inr", "net_r_multiple"])
    if df.empty:
        raise ValueError("No valid completed trades.")
    return df.sort_values(["period", "entry_date", "symbol"]).reset_index(drop=True)

def profit_factor(s):
    gp = s[s > 0].sum()
    gl = -s[s < 0].sum()
    return gp / gl if gl else float("nan")

def period_diagnostics(df):
    rows = []
    for period, g in df.groupby("period", observed=False):
        pnl = g.net_pnl_inr
        ordered = g.sort_values(["entry_date", "symbol"])
        losses = pnl[pnl < 0]
        stops = g[g.exit_reason.astype(str).str.startswith("stop")]
        rows.append({
            "period": period, "trades": len(g),
            "gross_profit_inr": round(pnl[pnl > 0].sum(), 2),
            "gross_loss_inr": round(-pnl[pnl < 0].sum(), 2),
            "profit_factor": round(profit_factor(pnl), 3),
            "stop_trade_share_pct": round(len(stops) / len(g) * 100, 2),
            "stop_net_pnl_inr": round(stops.net_pnl_inr.sum(), 2),
            "average_loss_inr": round(losses.mean(), 2) if len(losses) else 0,
            "median_loss_inr": round(losses.median(), 2) if len(losses) else 0,
            "worst_trade_inr": round(pnl.min(), 2),
            "best_trade_inr": round(pnl.max(), 2),
            "max_consecutive_losses": max_loss_streak(ordered.net_pnl_inr.tolist()),
            "first_half_pnl_inr": round(pnl.iloc[:len(pnl)//2].sum(), 2),
            "second_half_pnl_inr": round(pnl.iloc[len(pnl)//2:].sum(), 2),
        })
    return pd.DataFrame(rows)

def max_loss_streak(values):
    best = run = 0
    for value in values:
        if value < 0:
            run += 1
            best = max(best, run)
        else:
            run = 0
    return best

def symbol_diagnostics(df, minimum=5):
    rows = []
    for (period, symbol), g in df.groupby(["period", "symbol"], observed=False):
        if len(g) < minimum:
            continue
        rows.append({
            "period": period, "symbol": symbol, "trades": len(g),
            "net_pnl_inr": round(g.net_pnl_inr.sum(), 2),
            "win_rate_pct": round((g.net_pnl_inr > 0).mean()*100, 2),
            "profit_factor": round(profit_factor(g.net_pnl_inr), 3),
            "average_r": round(g.net_r_multiple.mean(), 3),
            "stop_share_pct": round(g.exit_reason.astype(str).str.startswith("stop").mean()*100, 2),
        })
    return pd.DataFrame(rows)

def rolling_diagnostics(df, window=30):
    rows = []
    for period, g in df.groupby("period", observed=False):
        g = g.sort_values(["entry_date", "symbol"]).copy()
        g["rolling_trade_count"] = range(1, len(g)+1)
        g["rolling_net_pnl_inr"] = g.net_pnl_inr.rolling(window, min_periods=window).sum()
        g["rolling_average_r"] = g.net_r_multiple.rolling(window, min_periods=window).mean()
        subset = g.dropna(subset=["rolling_average_r"])
        for _, r in subset.iterrows():
            rows.append({"period": period, "trade_number": int(r.rolling_trade_count),
                         "entry_date": r.entry_date.date().isoformat(),
                         "rolling_30_trade_pnl_inr": round(r.rolling_net_pnl_inr, 2),
                         "rolling_30_trade_average_r": round(r.rolling_average_r, 3)})
    return pd.DataFrame(rows)

def report(df, periods, symbols):
    lines = [
        "# Strategy Improvement Diagnostics",
        "",
        "Descriptive analysis of completed trades only. No alternative rules are tested,",
        "no causal claims are made, and no settings are changed.",
        "",
        "## Period-level loss diagnostics", "", periods.to_string(index=False),
        "", "## Symbol-level diagnostics (minimum 5 trades)", "",
        symbols.sort_values(["period", "net_pnl_inr"]).to_string(index=False) if not symbols.empty else "No qualifying groups.",
        "", "## What this export cannot answer", "",
        "- It cannot explain the price action or market regime immediately before each stop.",
        "- It cannot test alternative stop distances, entry filters, or holding rules.",
        "- It has completed trades only; rejected signals and overlapping portfolio positions are absent.",
        "- Trade ordering is approximated by entry date; same-day trades are ordered by symbol.",
        "- A 30-trade rolling window is descriptive and must not be used to tune rules on the holdout.",
        "",
        "## Research conclusions and safeguards", "",
        "- Stop exits and gap-stop exits should be examined separately from ordinary time exits.",
        "- Compare gross losses with gross profits; a high target payout alone does not establish positive expectancy.",
        "- Do not remove symbols or change filters based on this same out-of-sample sample.",
        "- Keep paper-only status until a pre-specified candidate passes a fresh untouched holdout",
        "  and a realistic portfolio-level simulation.",
        ""
    ]
    return "\n".join(lines)

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--input", default="backtest_trades.csv")
    p.add_argument("--report", default="improvement_research_report.md")
    p.add_argument("--symbol-output", default="improvement_by_symbol.csv")
    p.add_argument("--rolling-output", default="rolling_30_trade_diagnostics.csv")
    args = p.parse_args()
    df = load(args.input)
    periods = period_diagnostics(df)
    symbols = symbol_diagnostics(df)
    rolling = rolling_diagnostics(df)
    Path(args.report).write_text(report(df, periods, symbols), encoding="utf-8")
    symbols.to_csv(args.symbol_output, index=False)
    rolling.to_csv(args.rolling_output, index=False)
    print(f"Loaded {len(df)} completed trades.")
    print("\nPeriod diagnostics:")
    print(periods.to_string(index=False))
    print(f"\nSaved: {args.report}, {args.symbol_output}, {args.rolling_output}")
    print("No scanner, backtest, configuration, or trading rules were modified.")

if __name__ == "__main__":
    main()
