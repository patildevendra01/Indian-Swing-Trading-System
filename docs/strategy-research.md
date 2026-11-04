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
