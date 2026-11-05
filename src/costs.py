"""Transparent transaction-cost models for Indian equity-delivery research.

The Religare profile is an estimate based on public schedules, not a live tariff feed.
Slippage is deliberately calculated separately by the backtester.
"""
from dataclasses import dataclass
from pathlib import Path
import yaml


@dataclass(frozen=True)
class DeliveryCostModel:
    name: str
    brokerage_rate: float
    stt_buy_rate: float
    stt_sell_rate: float
    exchange_rate: float
    sebi_rate: float
    stamp_duty_buy_rate: float
    gst_rate: float
    dp_sell_charge_inr: float
    gst_on_brokerage: bool = True
    gst_on_exchange: bool = True
    gst_on_sebi: bool = True

    def calculate(self, entry_price: float, exit_price: float, quantity: int) -> dict:
        if entry_price <= 0 or exit_price <= 0 or quantity <= 0:
            raise ValueError("prices and quantity must be positive")
        buy_value, sell_value = entry_price * quantity, exit_price * quantity
        brokerage = round((buy_value + sell_value) * self.brokerage_rate, 2)
        stt = round(buy_value * self.stt_buy_rate + sell_value * self.stt_sell_rate, 2)
        exchange = round((buy_value + sell_value) * self.exchange_rate, 2)
        sebi = round((buy_value + sell_value) * self.sebi_rate, 2)
        stamp = round(buy_value * self.stamp_duty_buy_rate, 2)
        gst_base = ((brokerage if self.gst_on_brokerage else 0.0)
                    + (exchange if self.gst_on_exchange else 0.0)
                    + (sebi if self.gst_on_sebi else 0.0))
        gst = round(gst_base * self.gst_rate, 2)
        dp = round(self.dp_sell_charge_inr, 2)
        total = round(brokerage + stt + exchange + sebi + stamp + gst + dp, 2)
        return {
            "brokerage_inr": brokerage, "stt_inr": stt,
            "exchange_charges_inr": exchange, "sebi_charges_inr": sebi,
            "stamp_duty_inr": stamp, "gst_inr": gst,
            "dp_charges_inr": dp, "total_charges_inr": total,
        }


def load_cost_model(path: str | Path, profile: str) -> DeliveryCostModel:
    with Path(path).open(encoding="utf-8") as handle:
        config = yaml.safe_load(handle) or {}
    profiles = config.get("profiles", {})
    if profile not in profiles:
        raise ValueError(f"Unknown cost profile {profile!r}; available: {sorted(profiles)}")
    item = profiles[profile]
    required = ("brokerage_rate", "stt_buy_rate", "stt_sell_rate", "exchange_rate",
                "sebi_rate", "stamp_duty_buy_rate", "gst_rate", "dp_sell_charge_inr")
    missing = [key for key in required if item.get(key) is None]
    if missing:
        raise ValueError(f"Cost profile {profile!r} has unverified/missing rates: {missing}")
    values = {key: float(item[key]) for key in required}
    if any(value < 0 for value in values.values()):
        raise ValueError("Cost rates and charges must be non-negative")
    return DeliveryCostModel(
        name=profile, **values,
        gst_on_brokerage=bool(item.get("gst_on_brokerage", True)),
        gst_on_exchange=bool(item.get("gst_on_exchange", True)),
        gst_on_sebi=bool(item.get("gst_on_sebi", True)),
    )
