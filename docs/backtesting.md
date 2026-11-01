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
