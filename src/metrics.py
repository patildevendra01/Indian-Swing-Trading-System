"""Chronological trade-close equity and calendar-based exposure diagnostics."""
import pandas as pd


def chronological_trade_metrics(trades, initial_capital, trading_calendar):
    """Measure realised trade-close drawdown and position exposure on supplied sessions.

    P&L is aggregated by exit date before equity is updated, so row order and
    same-day trade ordering cannot change the curve. Positions are counted from
    entry through exit dates inclusive. Exposure is descriptive of independent
    symbol simulations, not a shared-capital portfolio.
    """
    calendar = pd.DatetimeIndex(pd.to_datetime(trading_calendar)).normalize().unique().sort_values()
    if len(calendar) == 0:
        return {
            "max_drawdown_pct": 0.0, "avg_concurrent_positions": 0.0,
            "max_concurrent_positions": 0, "days_with_position_pct": 0.0,
            "avg_capital_exposure_pct": 0.0,
        }
    daily_pnl = pd.Series(0.0, index=calendar)
    active_count = pd.Series(0, index=calendar, dtype=int)
    invested = pd.Series(0.0, index=calendar)
    if trades is not None and not trades.empty:
        frame = trades.copy()
        frame["entry_date"] = pd.to_datetime(frame["entry_date"]).dt.normalize()
        frame["exit_date"] = pd.to_datetime(frame["exit_date"]).dt.normalize()
        frame["net_pnl_inr"] = pd.to_numeric(frame["net_pnl_inr"], errors="coerce").fillna(0.0)
        exits = frame.groupby("exit_date")["net_pnl_inr"].sum()
        for date, pnl in exits.items():
            if date in daily_pnl.index:
                daily_pnl.loc[date] += float(pnl)
        for row in frame.itertuples():
            held = calendar[(calendar >= row.entry_date) & (calendar <= row.exit_date)]
            if len(held):
                active_count.loc[held] += 1
                if hasattr(row, "entry") and hasattr(row, "quantity"):
                    invested.loc[held] += float(row.entry) * float(row.quantity)

    equity = float(initial_capital) + daily_pnl.cumsum()
    peak = equity.cummax().clip(lower=float(initial_capital))
    drawdown = (equity / peak - 1.0) * 100.0
    exposure = invested.div(equity.where(equity > 0)).fillna(0.0) * 100.0
    return {
        "max_drawdown_pct": round(float(drawdown.min()), 2),
        "avg_concurrent_positions": round(float(active_count.mean()), 2),
        "max_concurrent_positions": int(active_count.max()),
        "days_with_position_pct": round(float((active_count > 0).mean() * 100.0), 2),
        "avg_capital_exposure_pct": round(float(exposure.mean()), 2),
    }
