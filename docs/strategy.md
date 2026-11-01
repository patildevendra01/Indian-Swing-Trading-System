# Swing Strategy Rules (Indian Cash Equities)

## Mandate

- Long-only NSE/BSE cash-equity research.
- Intended holding period: 3–10 trading sessions.
- No intraday system, futures, options, leverage, shorting, or auto-execution.
- A scan result is a candidate for human review, never an order instruction.

## Screening conditions

The initial scanner requires all of the following on daily candles:

1. Close above EMA 20, and EMA 20 above EMA 50.
2. RSI(14) between 50 and 70 (avoid chasing very extended momentum).
3. Latest volume at least 1.5 times its 20-session average.
4. Close above the previous 20-session high.
5. Price at least ₹50.
6. Average daily traded value at least ₹5 crore (approximate liquidity filter).
7. ATR as a percentage of price no greater than 6%.

These are configurable starting hypotheses, not proven edges. Do not loosen filters just to produce a candidate.

## Before considering entry

Manually verify:
- Latest exchange quote, candle timestamp, volume, spreads, delivery/market liquidity.
- Company filings and corporate announcements on NSE/BSE.
- Results, board meetings, dividends, splits, rights issues, mergers, pledges, promoter transactions, bulk/block deals, and material litigation/regulatory news.
- Sector and NIFTY trend; broad-market weakness can invalidate an otherwise attractive chart.
- No trading halt, surveillance restriction (ASM/GSM), circuit constraint, or unusual price/volume anomaly.
- Entry is not materially above the breakout level; avoid chasing a large gap-up.

## Risk and sizing

- Maximum planned risk per trade: 0.5% of configured account capital.
- Position value cap: 25% of capital by default.
- Quantity = minimum of (risk budget / entry-to-stop distance) and (position cap / entry).
- Scanner stop reference is 1.5 ATR below reference close. This is only a starting point; chart structure/support must be checked. Never widen a stop to justify a larger quantity.
- Initial target reference is at least 2R above entry.
- If one share exceeds the risk or capital limit, do not trade.
- Keep total open risk within a separately defined portfolio limit; the initial CLI does not track open positions, so the user must enforce this manually.
- Do not average down or add to a losing position.

## Exit and invalidation

- Exit if the stop is hit; real fills can be worse due to gaps/slippage.
- Reassess if the thesis fails, the breakout closes back below its level, or material negative news emerges.
- Take-profit planning should be based on price structure and a minimum 2R opportunity, not a guaranteed target.
- Time stop: review at the end of session 10; exit or document a specific reason to continue.
- Do not move a stop farther away. Any trailing-stop method must be tested before use.

## No-trade conditions

No trade if data is missing/stale, liquidity is inadequate, spreads are wide, price is circuit-bound, major event risk is imminent and unassessed, risk/reward is below 2, stop distance makes quantity zero, or the broader market is disorderly.

## Paper-trading protocol

1. Record the signal timestamp and the exact data source.
2. Record planned entry, stop, target, quantity, thesis, and event checks before entry.
3. Record actual simulated fill, exit, costs, slippage, and reason for exit.
4. Log every eligible candidate, including rejected/no-trade cases, to reduce selection bias.
5. Review at least 30–50 paper trades before considering any capital deployment; evaluate expectancy, win rate, average win/loss, drawdown, and rule adherence.
6. Backtest with survivorship bias, corporate actions, realistic costs, slippage, and next-session execution assumptions in mind.

## Risk disclosure

A 0.5% planned risk is not a maximum guaranteed loss. Overnight gaps, liquidity, exchange halts, and slippage can cause larger losses. This is educational software, not personalized investment advice.
