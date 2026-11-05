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


## Phase 5: close-based profit-protection experiment

Run after the baseline backtest has populated the local OHLCV snapshot:

```bash
python -m src.time_exit_research --config config.yaml --data-dir backtest_data
```

Candidate rule:
- A completed daily close at or above +1R arms protection.
- After arming, a later completed daily close below +0.5R schedules an exit at the next session open.
- If no next session exists within the original maximum holding window, the baseline time exit is retained.
- Original entries, initial stops, 2R targets, sizing, gap rejection, costs, and maximum holding period remain unchanged.

Outputs:
- `profit_protection_candidate_trades.csv`
- `profit_protection_research_report.md`

This is a research-only variant. Compare its development-period result with the baseline result on the same cached data. Do not tune the rule against the OOS period or treat a better historical result as proof of future profitability. The baseline backtest and production scanner are untouched.


## Phase 6: NIFTY 50 market-regime study

Run after the baseline backtest has created `backtest_trades.csv` and
`backtest_data/`:

```bash
python -m src.market_regime_research --input backtest_trades.csv --data-dir backtest_data --config config.yaml
```

The study tags each trade using NIFTY 50's latest available close on or before
its signal date. It reports above/below EMA50 and a four-state split that also
considers whether EMA50 is rising versus 20 prior trading observations.

Outputs:
- `market_regime_tagged_trades.csv`
- `market_regime_cohort_summary.csv`
- `market_regime_research_report.md`

These are descriptive cohorts of existing baseline trades, not a portfolio
re-simulation with a market filter. Use development results only to form a
single pre-specified hypothesis. OOS results are descriptive and must not be
used to select or tune a filter. No production rules are changed.

## Phase 7: stock relative-strength study vs NIFTY 50

Run after the baseline backtest has created `backtest_trades.csv` and
`backtest_data/`:

```bash
python -m src.relative_strength_research --input backtest_trades.csv --data-dir backtest_data --config config.yaml --lookback 20
```

The study measures each stock's trailing 20-session price return minus the
NIFTY 50's trailing 20-session price return, using the latest close on or
before each signal date. Fixed, pre-declared buckets are outperforming by at
least +2 percentage points, within ±2 percentage points, and underperforming
by at least -2 percentage points.

Outputs:
- `relative_strength_tagged_trades.csv`
- `relative_strength_cohort_summary.csv`
- `relative_strength_research_report.md`

This is a descriptive grouping of existing baseline trades, not a portfolio
re-simulation. Development results may motivate one hypothesis; OOS results
are descriptive only and must not be used to tune a filter. Short/missing
history is labelled unavailable. No production rules, scanner, configuration,
risk settings, or live-trading behavior are changed.


## Phase 8: transaction-cost sensitivity and constrained portfolio estimate

Run after the baseline backtest has created `backtest_trades.csv`:

```bash
python -m src.robustness_research --input backtest_trades.csv --capital 15000 --risk-pct 0.5 --max-position-pct 25 --max-positions 3
```

Outputs:
- `robustness_cost_sensitivity.csv`: fixed cost/slippage scenarios (20/5, 30/10, 40/15, and 60/20 basis points per side).
- `robustness_portfolio_estimate.csv`: approximate shared-capital reconstruction with risk-based quantity, 25% position cap, and maximum three overlapping positions.
- `robustness_research_report.md`: combined results and limitations.

The portfolio reconstruction is intentionally labelled approximate: it only has completed trades from independent per-symbol simulations, not all candidate signals or rejected entries. It re-sizes recorded trades chronologically and cannot reproduce a true daily portfolio or signal-ranking process. Treat it as a diagnostic lower-fidelity estimate, not validation or a forecast. No baseline scanner, backtest, or strategy parameters are changed; paper-only remains in force.


## Phase 9: chronological trade-close drawdown and exposure diagnostics

The baseline report now:
- Aggregates all completed-trade P&L by exit date before updating equity, making the
  realised trade-close drawdown independent of CSV row order and same-day trade ordering.
- Includes starting capital as the initial equity peak.
- Uses the union of available symbol trading dates for each period to estimate
  concurrent open positions and invested capital from entry date through exit date,
  inclusive.
- Reports average and maximum concurrent positions, percentage of sessions with
  positions open, and average invested capital as a percentage of realised equity.

These remain diagnostics over independent single-symbol simulations, not a true
shared-capital portfolio. They do not mark positions to market daily, model cash
constraints, or represent intraday drawdown. Exposure can exceed shared-portfolio
limits and must not be interpreted as executable portfolio utilisation.
