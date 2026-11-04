"""Research-only NIFTY 50 market-regime analysis of completed baseline trades."""
import argparse
from pathlib import Path
import pandas as pd
import yaml

try:
    from .backtest import load_or_download_history
except ImportError:
    from src.backtest import load_or_download_history


def build_regime_history(index_frame):
    """Build lag-safe EMA50 level and 20-observation slope labels."""
    if "Close" not in index_frame:
        raise ValueError("NIFTY history must contain a Close column")
    out = index_frame[["Close"]].copy()
    out["ema50"] = out["Close"].ewm(span=50, adjust=False, min_periods=50).mean()
    out["ema50_rising"] = out["ema50"] > out["ema50"].shift(20)
    valid = out["ema50"].notna() & out["ema50_rising"].notna()
    above = out["Close"] > out["ema50"]
    out["regime"] = "unavailable"
    out.loc[valid & above & out["ema50_rising"], "regime"] = "above_rising"
    out.loc[valid & above & ~out["ema50_rising"], "regime"] = "above_flat_or_falling"
    out.loc[valid & ~above & out["ema50_rising"], "regime"] = "below_rising"
    out.loc[valid & ~above & ~out["ema50_rising"], "regime"] = "below_falling"
    out["above_ema50_label"] = "unavailable"
    out.loc[valid & above, "above_ema50_label"] = "above_ema50"
    out.loc[valid & ~above, "above_ema50_label"] = "below_or_at_ema50"
    return out


def attach_signal_regime(trades, regime_history):
    """Join the latest NIFTY observation on or before each signal date."""
    if "signal_date" not in trades:
        raise ValueError("Trade file must contain signal_date")
    hist = regime_history.copy()
    hist.index = pd.to_datetime(hist.index).tz_localize(None).normalize()
    hist = hist[~hist.index.duplicated(keep="last")].sort_index()
    left = trades.copy()
    left["_row_order"] = range(len(left))
    left["_signal_dt"] = pd.to_datetime(left["signal_date"]).dt.tz_localize(None).dt.normalize()
    right = hist.reset_index()
    right = right.rename(columns={right.columns[0]: "_market_date"})
    joined = pd.merge_asof(left.sort_values("_signal_dt"), right.sort_values("_market_date"),
        left_on="_signal_dt", right_on="_market_date", direction="backward")
    joined["market_data_date"] = joined["_market_date"].dt.strftime("%Y-%m-%d").fillna("")
    return joined.sort_values("_row_order").drop(columns=["_row_order", "_signal_dt", "_market_date"])


def summarize_cohorts(trades, min_trades=1):
    required = {"period", "regime", "net_pnl_inr", "net_r_multiple"}
    missing = required - set(trades.columns)
    if missing:
        raise ValueError(f"Trade data missing columns: {', '.join(sorted(missing))}")
    rows = []
    for (period, regime), group in trades.groupby(["period", "regime"], dropna=False, sort=True):
        pnl = pd.to_numeric(group["net_pnl_inr"], errors="coerce").dropna()
        r = pd.to_numeric(group["net_r_multiple"], errors="coerce").dropna()
        if len(group) < min_trades:
            continue
        gp, gl = pnl[pnl > 0].sum(), -pnl[pnl < 0].sum()
        rows.append({"period": period, "regime": regime, "trades": len(group),
            "win_rate_pct": round(float((pnl > 0).mean() * 100), 2) if len(pnl) else 0.0,
            "net_pnl_inr": round(float(pnl.sum()), 2),
            "profit_factor": round(float(gp / gl), 3) if gl else (float("inf") if gp else 0.0),
            "average_r": round(float(r.mean()), 3) if len(r) else None})
    return pd.DataFrame(rows)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", default="backtest_trades.csv")
    parser.add_argument("--data-dir", default="backtest_data")
    parser.add_argument("--config", default="config.yaml")
    parser.add_argument("--min-trades", type=int, default=20)
    args = parser.parse_args()
    if args.min_trades < 1:
        parser.error("--min-trades must be at least 1")
    trades = pd.read_csv(args.input)
    with open(args.config, encoding="utf-8") as handle:
        cfg = yaml.safe_load(handle)
    raw, source = load_or_download_history("^NSEI", args.data_dir,
        cfg.get("backtest", {}).get("history_period", "5y"))
    if raw.empty:
        raise SystemExit("NIFTY 50 history unavailable; no regime report generated.")
    regime = build_regime_history(raw)
    enriched = attach_signal_regime(trades, regime)
    enriched.to_csv("market_regime_tagged_trades.csv", index=False)
    summary = summarize_cohorts(enriched, args.min_trades)
    summary.to_csv("market_regime_cohort_summary.csv", index=False)
    report = ["# NIFTY 50 Market-Regime Trade Study", "",
        "Regime uses the latest NIFTY 50 daily close on or before each trade signal date.",
        "Above/below EMA50 describes index level; rising/flat-or-falling compares EMA50 with its value 20 trading observations earlier.",
        f"Index data source: {source.get('source', 'unknown')}; rows: {source.get('rows', len(raw))}.", "",
        f"## Cohort results (minimum trades: {args.min_trades})", "",
        summary.to_string(index=False) if not summary.empty else "No cohorts met the minimum trade count.", "",
        "## Interpretation and guardrails", "",
        "- Development cohorts may form one pre-specified hypothesis; do not repeatedly optimize thresholds.",
        "- OOS figures are descriptive only. Do not use them to choose a regime filter; preserve the holdout.",
        "- These are existing trades grouped by regime, not a re-run with trades removed. Sizing, overlap and capital path are not recalculated.",
        "- Four states can create small samples; inspect counts before drawing conclusions.",
        "- NIFTY 50 is a broad-market proxy, not each stock's sector.",
        "- Yahoo Finance data can be revised, delayed or incomplete; reuse the same cached snapshot.",
        "- No scanner, baseline rules, account risk settings, or live-trading behavior are changed.", ""]
    Path("market_regime_research_report.md").write_text("\n".join(report), encoding="utf-8")
    print("Market regime cohort summary:")
    print(summary.to_string(index=False))
    print("\nSaved market_regime_tagged_trades.csv, market_regime_cohort_summary.csv, and market_regime_research_report.md")
    print("Research-only; baseline scanner and backtest remain unchanged.")


if __name__ == "__main__":
    main()
