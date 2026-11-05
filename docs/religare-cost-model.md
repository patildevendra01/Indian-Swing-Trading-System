# Religare Basic Plan delivery-cost estimate

This is an opt-in research cost model for NSE cash-equity delivery trades. It
does not change the legacy baseline, scanner, strategy rules, risk settings, or
execution behavior.

Run explicitly:

```bash
python -m src.backtest --config config.yaml --data-dir backtest_data \
  --output backtest_trades_religare.csv --cost-model religare_basic_estimate
```

The default remains `legacy_flat_bps`, preserving the original 20 bps-per-side
fee assumption and separate 5 bps-per-side slippage unless overridden.

## Included estimates

- Brokerage: 0.25% of buy turnover and 0.25% of sell turnover, per the
  Religare Basic Plan addendum.
- STT: 0.10% on delivery purchase and 0.10% on delivery sale.
- NSE cash-market transaction charge plus IPFT: ₹307 per crore per side,
  effective 1 March 2026.
- SEBI turnover fee: 0.0001% per side.
- Stamp duty: 0.015% on buy turnover.
- GST: 18% on brokerage, exchange charges and SEBI fee in this model.
- DP debit: ₹25 per sell trade as a conservative provisional assumption.

The public Religare depository schedule located for this estimate states ₹12
for delivery debit to the Religare pool account with POA/DDPI and ₹25 without
POA/DDPI. The schedule located is dated 2023; verify the current tariff and
account mandate. The config uses ₹25 until confirmed. DP charges may be applied
per scrip per sell day in a real contract note; the single-position-per-symbol
backtest approximates one debit per completed trade.

## Important caveats

- These are published schedule rates and estimates, not a verified client tariff
  or a substitute for contract-note reconciliation.
- The brokerage addendum may not reflect later account-specific amendments.
- The exchange charge is NSE-specific; BSE rates can differ.
- Rounding, minimum charges, illiquid-scrip surcharges, inter-settlement fees,
  DP/AMC plan differences and other adjustments are not fully modelled.
- Capital-gains tax is excluded.
- Slippage is separate and remains 5 bps per side by default.
- `gross_pnl_inr` remains after slippage; `estimated_costs_inr` contains
  brokerage/statutory/DP charges when this model is selected.
- This is still an independent-symbol backtest, not a shared-capital portfolio.
  It is not evidence of profitability or permission for live trading.
