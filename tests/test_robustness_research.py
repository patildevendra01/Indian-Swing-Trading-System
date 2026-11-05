import unittest
import pandas as pd

from src.robustness_research import cost_sensitivity, reconstruct_portfolio


def trades():
    return pd.DataFrame([
        {"symbol":"AAA","period":"development_3y","entry_date":"2024-01-02","exit_date":"2024-01-04",
         "entry":100.0,"stop":95.0,"exit":110.0,"quantity":10,"gross_pnl_inr":100.0,
         "estimated_costs_inr":0.0,"net_pnl_inr":100.0},
        {"symbol":"BBB","period":"development_3y","entry_date":"2024-01-03","exit_date":"2024-01-05",
         "entry":100.0,"stop":95.0,"exit":90.0,"quantity":10,"gross_pnl_inr":-100.0,
         "estimated_costs_inr":0.0,"net_pnl_inr":-100.0},
        {"symbol":"CCC","period":"development_3y","entry_date":"2024-01-04","exit_date":"2024-01-06",
         "entry":100.0,"stop":95.0,"exit":110.0,"quantity":10,"gross_pnl_inr":100.0,
         "estimated_costs_inr":0.0,"net_pnl_inr":100.0},
        {"symbol":"DDD","period":"development_3y","entry_date":"2024-01-04","exit_date":"2024-01-06",
         "entry":100.0,"stop":95.0,"exit":110.0,"quantity":10,"gross_pnl_inr":100.0,
         "estimated_costs_inr":0.0,"net_pnl_inr":100.0},
    ])


class RobustnessResearchTests(unittest.TestCase):
    def test_costs_reduce_pnl_as_cost_scenario_increases(self):
        result = cost_sensitivity(trades(), [(20, 5), (40, 10)])
        self.assertEqual(len(result), 2)
        self.assertLess(result.iloc[1]["net_pnl_inr"], result.iloc[0]["net_pnl_inr"])

    def test_cost_sensitivity_matches_one_entry_and_one_exit_slippage(self):
        frame = trades().iloc[:1]
        result = cost_sensitivity(frame, [(20, 5)])
        # Raw gain ₹100; combined turnover ₹2,100; total modeled drag 25 bps.
        expected = 100.0 - 2100.0 * 25 / 10000
        self.assertAlmostEqual(result.iloc[0]["net_pnl_inr"], expected, places=2)

    def test_portfolio_applies_slippage_once_to_entry_plus_exit_turnover(self):
        result = reconstruct_portfolio(
            trades().iloc[:1], initial_capital=15000, risk_pct=0.5,
            max_position_pct=25, max_positions=3, cost_bps=0, slippage_bps=5
        )
        # Quantity is 15; raw gain ₹150; turnover ₹3,150; 5 bps drag = ₹1.575.
        self.assertAlmostEqual(result.iloc[0]["net_pnl_inr"], 148.43, places=2)

    def test_portfolio_respects_max_open_positions(self):
        result = reconstruct_portfolio(trades(), initial_capital=15000,
            risk_pct=0.5, max_position_pct=25, max_positions=2, cost_bps=0, slippage_bps=0)
        row = result.iloc[0]
        self.assertEqual(row["accepted_trades"], 2)
        self.assertEqual(row["rejected_max_positions"], 2)

    def test_portfolio_risk_budget_caps_quantity(self):
        result = reconstruct_portfolio(trades().iloc[:1], initial_capital=15000,
            risk_pct=0.5, max_position_pct=25, max_positions=3, cost_bps=0, slippage_bps=0)
        # Risk budget ₹75 / ₹5 risk per share = 15 shares, within ₹3,750 allocation.
        self.assertEqual(result.iloc[0]["accepted_trades"], 1)
        self.assertAlmostEqual(result.iloc[0]["net_pnl_inr"], 150.0)


if __name__ == "__main__":
    unittest.main()
