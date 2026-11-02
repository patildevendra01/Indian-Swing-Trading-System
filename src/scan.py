"""Daily OHLCV watchlist scanner. Flags are research candidates, not trade advice."""
import argparse
import time
from pathlib import Path
import sys

import pandas as pd
import yaml
import yfinance as yf

try:
    from .indicators import add_indicators
    from .risk import build_trade_plan
except ImportError:  # supports: python src/scan.py
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from src.indicators import add_indicators
    from src.risk import build_trade_plan


def load_config(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as handle:
        return yaml.safe_load(handle)


def yahoo_symbol(symbol: str, exchange: str) -> str:
    symbol = symbol.strip().upper()
    if "." in symbol:
        return symbol
    suffix = ".BO" if exchange.upper() == "BSE" else ".NS"
    return symbol + suffix


def scan_one(symbol: str, cfg: dict) -> dict:
    market, account, strategy = cfg["market"], cfg["account"], cfg["strategy"]
    ticker = yahoo_symbol(symbol, market.get("exchange", "NSE"))
    raw = yf.download(ticker, period=market.get("history_period", "1y"),
                      interval=market.get("interval", "1d"), auto_adjust=True,
                      progress=False, threads=False)
    if raw.empty:
        return {"symbol": ticker, "status": "SKIP", "reason": "No price history returned"}
    if isinstance(raw.columns, pd.MultiIndex):
        raw.columns = raw.columns.get_level_values(0)
    data = add_indicators(raw, strategy["ema_fast"], strategy["ema_slow"],
                          strategy["rsi_period"], strategy["atr_period"],
                          strategy["volume_lookback"], strategy["breakout_lookback"])
    row = data.iloc[-1]
    close = float(row["Close"])
    checks = {
        "uptrend": close > float(row["ema_fast"]) > float(row["ema_slow"]),
        "momentum": 50 <= float(row["rsi"]) <= 70,
        "volume": pd.notna(row["relative_volume"]) and float(row["relative_volume"]) >= strategy["min_relative_volume"],
        "breakout": pd.notna(row["prior_high"]) and close > float(row["prior_high"]),
        "price_floor": close >= strategy["min_price_inr"],
        "turnover": pd.notna(row["avg_turnover"]) and float(row["avg_turnover"]) >= strategy["min_avg_daily_turnover_inr"],
        "volatility": pd.notna(row["atr_pct"]) and float(row["atr_pct"]) <= strategy["max_atr_pct"],
    }
    failed = [name for name, passed in checks.items() if not passed]
    result = {"symbol": ticker, "date": str(data.index[-1].date()), "close": round(close, 2),
              "rsi": round(float(row["rsi"]), 1),
              "relative_volume": round(float(row["relative_volume"]), 2) if pd.notna(row["relative_volume"]) else None,
              "atr_pct": round(float(row["atr_pct"]), 2) if pd.notna(row["atr_pct"]) else None,
              "status": "RESEARCH_CANDIDATE" if not failed else "WATCH / SKIP",
              "reason": "All screening filters passed" if not failed else "Failed: " + ", ".join(failed)}
    if not failed:
        # ATR-based initial stop proxy. Validate support/structure manually before any trade.
        stop = close - 1.5 * float(row["atr"])
        try:
            plan = build_trade_plan(close, stop, float(account["capital_inr"]),
                                    float(account["risk_per_trade_pct"]),
                                    float(account["max_position_pct"]),
                                    float(strategy["min_reward_risk"]))
            result.update({"entry_reference": round(plan.entry, 2), "stop_reference": round(plan.stop, 2),
                           "target_reference": round(plan.target, 2), "quantity_ceiling": plan.quantity,
                           "planned_risk_inr": round(plan.planned_risk_inr, 2),
                           "position_value_inr": round(plan.position_value_inr, 2)})
        except ValueError as exc:
            result["status"] = "NO TRADE"
            result["reason"] = str(exc)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default="config.yaml", help="Path to local YAML config")
    parser.add_argument("--output", default="scan_results.csv", help="CSV output path")
    args = parser.parse_args()
    cfg = load_config(args.config)
    results = []
    for symbol in cfg.get("watchlist", []):
        try:
            result = scan_one(symbol, cfg)
        except Exception as exc:  # keep scanner running if one symbol/data source fails
            result = {"symbol": symbol, "status": "ERROR", "reason": str(exc)}
        results.append(result)
        print(f"{result['symbol']}: {result['status']} — {result['reason']}")
        # Gentle pacing reduces the chance of throttling on large watchlists.
        time.sleep(max(0.0, float(cfg.get("market", {}).get("scan_delay_seconds", 0.5))))
    if results:
        output = pd.DataFrame(results)
        output.to_csv(args.output, index=False)
        print(f"\nSaved {len(results)} rows to {args.output}")
        print("Review all candidates manually; this output is not an order instruction.")


if __name__ == "__main__":
    main()
