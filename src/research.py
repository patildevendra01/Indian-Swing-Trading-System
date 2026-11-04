"""Descriptive diagnostics for an existing backtest trade export.

This module does not alter strategy rules or generate trading signals.
Run from the repository root:
    python -m src.research --input backtest_trades.csv
"""
import argparse
from pathlib import Path

import pandas as pd

REQUIRED = {
    "symbol", "entry_date", "exit_date", "holding_sessions",
    "exit_reason", "net_pnl_inr", "net_r_multiple", "period",
}


def load_trades(path: str) -> pd.DataFrame:
    frame = pd.read_csv(path)
    missing = REQUIRED.difference(frame.columns)
    if missing:
        raise ValueError(f"Trade file is missing required columns: {sorted(missing)}")
    for col in ("holding_sessions", "net_pnl_inr", "net_r_multiple"):
        frame[col] = pd.to_numeric(frame[col], errors="coerce")
    frame["entry_date"] = pd.to_datetime(frame["entry_date"], errors="coerce")
    frame["exit_date"] = pd.to_datetime(frame["exit_date"], errors="coerce")
    frame = frame.dropna(subset=["symbol", "period", "net_pnl_inr", "net_r_multiple"])
    if frame.empty:
        raise ValueError("No valid completed trades found.")
    return frame


def summarize(group: pd.DataFrame) -> dict:
    pnl = group["net_pnl_inr"]
    wins = pnl[pnl > 0].sum()
    losses = -pnl[pnl < 0].sum()
    return {
        "trades": len(group),
        "win_rate_pct": round((pnl > 0).mean() * 100, 2),
        "net_pnl_inr": round(pnl.sum(), 2),
        "profit_factor": round(wins / losses, 3) if losses else None,
        "average_r": round(group["net_r_multiple"].mean(), 3),
        "average_hold_sessions": round(group["holding_sessions"].mean(), 2),
    }


def grouped_summary(frame: pd.DataFrame, keys) -> pd.DataFrame:
    rows = []
    for values, group in frame.groupby(keys, dropna=False):
        if not isinstance(values, tuple):
            values = (values,)
        row = dict(zip(keys, values))
        row.update(summarize(group))
        rows.append(row)
    return pd.DataFrame(rows)


def build_report(frame: pd.DataFrame) -> str:
    lines = [
        "# Trade Diagnostics (Descriptive Only)",
        "",
        "This report describes completed trades from the existing backtest export. "
        "It does not test alternative entry/exit rules and is not a performance forecast.",
        "",
        "## Results by period",
    ]
    by_period = grouped_summary(frame, ["period"])
    lines += ["", by_period.to_markdown(index=False), "", "## Results by exit reason and period"]
    by_exit = grouped_summary(frame, ["period", "exit_reason"])
    lines += ["", by_exit.to_markdown(index=False), "", "## Holding-duration buckets"]
    bins = [0, 1, 3, 5, 7, 10, float("inf")]
    labels = ["1", "2-3", "4-5", "6-7", "8-10", "11+"]
    temp = frame.copy()
    temp["holding_bucket"] = pd.cut(
        temp["holding_sessions"], bins=bins, labels=labels, include_lowest=True
    )
    by_hold = grouped_summary(temp, ["period", "holding_bucket"])
    lines += ["", by_hold.to_markdown(index=False), "", "## Symbol results (minimum 5 trades)"]
    symbol_counts = frame.groupby(["period", "symbol"]).size().rename("sample_trades")
    eligible = symbol_counts[symbol_counts >= 5].index
    symbol_frame = frame.set_index(["period", "symbol"]).loc[
        frame.set_index(["period", "symbol"]).index.isin(eligible)
    ].reset_index()
    by_symbol = grouped_summary(symbol_frame, ["period", "symbol"])
    if by_symbol.empty:
        lines += ["", "No symbol-period group had at least five trades."]
    else:
        lines += ["", by_symbol.sort_values(["period", "net_pnl_inr"]).to_markdown(index=False)]
    lines += [
        "",
        "## Interpretation safeguards",
        "",
        "- Small symbol samples are not evidence of a repeatable edge.",
        "- Exit-reason and holding-bucket summaries are conditional descriptions, not causal tests.",
        "- The export contains no complete per-bar candidate data, so it cannot establish which "
        "entry-filter combinations would have performed better.",
        "- Do not select a new strategy from these same out-of-sample results. Any proposed change "
        "needs a fresh, untouched validation period and realistic portfolio-level testing.",
        "",
    ]
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", default="backtest_trades.csv")
    parser.add_argument("--report", default="research_report.md")
    parser.add_argument("--symbol-output", default="research_by_symbol.csv")
    args = parser.parse_args()

    frame = load_trades(args.input)
    report = build_report(frame)
    Path(args.report).write_text(report, encoding="utf-8")
    by_symbol = grouped_summary(frame, ["period", "symbol"])
    by_symbol.to_csv(args.symbol_output, index=False)
    print(f"Loaded {len(frame)} completed trades from {args.input}")
    print("\nPeriod summary:")
    print(grouped_summary(frame, ["period"]).to_string(index=False))
    print(f"\nSaved descriptive report to {args.report}")
    print(f"Saved symbol summary to {args.symbol_output}")
    print("No scanner, strategy, or backtest rules were modified.")


if __name__ == "__main__":
    main()
