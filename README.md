# Indian Swing Trading System

A research and paper-trading toolkit for Indian cash-equity swing trades (NSE/BSE). It is designed around a 3–10 trading-day holding window, strict position sizing, and explicit no-trade decisions.

> **Educational software, not investment advice.** Signals are screening candidates, not buy/sell recommendations or guaranteed returns. Market data from free sources may be delayed, incomplete, adjusted, or unavailable. Verify prices, corporate actions, liquidity, disclosures, and costs with primary sources and your broker before acting.

## Default risk profile

| Setting | Default |
|---|---:|
| Trading capital | ₹10,000–₹25,000 |
| Risk budget per trade | 0.5% of capital |
| Planned holding period | 3–10 trading days |
| Minimum reward/risk | 2.0 |
| Market | NSE/BSE cash equities |
| Execution | Paper trading only |

The program does **not** connect to a broker, place orders, or manage live positions.

## Quick start

Requires Python 3.10+.

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate
source .venv/bin/activate
pip install -r requirements.txt
cp config.example.yaml config.yaml
```

The example configuration includes 100 curated NSE symbols as a broad research universe. It is not an official index constituent list; verify current listing status, liquidity and corporate actions. Edit `config.yaml` to change symbols. The scanner pauses briefly between symbols to reduce data-provider throttling. Then run:

```bash
python -m src.scan --config config.yaml
python -m src.market_context
```

For NSE data, the scanner appends `.NS` for Yahoo Finance. You can use `.BO` explicitly for BSE symbols. Yahoo Finance is a convenience data source, not an exchange-authoritative feed.

## What it does

- Downloads daily OHLCV history for a curated 100-symbol NSE watchlist by default (editable in `config.yaml`).
- Calculates EMA 20/50, RSI(14), ATR(14), and relative volume.
- Flags a **research candidate** only when trend, momentum, volume, and breakout checks align.
- Calculates quantity from the configured maximum rupee risk, stop distance, capital allocation cap, and minimum 2R target.
- Prints a no-trade reason when data or risk constraints fail.
- Includes a CSV trade journal template and a simple risk calculator.

## Strategy overview

See [docs/strategy.md](docs/strategy.md) for entry filters, exits, gap risk, event checks, and operational rules. The scanner is deliberately conservative and should be validated with realistic backtests and paper trades before risking capital.

## Safety and limitations

1. Never treat a scanner flag as an instruction to buy.
2. Confirm the latest quote and liquidity independently; do not use stale end-of-day prices for execution.
3. Avoid illiquid, SME, suspended, ASM/GSM, circuit-bound, and poorly disclosed securities.
4. Check results, board meetings, dividends, splits, pledges, bulk/block deals, and exchange announcements.
5. Account for brokerage, STT, exchange transaction charges, GST, stamp duty, SEBI charges, and slippage. Rates vary; confirm current charges with your broker.
6. Risk limits do not eliminate overnight gaps, slippage, or loss beyond the planned stop.
7. No derivatives, leverage, short selling, or automatic live trading are implemented.

## Backtesting and tests

Run an exploratory historical simulation (default cost assumptions are illustrative):

```bash
python -m src.backtest --config config.yaml --cost-bps 20 --slippage-bps 5
```

Run unit tests:

```bash
python -m unittest discover -s tests -v
```

Backtest assumptions and important limitations are documented in [docs/backtesting.md](docs/backtesting.md). The GitHub Actions workflow runs the unit tests on pushes and pull requests.

## Project layout

- `config.example.yaml` — editable defaults and watchlist
- `src/indicators.py` — technical indicators
- `src/risk.py` — quantity and reward/risk calculations
- `src/scan.py` — daily watchlist scanner
- `src/backtest.py` — conservative next-session historical simulation
- `src/market_context.py` — NIFTY and sector-index EMA context
- `tests/` — unit tests for risk sizing and indicators
- `docs/strategy.md` — strategy and operating rules
- `docs/data-sources.md` — data quality and verification
- `docs/fundamental-event-checks.md` — news, corporate filings, FII/DII verification checklist
- `journal/trade_journal_template.csv` — paper-trade journal

## Disclaimer

This project is for learning and research only. It is not SEBI-registered investment advice, and it does not know your full financial situation. You are responsible for independent verification and every investment decision.
