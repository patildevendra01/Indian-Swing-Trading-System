import unittest

from src.time_exit_research import protection_state


class ProfitProtectionRuleTests(unittest.TestCase):
    def test_first_close_at_one_r_arms_but_does_not_exit(self):
        self.assertEqual(protection_state(1.0, False), (True, False))

    def test_armed_trade_triggers_only_below_half_r(self):
        self.assertEqual(protection_state(0.49, True), (True, True))
        self.assertEqual(protection_state(0.50, True), (True, False))
        self.assertEqual(protection_state(0.75, True), (True, False))

    def test_unarmed_trade_does_not_trigger_below_half_r(self):
        self.assertEqual(protection_state(0.25, False), (False, False))

    def test_arming_is_persistent(self):
        self.assertEqual(protection_state(0.8, True), (True, False))


if __name__ == "__main__":
    unittest.main()
