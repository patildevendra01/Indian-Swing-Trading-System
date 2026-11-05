# Fibonacci Pullback Entry Research

This is a separate research experiment. It does not modify the production
scanner, baseline backtest, risk settings, or paper-trading workflow.

## Fixed hypothesis

A confirmed daily higher-low / higher-high impulse is followed by a pullback
to one of four pre-declared retracement levels (0.50, 0.618, 0.66, 0.786).
A signal requires the daily low to touch the level and the daily close to finish
above the level, above the day's open, and above the prior close. Entry is the
next session open, with adverse slippage and an opening-gap rejection rule.

The stop is 0.25 signal-date ATR below the impulse higher low. Target uses the
configured minimum reward/risk (normally 2R). Holding is capped by the existing
configured maximum (normally 10 sessions). If stop and target are both touched
on one daily candle, the stop is assumed first.

## Run in Colab

After the baseline backtest has populated `backtest_data/`:

```bash
python -m src.fibonacci_pullback_backtest \
  --config config.yaml \
  --data-dir backtest_data \
  --baseline backtest_trades.csv
```

Outputs:
- `fibonacci_pullback_trades.csv`
- `fibonacci_pullback_summary.csv`
- `fibonacci_pullback_report.md`

Tests:

```bash
python -m unittest discover -s tests -p 'test_fibonacci_pullback_backtest.py' -v
```

## Interpretation safeguards

The four ratios are reported independently; do not choose the best ratio using
the already-inspected out-of-sample period. Costs use the repository's existing
delivery-cost model, with slippage separately applied. Price data are adjusted
daily OHLCV; intraday ordering is unknowable.

This first implementation simulates symbols independently. It is not a
portfolio simulation: simultaneous trades do not share ₹15,000 cash, and the
three-position account cap is not enforced across symbols. Therefore even a
positive result is only a hypothesis. A candidate must next pass a shared-cash
portfolio simulator and a genuinely future paper-trading validation window.

No scanner, baseline strategy, account risk setting, or live order behavior is
changed.
