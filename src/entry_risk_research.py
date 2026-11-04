"""Entry-gap and initial-stop-distance diagnostics for completed backtest trades.

Run: python -m src.entry_risk_research --input backtest_trades.csv
Requires a fresh backtest export containing the added entry-risk columns.
Descriptive only: does not alter strategy rules or test alternative parameters.
"""
import argparse
from pathlib import Path
import pandas as pd

REQUIRED = {
    "symbol", "period", "signal_date", "entry_date", "exit_reason",
    "signal_close", "signal_atr", "entry_gap_pct",
    "entry_stop_distance_inr", "entry_stop_distance_pct",
    "stop_distance_vs_signal_atr", "net_pnl_inr", "net_r_multiple",
}

def load(path):
    df = pd.read_csv(path)
    missing = REQUIRED - set(df.columns)
    if missing:
        raise ValueError(
            "Trade export is missing research fields: " + ", ".join(sorted(missing)) +
            ". Pull the research branch and rerun the backtest to regenerate it."
        )
    numeric = [
        "signal_close", "signal_atr", "entry_gap_pct",
        "entry_stop_distance_inr", "entry_stop_distance_pct",
        "stop_distance_vs_signal_atr", "net_pnl_inr", "net_r_multiple",
    ]
    for col in numeric:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df["entry_date"] = pd.to_datetime(df["entry_date"], errors="coerce")
    df = df.dropna(subset=["period", "entry_date", "entry_gap_pct",
                           "entry_stop_distance_pct", "net_pnl_inr"])
    if df.empty:
        raise ValueError("No valid completed trades with entry-risk fields.")
    return df.sort_values(["period", "entry_date", "symbol"]).reset_index(drop=True)

def summarize(df):
    rows = []
    for period, g in df.groupby("period", observed=False):
        stop = g[g.exit_reason.astype(str).str.startswith("stop")]
        gap_stop = g[g.exit_reason.astype(str).eq("stop_gap")]
        normal_stop = g[g.exit_reason.astype(str).isin(["stop", "both_hit_stop_assumed"])]
        rows.append({
            "period": period,
            "trades": len(g),
            "avg_entry_gap_pct": round(g.entry_gap_pct.mean(), 4),
            "median_entry_gap_pct": round(g.entry_gap_pct.median(), 4),
            "positive_gap_share_pct": round((g.entry_gap_pct > 0).mean() * 100, 2),
            "negative_gap_share_pct": round((g.entry_gap_pct < 0).mean() * 100, 2),
            "median_stop_distance_pct": round(g.entry_stop_distance_pct.median(), 4),
            "median_stop_distance_inr": round(g.entry_stop_distance_inr.median(), 4),
            "median_stop_vs_signal_atr": round(g.stop_distance_vs_signal_atr.median(), 4),
            "trades_stop_distance_over_1_5_atr": int((g.stop_distance_vs_signal_atr > 1.5).sum()),
            "stop_exit_count": len(stop),
            "stop_exit_net_pnl_inr": round(stop.net_pnl_inr.sum(), 2),
            "gap_stop_count": len(gap_stop),
            "gap_stop_net_pnl_inr": round(gap_stop.net_pnl_inr.sum(), 2),
            "ordinary_or_both_hit_stop_count": len(normal_stop),
            "ordinary_or_both_hit_stop_net_pnl_inr": round(normal_stop.net_pnl_inr.sum(), 2),
        })
    return pd.DataFrame(rows)

def gap_buckets(df):
    bins = [-float("inf"), -1.0, -0.5, 0.5, 1.0, float("inf")]
    labels = ["<= -1%", "-1% to -0.5%", "-0.5% to +0.5%", "+0.5% to +1%", "> +1%"]
    work = df.copy()
    work["gap_bucket"] = pd.cut(work.entry_gap_pct, bins=bins, labels=labels, right=True)
    rows = []
    for (period, bucket), g in work.groupby(["period", "gap_bucket"], observed=False):
        if g.empty:
            continue
        rows.append({
            "period": period, "gap_bucket": str(bucket), "trades": len(g),
            "win_rate_pct": round((g.net_pnl_inr > 0).mean() * 100, 2),
            "net_pnl_inr": round(g.net_pnl_inr.sum(), 2),
            "average_r": round(g.net_r_multiple.mean(), 3),
            "stop_exit_share_pct": round(g.exit_reason.astype(str).str.startswith("stop").mean() * 100, 2),
        })
    return pd.DataFrame(rows)

def stop_reason_summary(df):
    work = df[df.exit_reason.astype(str).str.startswith("stop")].copy()
    if work.empty:
        return pd.DataFrame(columns=["period", "exit_reason", "trades", "net_pnl_inr", "average_r"])
    return (work.groupby(["period", "exit_reason"], observed=False)
            .agg(trades=("net_pnl_inr", "size"),
                 net_pnl_inr=("net_pnl_inr", "sum"),
                 average_r=("net_r_multiple", "mean"))
            .reset_index().round({"net_pnl_inr": 2, "average_r": 3}))

def render(periods, gaps, reasons):
    return "\n".join([
        "# Entry Gap and Initial Stop-Distance Diagnostics", "",
        "Descriptive analysis of completed trades only. No strategy rules or parameters were changed.", "",
        "## By period", "", periods.to_string(index=False),
        "", "## Entry-gap buckets", "", gaps.to_string(index=False) if not gaps.empty else "No gap buckets.",
        "", "## Stop exit types", "", reasons.to_string(index=False) if not reasons.empty else "No stop exits.",
        "", "## Interpretation safeguards", "",
        "- Entry gap is next-session open versus signal-session close; it is not an intraday fill estimate.",
        "- Initial stop distance is measured from actual next-session entry to the stop calculated from signal close and signal ATR.",
        "- A stop distance above 1.5 signal ATR can arise because the next-session entry is above the signal close.",
        "- These are descriptive associations, not proof that gaps caused losses or that changing a stop improves results.",
        "- The backtest's entry, stop, target, sizing, filters, and paper-only policy remain unchanged.",
        "- Re-run on a fresh untouched holdout before evaluating any future rule change.", ""
    ])

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--input", default="backtest_trades.csv")
    p.add_argument("--report", default="entry_risk_research_report.md")
    p.add_argument("--gap-output", default="entry_gap_buckets.csv")
    p.add_argument("--stop-output", default="stop_exit_types.csv")
    args = p.parse_args()
    df = load(args.input)
    periods, gaps, reasons = summarize(df), gap_buckets(df), stop_reason_summary(df)
    Path(args.report).write_text(render(periods, gaps, reasons), encoding="utf-8")
    gaps.to_csv(args.gap_output, index=False)
    reasons.to_csv(args.stop_output, index=False)
    print(f"Loaded {len(df)} completed trades.")
    print("\nEntry and stop-distance diagnostics:")
    print(periods.to_string(index=False))
    print(f"\nSaved: {args.report}, {args.gap_output}, {args.stop_output}")
    print("No scanner, signal, sizing, stop, target, or trading rules were changed.")

if __name__ == "__main__":
    main()
