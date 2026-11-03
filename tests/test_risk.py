import unittest
from src.risk import build_trade_plan


class RiskTests(unittest.TestCase):
    def test_risk_budget_and_two_r_target(self):
        plan = build_trade_plan(entry=100, stop=95, capital=20000, risk_pct=0.5,
                                max_position_pct=25, min_reward_risk=2)
        self.assertLessEqual(plan.planned_risk_inr, 100)
        self.assertAlmostEqual(plan.target, 110)
        self.assertEqual(plan.quantity, 20)

    def test_rejects_stop_above_entry(self):
        with self.assertRaises(ValueError):
            build_trade_plan(100, 101, 20000)

    def test_rejects_when_one_share_exceeds_risk(self):
        with self.assertRaises(ValueError):
            build_trade_plan(1000, 900, 10000, risk_pct=0.5)

    def test_high_price_share_is_marked_infeasible_by_trade_plan(self):
        # With ₹15,000 capital and a 25% allocation cap, a ₹49,640 share
        # cannot fit even one share into the configured position budget.
        with self.assertRaisesRegex(ValueError, "position-size limits"):
            build_trade_plan(entry=49640, stop=47844.305, capital=15000,
                             risk_pct=0.5, max_position_pct=25,
                             min_reward_risk=2)


if __name__ == "__main__":
    unittest.main()
