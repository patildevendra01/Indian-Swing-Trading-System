"""Trade-path excursion diagnostics for completed backtest trades.

Run: python -m src.trade_path_research --input backtest_trades.csv
Requires a fresh export from the research branch with MFE/MAE fields.
Descriptive only; does not change entries, exits, sizing, or strategy rules.
"""
import argparse
from pathlib import Path
import pandas as pd

REQUIRED = {"period", "exit_reason", "net_pnl_inr", "net_r_multiple",
            "holding_sessions", "mfe_r", "mae_r", "best_close_r", "exit_fill_r"}


def load(path):
    df = pd.read_csv(path)
    missing = REQUIRED - set(df.columns)
    if missing:
        raise ValueError(
            "Trade export is missing path-diagnostic fields: " + ", ".join(sorted(missing)) +
            ". Pull the latest research branch and rerun the backtest."
        )
    for col in ("net_pnl_inr", "net_r_multiple", "holding_sessions",
                "mfe_r", "mae_r", "best_close_r", "exit_fill_r"):
        df[col] = pd.to_numeric(df[col], errors="coerce")
    return df.dropna(subset=["period", "exit_reason", "mfe_r", "mae_r"]).copy()


def summarize_paths(df):
    rows = []
    for (period, reason), g in df.groupby(["period", "exit_reason"], observed=False):
        rows.append({
            "period": period, "exit_reason": reason, "trades": len(g),
            "net_pnl_inr": round(g.net_pnl_inr.sum(), 2),
            "average_net_r": round(g.net_r_multiple.mean(), 3),
            "avg_mfe_r": round(g.mfe_r.mean(), 3),
            "median_mfe_r": round(g.mfe_r.median(), 3),
            "share_mfe_ge_0_5r_pct": round((g.mfe_r >= 0.5).mean() * 100, 2),
            "share_mfe_ge_1r_pct": round((g.mfe_r >= 1.0).mean() * 100, 2),
            "share_mfe_ge_1_5r_pct": round((g.mfe_r >= 1.5).mean() * 100, 2),
            "avg_mae_r": round(g.mae_r.mean(), 3),
            "avg_best_close_r": round(g.best_close_r.mean(), 3),
            "avg_exit_fill_r": round(g.exit_fill_r.mean(), 3),
            "avg_holding_sessions": round(g.holding_sessions.mean(), 2),
        })
    return pd.DataFrame(rows)


def summarize_periods(df):
    rows = []
    for period, g in df.groupby("period", observed=False):
        rows.append({
            "period": period, "trades": len(g),
            "avg_mfe_r": round(g.mfe_r.mean(), 3),
            "median_mfe_r": round(g.mfe_r.median(), 3),
            "share_mfe_ge_0_5r_pct": round((g.mfe_r >= 0.5).mean() * 100, 2),
            "share_mfe_ge_1r_pct": round((g.mfe_r >= 1.0).mean() * 100, 2),
            "share_mfe_ge_1_5r_pct": round((g.mfe_r >= 1.5).mean() * 100, 2),
            "avg_mae_r": round(g.mae_r.mean(), 3),
            "avg_best_close_r": round(g.best_close_r.mean(), 3),
            "avg_exit_fill_r": round(g.exit_fill_r.mean(), 3),
        })
    return pd.DataFrame(rows)


def render(periods, paths):
    return "\n".join([
        "# Trade Path / MFE-MAE Research", "",
        "Descriptive diagnostics only. No strategy parameters or trading rules were changed.", "",
        "## Period summary", "", periods.to_string(index=False),
        "", "## Exit-reason summary", "", paths.to_string(index=False),
        "", "## Definitions and safeguards", "",
        "- MFE R: highest daily high from entry through exit, measured in initial entry-to-stop risk units.",
        "- MAE R: lowest daily low from entry through exit, measured in the same risk units; negative values are adverse.",
        "- Best-close R: highest daily close while the position remained open; it is blank when a gap exit occurs at the entry open. Exit-fill R: simulated exit price in initial-risk units.",
        "- Daily OHLC bars do not reveal the intraday order of highs and lows. Excursions on a stop/target day are not proof that an intraday target was executable before a stop.",
        "- MFE/MAE include the exit session while the position is considered open; for opening-gap exits only the opening price is counted, not later same-day highs/lows.",
        "- Do not select thresholds from the out-of-sample period. Use development results to form a pre-specified hypothesis, then validate on a fresh untouched holdout.",
        "- Existing entry, stop, target, position sizing, filters, and paper-only policy remain unchanged.", ""
    ])


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--input", default="backtest_trades.csv")
    p.add_argument("--report", default="trade_path_research_report.md")
    p.add_argument("--exit-output", default="trade_path_by_exit.csv")
    p.add_argument("--period-output", default="trade_path_by_period.csv")
    args = p.parse_args()
    df = load(args.input)
    periods, paths = summarize_periods(df), summarize_paths(df)
    Path(args.report).write_text(render(periods, paths), encoding="utf-8")
    periods.to_csv(args.period_output, index=False)
    paths.to_csv(args.exit_output, index=False)
    print(f"Loaded {len(df)} completed trades.")
    print("\nTrade path summary by period:")
    print(periods.to_string(index=False))
    print("\nTrade path summary by exit reason:")
    print(paths.to_string(index=False))
    print(f"\nSaved: {args.report}, {args.period_output}, {args.exit_output}")
    print("No trading rules or parameters were changed.")


if __name__ == "__main__":
    main()
