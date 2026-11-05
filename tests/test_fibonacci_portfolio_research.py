import unittest

import pandas as pd

from src.fibonacci_portfolio_research import replay_portfolio


class FlatCostModel:
    def calculate(self, entry_price, exit_price, quantity):
        return {"total_charges_inr": 10.0}


def config():
    return {
        "account": {
            "capital_inr": 15000,
            "risk_per_trade_pct": 0.5,
            "max_position_pct": 25.0,
            "max_open_positions": 3,
        }
    }


def trade(symbol, entry_date="2026-01-01", exit_date="2026-01-05",
          entry=100.0, exit=110.0, stop=95.0):
    return {
        "period": "development_3y",
        "setup": "fib_0618",
        "symbol": symbol,
        "signal_date": "2025-12-31",
        "entry_date": entry_date,
        "exit_date": exit_date,
        "entry": entry,
        "exit": exit,
        "stop": stop,
    }


class FibonacciPortfolioTests(unittest.TestCase):
    def test_enforces_three_open_positions_and_releases_cash_next_day(self):
        rows = [
            trade("AAA"), trade("BBB"), trade("CCC"), trade("DDD"),
            trade("AAA", entry_date="2026-01-06", exit_date="2026-01-09"),
        ]
        accepted, rejected, summary = replay_portfolio(
            pd.DataFrame(rows), config(), FlatCostModel(), slippage_bps=5.0
        )
        self.assertEqual(len(accepted), 4)
        self.assertEqual(len(rejected), 1)
        self.assertEqual(rejected.iloc[0]["reason"], "max_concurrent_positions")
        self.assertEqual(summary.iloc[0]["accepted_trades"], 4)
        self.assertEqual(summary.iloc[0]["risk_budget_per_entry_inr"], 75.0)
        self.assertLessEqual(accepted["planned_risk_inr"].max(), 75.0)

    def test_position_value_cap_is_respected(self):
        accepted, _, _ = replay_portfolio(
            pd.DataFrame([trade("AAA", entry=10.0, exit=11.0, stop=9.0)]),
            config(), FlatCostModel()
        )
        self.assertEqual(len(accepted), 1)
        self.assertLessEqual(accepted.iloc[0]["entry_notional_inr"], 3750.0)

    def test_rejects_overlapping_trade_for_same_symbol(self):
        rows = [
            trade("AAA", exit_date="2026-01-08"),
            trade("AAA", entry_date="2026-01-04", exit_date="2026-01-10"),
        ]
        accepted, rejected, _ = replay_portfolio(
            pd.DataFrame(rows), config(), FlatCostModel()
        )
        self.assertEqual(len(accepted), 1)
        self.assertEqual(rejected.iloc[0]["reason"], "symbol_already_open")


if __name__ == "__main__":
    unittest.main()
