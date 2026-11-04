# Backtesting: Assumptions and Limitations

Run: `python -m src.backtest --config config.yaml`

Optional assumptions: `--cost-bps 20 --slippage-bps 5 --max-gap-pct 2.5`. These are user-configurable illustrative assumptions, not current broker fee quotes. Replace them with a realistic, broker-specific cost model before interpreting results.

## Execution model
- Indicators and signals are evaluated only on completed daily candles.
- A signal at close is entered at the next session open.
- Large next-session gaps beyond the configured threshold are skipped.
- The initial stop is based on the signal candle's close and ATR; quantity is recalculated using the next open.
- Stop/target checks use daily high/low. If both levels are touched in one candle, the backtester assumes the stop happened first.
- Stop gaps exit at the opening price, not the stop price.
- Trades are sequential per symbol; the script does not simulate a combined multi-stock portfolio or correlated exposure.
- Cost and slippage are simple basis-point estimates. Taxes and charges are not individually modeled.

## Interpretation
This is an exploratory sanity-check, not evidence of a tradable edge. Historical adjusted data can be incomplete; current watchlists create survivorship bias; the scanner does not include delisted stocks. The default 5-year window is not a substitute for multiple market regimes. Do not optimize parameters on the same period used to report performance.

Before any live use, add point-in-time constituents, corporate-action handling, a portfolio-level cash/risk engine, realistic broker/exchange charges, out-of-sample and walk-forward validation, and paper-trade reconciliation. A backtest cannot guarantee future results.


## Walk-forward and benchmark report

The backtest now divides the downloaded history chronologically: the first three calendar years are reported as a development period and the following two years as an out-of-sample holdout. The strategy rules are held fixed in both periods; this is a chronological validation split, not parameter optimization. Each period is simulated separately, so positions do not cross the split boundary and each symbol/period starts with the configured capital for sizing.

For each period, the console reports per-filter pass/fail counts after the EMA warm-up, raw qualifying signals, completed trades, gap/risk rejections, and truncated positions. This helps identify which condition is limiting signal frequency. A signal is counted only where a following session exists for next-open execution.

The script also retrieves the NIFTY 50 price-index return over the out-of-sample date range. This is a market reference only: it excludes dividends and is not directly comparable to the sum of independent single-stock trade P&L.

Important caveats: the 3y/2y split is based on the earliest downloaded symbol history; symbol histories can start/end on different dates. A fixed ruleset avoids tuning on the holdout, but the first three years have not been parameter-optimized. The strategy report is not a combined portfolio return. Drawdown is calculated on sequential completed-trade P&L, not daily marked-to-market equity, and exposure is a rough sum across independent symbol simulations.
