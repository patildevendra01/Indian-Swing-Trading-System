# Indian Market Data: Source and Verification Policy

## Current implementation

The scanner downloads daily adjusted OHLCV through the `yfinance` Python package. NSE symbols normally use the Yahoo Finance suffix `.NS`; BSE symbols normally use `.BO`.

This is a convenience source only. Availability, symbol mapping, timestamps, adjustments, volume and historical completeness are not guaranteed. Free data may be delayed or revised.

## Primary verification

Before making a decision, verify information directly through:
- NSE India: https://www.nseindia.com/
- BSE India: https://www.bseindia.com/
- Company investor-relations pages and exchange-filed announcements.
- SEBI: https://www.sebi.gov.in/
- Your broker's live quote, order book, contract note, and charge schedule.

Use official exchange/company filings for material news and corporate actions. Do not rely solely on social media, forwarded messages, unverified Telegram/WhatsApp tips, or a headline aggregator.

## Trading costs

Include brokerage, STT, exchange transaction charges, GST, SEBI charges, stamp duty, and slippage. The exact amount depends on product, exchange, broker, and current regulations. Do not hard-code old fee rates; check your broker's latest tariff and applicable official rules.

## Data hygiene

- Confirm the latest available candle date before interpreting a scan.
- Handle missing bars, splits, dividends, symbol changes, and delisted securities.
- Do not assume adjusted prices are executable prices.
- Never use future data in a backtest; signals from a completed candle should be executed no earlier than the next tradable session.
