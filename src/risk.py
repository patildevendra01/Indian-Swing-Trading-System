"""Risk-first position sizing for cash-equity swing trades."""
from dataclasses import dataclass


@dataclass(frozen=True)
class TradePlan:
    entry: float
    stop: float
    target: float
    quantity: int
    risk_per_share: float
    planned_risk_inr: float
    reward_risk: float
    position_value_inr: float


def build_trade_plan(entry: float, stop: float, capital: float,
                     risk_pct: float = 0.5, max_position_pct: float = 25.0,
                     min_reward_risk: float = 2.0) -> TradePlan:
    values = (entry, stop, capital, risk_pct, max_position_pct, min_reward_risk)
    if any(v <= 0 for v in values):
        raise ValueError("All inputs must be positive")
    if stop >= entry:
        raise ValueError("For a long cash-equity trade, stop must be below entry")
    risk_per_share = entry - stop
    risk_budget = capital * risk_pct / 100
    max_position_value = capital * max_position_pct / 100
    quantity_by_risk = int(risk_budget // risk_per_share)
    quantity_by_capital = int(max_position_value // entry)
    quantity = min(quantity_by_risk, quantity_by_capital)
    if quantity < 1:
        raise ValueError("No trade: one share exceeds risk or position-size limits")
    target = entry + min_reward_risk * risk_per_share
    return TradePlan(entry, stop, target, quantity, risk_per_share,
                     quantity * risk_per_share, min_reward_risk,
                     quantity * entry)
