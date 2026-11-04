# Isolated Strategy Research

This work lives on the `research/strategy-diagnostics` branch. It does not modify
`src/scan.py`, `src/backtest.py`, the strategy configuration, or the production
scanner rules.

## Phase 1: descriptive trade diagnostics

After running the existing backtest and producing `backtest_trades.csv`, run:

```bash
python -m src.research --input backtest_trades.csv
```

The script produces:
- `research_report.md`: results by period, exit reason, holding-duration bucket,
  and symbol-period groups with at least five trades.
- `research_by_symbol.csv`: per-symbol descriptive metrics.

Metrics include trade count, win rate, net P&L, profit factor, average net R,
and average holding sessions.

## Important interpretation limits

This is a descriptive review of already completed trades, not a new backtest.
It cannot determine which alternative filter combinations would have worked,
because the trade export does not contain every eligible bar and every rejected
candidate. Exit-reason and holding-duration summaries are conditional outcomes,
not causal evidence that changing an exit rule will improve returns.

Do not choose a revised strategy using the same out-of-sample period and then
present that period as independent validation. Any candidate changes must be
specified before evaluation on a fresh, untouched holdout. A later phase may
add controlled alternative-rule simulations using the underlying daily OHLCV
data, with the original baseline kept unchanged.

All results remain paper-research only. No live orders or broker integration.
