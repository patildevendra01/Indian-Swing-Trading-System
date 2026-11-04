# Isolated Strategy Research

All work is on `research/strategy-diagnostics`; the production scanner and
baseline backtest remain unchanged.

## Phase 1: descriptive trade diagnostics

Run after the baseline backtest creates `backtest_trades.csv`:

```bash
python -m src.research --input backtest_trades.csv
```

Outputs: `research_report.md` and `research_by_symbol.csv`.

## Phase 2: loss diagnostics

Run:

```bash
python -m src.improvement_research --input backtest_trades.csv
```

Outputs:
- `improvement_research_report.md`: period-level loss concentration,
  stop-exit share, average/median loss, worst/best trade, consecutive loss
  streaks, first-half vs second-half P&L, and symbol diagnostics.
- `improvement_by_symbol.csv`: per-symbol-period diagnostics for groups
  with at least five completed trades.
- `rolling_30_trade_diagnostics.csv`: chronological rolling 30-trade net P&L
  and average R, separately by period.

## Interpretation limits

These are descriptive diagnostics, not causal tests or strategy optimization.
The trade export does not include all candidate bars, rejected signals, market
regime snapshots, or simultaneous portfolio positions. Therefore this phase
cannot establish that changing a stop, entry filter, holding period, or
watchlist will improve returns.

Do not select new rules from the same out-of-sample period and call it
independent validation. Any future candidate must be specified in advance,
tested on development data, and then evaluated on a fresh untouched holdout
with realistic portfolio constraints and costs.

The baseline scanner, backtest, configuration, 0.5% risk cap, and paper-only
policy are not modified. No broker connection or live order execution.


## Phase 3: entry-gap and initial-stop-distance diagnostics

After pulling the latest research branch, regenerate the trade export because the backtest now adds signal close, signal ATR, next-session entry gap, and actual entry-to-stop distance fields. Then run:

```bash
python -m src.entry_risk_research --input backtest_trades.csv
```

Outputs:
- `entry_risk_research_report.md`: period summary of entry gaps, initial stop distance, distance relative to signal ATR, and normal versus gap-through stops.
- `entry_gap_buckets.csv`: trade outcomes grouped by next-session opening gap.
- `stop_exit_types.csv`: P&L split by stop exit reason.

This only adds diagnostic fields to completed trade records. It does not change the entry, stop, target, position sizing, filters, or scanner. Existing `backtest_trades.csv` files do not contain the new fields and must be regenerated.

## Phase 4: trade-path excursion diagnostics

After pulling the latest research branch, regenerate `backtest_trades.csv` so each completed trade includes MFE, MAE, best-close R, and exit-close R diagnostics. Then run:

```bash
python -m src.trade_path_research --input backtest_trades.csv
```

Outputs:
- `trade_path_research_report.md`: period and exit-reason summaries.
- `trade_path_by_period.csv`: aggregate excursion metrics by chronological period.
- `trade_path_by_exit.csv`: excursion metrics split by stop, target, and time exits.

MFE/MAE use daily high/low values through the exit session and are not executable intraday paths. In particular, a daily bar cannot establish whether a target was reached before a stop on the same session. These fields are descriptive only; no entry, stop, target, sizing, filter, or scanner rule is changed.
