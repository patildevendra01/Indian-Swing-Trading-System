import tempfile
import unittest
from pathlib import Path
import yaml

from src.costs import DeliveryCostModel, load_cost_model


class DeliveryCostModelTests(unittest.TestCase):
    def model(self):
        return DeliveryCostModel(
            name="test", brokerage_rate=0.0025, stt_buy_rate=0.001,
            stt_sell_rate=0.001, exchange_rate=0.0000307,
            sebi_rate=0.000001, stamp_duty_buy_rate=0.00015,
            gst_rate=0.18, dp_sell_charge_inr=25.0,
        )

    def test_religare_basic_rates_calculate_each_leg_and_dp_once(self):
        result = self.model().calculate(100, 110, 10)
        self.assertEqual(result["brokerage_inr"], 5.25)
        self.assertEqual(result["stt_inr"], 2.10)
        self.assertEqual(result["stamp_duty_inr"], 0.15)
        self.assertEqual(result["dp_charges_inr"], 25.0)
        self.assertEqual(result["total_charges_inr"],
                         round(sum(v for k, v in result.items()
                                   if k != "total_charges_inr"), 2))

    def test_loader_rejects_unverified_null_rates(self):
        data = {"profiles": {"blank": {
            "brokerage_rate": None, "stt_buy_rate": None,
            "stt_sell_rate": None, "exchange_rate": None,
            "sebi_rate": None, "stamp_duty_buy_rate": None,
            "gst_rate": None, "dp_sell_charge_inr": None,
        }}}
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "costs.yaml"
            path.write_text(yaml.safe_dump(data), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "unverified/missing"):
                load_cost_model(path, "blank")

    def test_loader_reads_religare_profile(self):
        path = Path(__file__).resolve().parents[1] / "config" / "cost_models.example.yaml"
        model = load_cost_model(path, "religare_basic_estimate")
        self.assertEqual(model.brokerage_rate, 0.0025)
        self.assertEqual(model.dp_sell_charge_inr, 25.0)

    def test_invalid_trade_inputs_rejected(self):
        with self.assertRaises(ValueError):
            self.model().calculate(0, 100, 1)


if __name__ == "__main__":
    unittest.main()
