# Fibonacci Retracement Research

This is an isolated, descriptive research module for the Indian daily-bar swing
system. It does not alter the production scanner, baseline backtest, risk
settings, or paper-trading workflow.

## What it tests

The module tags trades from an existing `backtest_trades.csv` export. At each
trade's signal-date close, it looks for a confirmed long-side market structure
with higher highs and higher lows, then calculates retracement prices from the
latest confirmed upward impulse. It checks proximity to:

- 0.50
- 0.618
- 0.66
- 0.786
- The 0.618–0.66 Golden Pocket band

The default proximity tolerance is 1% of the signal-date close. Swing points
use three bars on each side by default. A pivot is unavailable until all
right-side confirmation bars have elapsed, and the signal date cannot use
later data.

## Run

From the repository root, after the baseline backtest has created its trade CSV:

```bash
python -m src.fibonacci_research --input backtest_trades.csv --data-dir backtest_data --config config.yaml
```

Optional research assumptions:

```bash
python -m src.fibonacci_research --input backtest_trades.csv --data-dir backtest_data --config config.yaml --tolerance-pct 1.0 --left-bars 3 --right-bars 3 --min-trades 20
```

Outputs:

- `fibonacci_tagged_trades.csv`
- `fibonacci_cohort_summary.csv`
- `fibonacci_research_report.md`

Run unit tests:

```bash
python -m unittest tests.test_fibonacci_research -v
```

## Important interpretation limits

This first phase is a cohort diagnostic, not a new entry/exit backtest. It
compares the existing baseline trades that happened to signal near each
retracement level against all baseline trades in the same period. Cohorts
overlap. It cannot show that entering at a Fibonacci level would have filled,
or estimate the stop/target path of a new pullback strategy.

A promising cohort is only a hypothesis. Before adoption, specify a separate
pullback-entry simulation with executable next-session prices, stop placement,
holding-period limits, realistic Indian delivery costs and slippage, portfolio
capital constraints, and an untouched out-of-sample period. Do not tune
thresholds against the existing out-of-sample results.

No scanner or baseline strategy rules are changed by this module.
