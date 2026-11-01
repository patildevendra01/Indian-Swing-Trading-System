# News, Fundamentals, and Institutional-Flow Verification

The project deliberately does not convert unverified headlines or social posts into automated signals. Before considering a candidate, complete these checks manually and record the source and timestamp in the journal.

## Company-specific checks
- Latest quarterly/annual results, guidance, margins, debt, cash flow, and auditor remarks.
- NSE/BSE corporate announcements, board meeting outcomes, investor presentations, and shareholding disclosures.
- Promoter holding changes, pledges/releases, insider trading disclosures, bulk/block deals.
- Results dates, dividends, splits, rights issues, buybacks, mergers, demergers, fundraising, and material litigation.
- Any exchange surveillance, trading suspension, circuit restriction, or material regulatory action.

## Market and institutional context
- NIFTY 50 and relevant sector-index trend; run `python -m src.market_context` for indicative EMA context.
- Check official NSE/BSE market data for FII/FPI and DII activity. These flows are aggregate context, not a standalone buy/sell signal.
- Check RBI policy, major macro releases, global risk events, currency and crude moves when relevant.
- Confirm the date and definition of every flow number; cash-market activity and derivatives positioning are different datasets.

## Primary-source starting points
- NSE announcements and corporate filings: https://www.nseindia.com/companies-listing/corporate-filings-announcements
- NSE market data: https://www.nseindia.com/market-data
- BSE corporate announcements: https://www.bseindia.com/corporates/ann.html
- SEBI disclosures and orders: https://www.sebi.gov.in/

Web pages and data portals can change. If an official source is unavailable, record the check as incomplete rather than assuming there is no event or risk.
